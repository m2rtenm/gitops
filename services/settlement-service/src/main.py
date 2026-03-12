import os
import logging
import psycopg2
import json
from flask import Flask, jsonify, request
from flasgger import Flasgger
from kafka import KafkaProducer, KafkaConsumer
from prometheus_client import Counter, Histogram, generate_latest
import time
from datetime import datetime

app = Flask(__name__)
Flasgger(app, template={
    "swagger": "2.0",
    "info": {
        "title": "Settlement Service API",
        "description": "Settlement and reconciliation service",
        "version": "1.0.0"
    },
    "basePath": "/api/v1"
})
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Prometheus metrics
settlement_created = Counter('settlement_created_total', 'Total settlements created')
settlement_errors = Counter('settlement_errors_total', 'Total settlement errors')
request_duration = Histogram('settlement_request_duration_seconds', 'Request duration in seconds')

# Configuration
KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:9092').split(',')
KAFKA_TOPIC_SETTLEMENT = os.getenv('KAFKA_TOPIC_SETTLEMENT', 'fintech.settlement')
KAFKA_TOPIC_EVENTS = os.getenv('KAFKA_TOPIC_EVENTS', 'fintech.settlement-events')
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

    The ledger database may not be ready immediately; loop until a
    connection succeeds and then create tables.
    """
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settlements (
                    id SERIAL PRIMARY KEY,
                    transaction_id BIGINT UNIQUE NOT NULL,
                    settlement_date DATE NOT NULL,
                    settlement_time TIMESTAMP DEFAULT NOW(),
                    amount NUMERIC(19, 4) NOT NULL,
                    status VARCHAR(20) DEFAULT 'PENDING',
                    reconciliation_status VARCHAR(20) DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT NOW(),
                    settled_at TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settlement_batch (
                    id SERIAL PRIMARY KEY,
                    batch_date DATE NOT NULL,
                    batch_time TIMESTAMP DEFAULT NOW(),
                    total_amount NUMERIC(19, 4) NOT NULL,
                    transaction_count INT NOT NULL,
                    status VARCHAR(20) DEFAULT 'PENDING'
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
    return jsonify({'status': 'healthy', 'service': 'settlement-service'}), 200

@app.route('/ready', methods=['GET'])
def ready():
    """Readiness check endpoint"""
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({'status': 'ready', 'service': 'settlement-service'}), 200
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return jsonify({'status': 'not-ready', 'error': str(e)}), 503

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()

@app.route('/api/v1/settlements', methods=['POST'])
@request_duration.time()
def create_settlement():
    """Create a settlement record
    ---
    tags:
      - Settlements
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            transaction_id:
              type: integer
            amount:
              type: number
    responses:
      201:
        description: Settlement created
      500:
        description: Server error
    """
    try:
        data = request.json
        transaction_id = data.get('transaction_id')
        amount = data.get('amount')
        settlement_date = data.get('settlement_date')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO settlements (transaction_id, amount, settlement_date)
            VALUES (%s, %s, %s)
            RETURNING id, transaction_id, status, created_at
        ''', (transaction_id, amount, settlement_date))
        
        settlement = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        settlement_created.inc()
        logger.info(f"Settlement created: {settlement[0]}")
        
        # Send event to Kafka
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            producer.send(KAFKA_TOPIC_EVENTS, {
                'event_type': 'settlement_created',
                'settlement_id': settlement[0],
                'transaction_id': transaction_id,
                'timestamp': time.time()
            })
            producer.flush()
        except Exception as e:
            logger.error(f"Failed to send Kafka event: {e}")
        
        return jsonify({
            'id': settlement[0],
            'transaction_id': settlement[1],
            'amount': float(amount),
            'status': settlement[2],
            'created_at': str(settlement[3])
        }), 201
    
    except Exception as e:
        settlement_errors.inc()
        logger.error(f"Failed to create settlement: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/settlements/<int:settlement_id>', methods=['GET'])
def get_settlement(settlement_id):
    """Get settlement by ID"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, transaction_id, amount, status, settlement_date, created_at
            FROM settlements WHERE id = %s
        ''', (settlement_id,))
        
        settlement = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not settlement:
            return jsonify({'error': 'Settlement not found'}), 404
        
        return jsonify({
            'id': settlement[0],
            'transaction_id': settlement[1],
            'amount': float(settlement[2]),
            'status': settlement[3],
            'settlement_date': str(settlement[4]),
            'created_at': str(settlement[5])
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to get settlement: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/settlements/batch', methods=['GET'])
def get_settlement_batch():
    """Get settlement batch summary for today"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*), SUM(amount), AVG(amount), MIN(amount), MAX(amount)
            FROM settlements 
            WHERE settlement_date = CURRENT_DATE
        ''')
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not result or result[0] is None:
            return jsonify({
                'settlement_date': 'today',
                'transaction_count': 0,
                'total_amount': 0
            }), 200
        
        return jsonify({
            'settlement_date': 'today',
            'transaction_count': result[0],
            'total_amount': float(result[1]) if result[1] else 0,
            'average_amount': float(result[2]) if result[2] else 0,
            'min_amount': float(result[3]) if result[3] else 0,
            'max_amount': float(result[4]) if result[4] else 0
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to get settlement batch: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080, debug=False)
