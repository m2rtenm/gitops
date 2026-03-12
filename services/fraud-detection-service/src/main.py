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
        "title": "Fraud Detection Service API",
        "description": "Real-time fraud detection and alerting service",
        "version": "1.0.0"
    },
    "basePath": "/api/v1"
})
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Prometheus metrics
fraud_alerts = Counter('fraud_alerts_total', 'Total fraud alerts generated')
fraud_high_risk = Counter('fraud_high_risk_total', 'High risk transactions detected')
request_duration = Histogram('fraud_detection_request_duration_seconds', 'Request duration in seconds')

# Configuration
KAFKA_BROKERS = os.getenv('KAFKA_BROKERS', 'localhost:9092').split(',')
KAFKA_TOPIC_TRANSACTIONS = os.getenv('KAFKA_TOPIC_TRANSACTIONS', 'fintech.transactions')
KAFKA_TOPIC_ALERTS = os.getenv('KAFKA_TOPIC_ALERTS', 'fintech.fraud-alerts')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'audit_db')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'audit_user')
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

    Will keep attempting to connect until the audit DB is ready.
    """
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fraud_alerts (
                    id BIGSERIAL PRIMARY KEY,
                    transaction_id BIGINT NOT NULL,
                    alert_type VARCHAR(50) NOT NULL,
                    risk_score NUMERIC(5, 2) NOT NULL,
                    alert_message TEXT,
                    rule_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW(),
                    reviewed_at TIMESTAMP,
                    reviewed_by VARCHAR(255),
                    action_taken VARCHAR(50)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transaction_audit (
                    id BIGSERIAL PRIMARY KEY,
                    transaction_id BIGINT NOT NULL,
                    account_id BIGINT NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    timestamp TIMESTAMP DEFAULT NOW(),
                    user_id VARCHAR(255),
                    ip_address VARCHAR(45),
                    status VARCHAR(20),
                    error_message TEXT
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

def calculate_risk_score(transaction):
    """Calculate risk score for a transaction"""
    risk_score = 0.0
    rules_triggered = []
    
    amount = float(transaction.get('amount', 0))
    
    # Rule 1: Large transaction
    if amount > 10000:
        risk_score += 0.3
        rules_triggered.append('large_transaction')
    
    # Rule 2: Unusual time (example)
    hour = datetime.now().hour
    if hour < 6 or hour > 22:
        risk_score += 0.2
        rules_triggered.append('unusual_time')
    
    # Rule 3: Multiple transactions in short time (simulated)
    if amount > 5000:
        risk_score += 0.25
        rules_triggered.append('high_value_transaction')
    
    return min(risk_score * 100, 99), rules_triggered

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
    return jsonify({'status': 'healthy', 'service': 'fraud-detection-service'}), 200

@app.route('/ready', methods=['GET'])
def ready():
    """Readiness check endpoint"""
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({'status': 'ready', 'service': 'fraud-detection-service'}), 200
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return jsonify({'status': 'not-ready', 'error': str(e)}), 503

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()

@app.route('/api/v1/analyze', methods=['POST'])
@request_duration.time()
def analyze_transaction():
    """Analyze transaction for fraud risk
    ---
    tags:
      - Fraud Detection
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
            account_id:
              type: integer
    responses:
      200:
        description: Risk analysis result
      500:
        description: Server error
    """
    try:
        data = request.json
        transaction_id = data.get('transaction_id')
        amount = data.get('amount')
        from_account = data.get('from_account')
        to_account = data.get('to_account')
        
        risk_score, rules = calculate_risk_score(data)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        alert_type = 'HIGH_RISK' if risk_score > 70 else 'MEDIUM_RISK' if risk_score > 40 else 'LOW_RISK'
        
        cursor.execute('''
            INSERT INTO fraud_alerts 
            (transaction_id, alert_type, risk_score, rule_name, alert_message)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, alert_type, risk_score
        ''', (transaction_id, alert_type, risk_score, ','.join(rules), f'Rules triggered: {", ".join(rules)}'))
        
        alert = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        fraud_alerts.inc()
        if risk_score > 70:
            fraud_high_risk.inc()
        
        logger.info(f"Fraud alert created: {alert[0]} (score: {alert[2]})")
        
        # Send alert to Kafka
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            producer.send(KAFKA_TOPIC_ALERTS, {
                'alert_id': alert[0],
                'transaction_id': transaction_id,
                'alert_type': alert[1],
                'risk_score': float(alert[2]),
                'timestamp': time.time(),
                'rules': rules
            })
            producer.flush()
        except Exception as e:
            logger.error(f"Failed to send Kafka alert: {e}")
        
        return jsonify({
            'alert_id': alert[0],
            'transaction_id': transaction_id,
            'alert_type': alert[1],
            'risk_score': float(alert[2]),
            'rules_triggered': rules,
            'timestamp': datetime.now().isoformat()
        }), 201
    
    except Exception as e:
        logger.error(f"Failed to analyze transaction: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/alerts', methods=['GET'])
def get_alerts():
    """Get recent fraud alerts"""
    try:
        limit = request.args.get('limit', default=10, type=int)
        min_risk = request.args.get('min_risk', default=0, type=float)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, transaction_id, alert_type, risk_score, alert_message, created_at
            FROM fraud_alerts
            WHERE risk_score >= %s
            ORDER BY created_at DESC
            LIMIT %s
        ''', (min_risk, limit))
        
        alerts = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            'alerts': [
                {
                    'id': a[0],
                    'transaction_id': a[1],
                    'alert_type': a[2],
                    'risk_score': float(a[3]),
                    'message': a[4],
                    'created_at': str(a[5])
                }
                for a in alerts
            ]
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/alerts/<int:alert_id>/review', methods=['POST'])
def review_alert(alert_id):
    """Review and take action on an alert"""
    try:
        data = request.json
        action = data.get('action', 'REVIEWED')  # REVIEWED, APPROVED, BLOCKED
        reviewed_by = data.get('reviewed_by', 'system')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE fraud_alerts
            SET reviewed_at = NOW(), action_taken = %s, reviewed_by = %s
            WHERE id = %s
            RETURNING id, alert_type, risk_score
        ''', (action, reviewed_by, alert_id))
        
        alert = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        if not alert:
            return jsonify({'error': 'Alert not found'}), 404
        
        logger.info(f"Alert {alert_id} reviewed with action: {action}")
        
        return jsonify({
            'id': alert[0],
            'alert_type': alert[1],
            'risk_score': float(alert[2]),
            'action': action,
            'reviewed_at': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"Failed to review alert: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080, debug=False)
