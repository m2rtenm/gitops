import os
import logging
import psycopg2
import json
from flask import Flask, jsonify, request
from flasgger import Flasgger
from kafka import KafkaProducer, KafkaConsumer
from prometheus_client import Counter, Histogram, generate_latest
import time

app = Flask(__name__)
Flasgger(app, template={
    "swagger": "2.0",
    "info": {
        "title": "Account Service API",
        "description": "Customer account management service",
        "version": "1.0.0"
    },
    "basePath": "/api/v1"
})
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Prometheus metrics
account_created = Counter('account_created_total', 'Total accounts created')
account_errors = Counter('account_errors_total', 'Total account errors')
request_duration = Histogram('account_request_duration_seconds', 'Request duration in seconds')

# Configuration
KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:9092').split(',')
KAFKA_TOPIC_ACCOUNTS = os.getenv('KAFKA_TOPIC_ACCOUNTS', 'fintech.accounts')
KAFKA_TOPIC_EVENTS = os.getenv('KAFKA_TOPIC_EVENTS', 'fintech.account-events')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'accounts_db')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'accounts_user')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')

def get_db_connection():
    """Connect to PostgreSQL database"""
    # simple connection wrapper used by readiness checks and queries
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

def init_db():
    """Initialize database schema.

    This function will retry indefinitely until the database becomes
    available. That makes startup resilient in docker-compose where
    the database container may not be ready immediately.
    """
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    id SERIAL PRIMARY KEY,
                    customer_id BIGINT UNIQUE NOT NULL,
                    account_number VARCHAR(20) UNIQUE NOT NULL,
                    account_type VARCHAR(50) NOT NULL,
                    balance NUMERIC(19, 4) DEFAULT 0,
                    currency VARCHAR(3) DEFAULT 'USD',
                    status VARCHAR(20) DEFAULT 'ACTIVE',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            conn.commit()
            cursor.close()
            conn.close()
            logger.info("Database initialized")
            break
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            logger.info("Retrying in 3 seconds...")
            time.sleep(3)

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        request_duration.observe(duration)
    return response

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'account-service'}), 200

@app.route('/ready', methods=['GET'])
def ready():
    """Readiness check endpoint"""
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({'status': 'ready', 'service': 'account-service'}), 200
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return jsonify({'status': 'not-ready', 'error': str(e)}), 503

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()

@app.route('/api/v1/accounts', methods=['POST'])
@request_duration.time()
def create_account():
    """Create a new account
    ---
    tags:
      - Accounts
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            customer_id:
              type: integer
              example: 12345
            account_number:
              type: string
              example: "ACC-001"
            account_type:
              type: string
              example: "CHECKING"
              enum: ["CHECKING", "SAVINGS", "MONEY_MARKET"]
    responses:
      201:
        description: Account created successfully
        schema:
          properties:
            id:
              type: integer
            customer_id:
              type: integer
            account_number:
              type: string
            status:
              type: string
      500:
        description: Server error
    """
    try:
        data = request.json
        customer_id = data.get('customer_id')
        account_number = data.get('account_number')
        account_type = data.get('account_type', 'CHECKING')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO accounts (customer_id, account_number, account_type)
            VALUES (%s, %s, %s)
            RETURNING id, customer_id, account_number, status
        ''', (customer_id, account_number, account_type))
        
        account = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        account_created.inc()
        logger.info(f"Account created: {account[0]}")
        
        # Send event to Kafka
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            producer.send(KAFKA_TOPIC_EVENTS, {
                'event_type': 'account_created',
                'account_id': account[0],
                'customer_id': account[1],
                'timestamp': time.time()
            })
            producer.flush()
        except Exception as e:
            logger.error(f"Failed to send Kafka event: {e}")
        
        return jsonify({
            'id': account[0],
            'customer_id': account[1],
            'account_number': account[2],
            'status': account[3]
        }), 201
    
    except Exception as e:
        account_errors.inc()
        logger.error(f"Failed to create account: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/accounts/<int:account_id>', methods=['GET'])
def get_account(account_id):
    """Get account by ID
    ---
    tags:
      - Accounts
    parameters:
      - in: path
        name: account_id
        type: integer
        required: true
    responses:
      200:
        description: Account details
        schema:
          properties:
            id:
              type: integer
            customer_id:
              type: integer
            account_number:
              type: string
            account_type:
              type: string
            balance:
              type: number
            status:
              type: string
      404:
        description: Account not found
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, customer_id, account_number, account_type, balance, status
            FROM accounts WHERE id = %s
        ''', (account_id,))
        
        account = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        
        return jsonify({
            'id': account[0],
            'customer_id': account[1],
            'account_number': account[2],
            'account_type': account[3],
            'balance': float(account[4]),
            'status': account[5]
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to get account: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/accounts/<int:account_id>/balance', methods=['GET'])
def get_balance(account_id):
    """Get account balance
    ---
    tags:
      - Accounts
    parameters:
      - in: path
        name: account_id
        type: integer
        required: true
    responses:
      200:
        description: Account balance
        schema:
          properties:
            account_id:
              type: integer
            balance:
              type: number
      404:
        description: Account not found
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance FROM accounts WHERE id = %s', (account_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not result:
            return jsonify({'error': 'Account not found'}), 404
        
        return jsonify({'account_id': account_id, 'balance': float(result[0])}), 200
    
    except Exception as e:
        logger.error(f"Failed to get balance: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080, debug=False)
