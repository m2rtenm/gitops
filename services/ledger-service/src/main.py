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
        "title": "Ledger Service API",
        "description": "Immutable ledger and balance tracking service",
        "version": "1.0.0"
    },
    "basePath": "/api/v1"
})
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Prometheus metrics
ledger_entry_created = Counter('ledger_entry_created_total', 'Total ledger entries created')
ledger_errors = Counter('ledger_errors_total', 'Total ledger errors')
request_duration = Histogram('ledger_request_duration_seconds', 'Request duration in seconds')

# Configuration
KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:9092').split(',')
KAFKA_TOPIC_LEDGER = os.getenv('KAFKA_TOPIC_LEDGER', 'fintech.ledger')
KAFKA_TOPIC_EVENTS = os.getenv('KAFKA_TOPIC_EVENTS', 'fintech.ledger-events')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'ledger_db')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'ledger_user')
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

    Wait until the ledger database accepts connections. This avoids
    startup failures when Postgres isn't ready yet (e.g. in docker-compose).
    """
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ledger (
                    id BIGSERIAL PRIMARY KEY,
                    transaction_id BIGINT UNIQUE NOT NULL,
                    account_from BIGINT NOT NULL,
                    account_to BIGINT NOT NULL,
                    amount NUMERIC(19, 4) NOT NULL,
                    currency VARCHAR(3) DEFAULT 'USD',
                    status VARCHAR(20) DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT NOW(),
                    settled_at TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS balances (
                    id SERIAL PRIMARY KEY,
                    account_id BIGINT UNIQUE NOT NULL,
                    balance NUMERIC(19, 4) NOT NULL DEFAULT 0,
                    reserved NUMERIC(19, 4) DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT NOW(),
                    version BIGINT DEFAULT 1
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
    return jsonify({'status': 'healthy', 'service': 'ledger-service'}), 200

@app.route('/ready', methods=['GET'])
def ready():
    """Readiness check endpoint"""
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({'status': 'ready', 'service': 'ledger-service'}), 200
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return jsonify({'status': 'not-ready', 'error': str(e)}), 503

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()

@app.route('/api/v1/ledger', methods=['POST'])
@request_duration.time()
def create_ledger_entry():
    """Create a ledger entry (immutable)
    ---
    tags:
      - Ledger
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            transaction_id:
              type: integer
            account_from:
              type: integer
            account_to:
              type: integer
            amount:
              type: number
    responses:
      201:
        description: Ledger entry created
      500:
        description: Server error
    """
    try:
        data = request.json
        transaction_id = data.get('transaction_id')
        account_from = data.get('account_from')
        account_to = data.get('account_to')
        amount = data.get('amount')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO ledger (transaction_id, account_from, account_to, amount)
            VALUES (%s, %s, %s, %s)
            RETURNING id, transaction_id, status, created_at
        ''', (transaction_id, account_from, account_to, amount))
        
        entry = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        ledger_entry_created.inc()
        logger.info(f"Ledger entry created: {entry[0]}")
        
        # Send event to Kafka
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            producer.send(KAFKA_TOPIC_EVENTS, {
                'event_type': 'ledger_entry_created',
                'ledger_id': entry[0],
                'transaction_id': transaction_id,
                'timestamp': time.time()
            })
            producer.flush()
        except Exception as e:
            logger.error(f"Failed to send Kafka event: {e}")
        
        return jsonify({
            'id': entry[0],
            'transaction_id': entry[1],
            'account_from': account_from,
            'account_to': account_to,
            'amount': float(amount),
            'status': entry[2],
            'created_at': str(entry[3])
        }), 201
    
    except Exception as e:
        ledger_errors.inc()
        logger.error(f"Failed to create ledger entry: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/ledger/<int:ledger_id>', methods=['GET'])
def get_ledger_entry(ledger_id):
    """Get ledger entry by ID (read-only)
    ---
    tags:
      - Ledger
    parameters:
      - in: path
        name: ledger_id
        type: integer
        required: true
    responses:
      200:
        description: Ledger entry
      404:
        description: Entry not found
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, transaction_id, account_from, account_to, amount, status, created_at
            FROM ledger WHERE id = %s
        ''', (ledger_id,))
        
        entry = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not entry:
            return jsonify({'error': 'Ledger entry not found'}), 404
        
        return jsonify({
            'id': entry[0],
            'transaction_id': entry[1],
            'account_from': entry[2],
            'account_to': entry[3],
            'amount': float(entry[4]),
            'status': entry[5],
            'created_at': str(entry[6])
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to get ledger entry: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/accounts/<int:account_id>/balance', methods=['GET'])
def get_account_balance(account_id):
    """Get account balance from ledger
    ---
    tags:
      - Ledger
    parameters:
      - in: path
        name: account_id
        type: integer
        required: true
    responses:
      200:
        description: Account balance
      404:
        description: Account not found
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance, reserved FROM balances WHERE account_id = %s', (account_id,))
        result = cursor.fetchone()
        
        if not result:
            cursor.execute('SELECT 0, 0')
            result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'account_id': account_id,
            'balance': float(result[0]),
            'reserved': float(result[1]),
            'available': float(result[0] - result[1])
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to get account balance: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080, debug=False)
