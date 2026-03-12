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
        "title": "Transaction Service API",
        "description": "Transaction processing and history service",
        "version": "1.0.0"
    },
    "basePath": "/api/v1"
})
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Prometheus metrics
transaction_created = Counter('transaction_created_total', 'Total transactions created')
transaction_errors = Counter('transaction_errors_total', 'Total transaction errors')
request_duration = Histogram('transaction_request_duration_seconds', 'Request duration in seconds')

# Configuration
KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:9092').split(',')
KAFKA_TOPIC_TRANSACTIONS = os.getenv('KAFKA_TOPIC_TRANSACTIONS', 'fintech.transactions')
KAFKA_TOPIC_EVENTS = os.getenv('KAFKA_TOPIC_EVENTS', 'fintech.transaction-events')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'accounts_db')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'accounts_user')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')

def get_db_connection():
    """Connect to PostgreSQL database"""
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
    """Initialize database schema with retry.

    Wait for the database to be reachable before creating tables so that
    the container startup doesn't fail when Postgres isn't accepting
    connections immediately.
    """
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    from_account_id BIGINT NOT NULL,
                    to_account_id BIGINT NOT NULL,
                    amount NUMERIC(19, 4) NOT NULL,
                    currency VARCHAR(3) DEFAULT 'USD',
                    status VARCHAR(20) DEFAULT 'PENDING',
                    description TEXT,
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
    return jsonify({'status': 'healthy', 'service': 'transaction-service'}), 200

@app.route('/ready', methods=['GET'])
def ready():
    """Readiness check endpoint"""
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({'status': 'ready', 'service': 'transaction-service'}), 200
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return jsonify({'status': 'not-ready', 'error': str(e)}), 503

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()

@app.route('/api/v1/transactions', methods=['POST'])
@request_duration.time()
def create_transaction():
    """Create a new transaction
    ---
    tags:
      - Transactions
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            from_account_id:
              type: integer
            to_account_id:
              type: integer
            amount:
              type: number
            description:
              type: string
    responses:
      201:
        description: Transaction created
      500:
        description: Server error
    """
    try:
        data = request.json
        from_account_id = data.get('from_account_id')
        to_account_id = data.get('to_account_id')
        amount = data.get('amount')
        description = data.get('description', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO transactions (from_account_id, to_account_id, amount, description)
            VALUES (%s, %s, %s, %s)
            RETURNING id, status, created_at
        ''', (from_account_id, to_account_id, amount, description))
        
        transaction = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        transaction_created.inc()
        logger.info(f"Transaction created: {transaction[0]}")
        
        # Send event to Kafka
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            producer.send(KAFKA_TOPIC_EVENTS, {
                'event_type': 'transaction_created',
                'transaction_id': transaction[0],
                'from_account_id': from_account_id,
                'to_account_id': to_account_id,
                'amount': float(amount),
                'timestamp': time.time()
            })
            producer.flush()
        except Exception as e:
            logger.error(f"Failed to send Kafka event: {e}")
        
        return jsonify({
            'id': transaction[0],
            'from_account_id': from_account_id,
            'to_account_id': to_account_id,
            'amount': float(amount),
            'status': transaction[1],
            'created_at': str(transaction[2])
        }), 201
    
    except Exception as e:
        transaction_errors.inc()
        logger.error(f"Failed to create transaction: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/transactions/<int:transaction_id>', methods=['GET'])
def get_transaction(transaction_id):
    """Get transaction by ID
    ---
    tags:
      - Transactions
    parameters:
      - in: path
        name: transaction_id
        type: integer
        required: true
    responses:
      200:
        description: Transaction details
      404:
        description: Transaction not found
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, from_account_id, to_account_id, amount, status, created_at
            FROM transactions WHERE id = %s
        ''', (transaction_id,))
        
        transaction = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404
        
        return jsonify({
            'id': transaction[0],
            'from_account_id': transaction[1],
            'to_account_id': transaction[2],
            'amount': float(transaction[3]),
            'status': transaction[4],
            'created_at': str(transaction[5])
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to get transaction: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/accounts/<int:account_id>/transactions', methods=['GET'])
def get_account_transactions(account_id):
    """Get all transactions for an account
    ---
    tags:
      - Transactions
    parameters:
      - in: path
        name: account_id
        type: integer
        required: true
    responses:
      200:
        description: List of transactions for account
      404:
        description: Account not found
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, from_account_id, to_account_id, amount, status, created_at
            FROM transactions 
            WHERE from_account_id = %s OR to_account_id = %s
            ORDER BY created_at DESC LIMIT 100
        ''', (account_id, account_id))
        
        transactions = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            'account_id': account_id,
            'transactions': [
                {
                    'id': t[0],
                    'from_account_id': t[1],
                    'to_account_id': t[2],
                    'amount': float(t[3]),
                    'status': t[4],
                    'created_at': str(t[5])
                }
                for t in transactions
            ]
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to get transactions: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080, debug=False)
