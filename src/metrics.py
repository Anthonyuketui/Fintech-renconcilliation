"""
Prometheus metrics for FinTech reconciliation system.
Tracks business and technical metrics for monitoring and alerting.
"""

from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time
from functools import wraps
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# Business Metrics
RECONCILIATION_RUNS_TOTAL = Counter(
    'reconciliation_runs_total',
    'Total number of reconciliation runs',
    ['processor', 'status']
)

TRANSACTIONS_PROCESSED_TOTAL = Counter(
    'transactions_processed_total',
    'Total transactions processed',
    ['processor', 'source']
)

MISSING_TRANSACTIONS_TOTAL = Counter(
    'missing_transactions_total',
    'Total missing transactions found',
    ['processor']
)

DISCREPANCY_AMOUNT_TOTAL = Counter(
    'discrepancy_amount_total',
    'Total discrepancy amount in USD',
    ['processor']
)

# Technical Metrics
RECONCILIATION_DURATION_SECONDS = Histogram(
    'reconciliation_duration_seconds',
    'Time spent on reconciliation',
    ['processor'],
    buckets=[1, 5, 10, 30, 60, 300, 600, 1800]
)

API_REQUESTS_TOTAL = Counter(
    'api_requests_total',
    'Total API requests made',
    ['processor', 'endpoint', 'status']
)

API_REQUEST_DURATION_SECONDS = Histogram(
    'api_request_duration_seconds',
    'API request duration',
    ['processor', 'endpoint'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30]
)

DATABASE_OPERATIONS_TOTAL = Counter(
    'database_operations_total',
    'Total database operations',
    ['operation', 'status']
)

DATABASE_OPERATION_DURATION_SECONDS = Histogram(
    'database_operation_duration_seconds',
    'Database operation duration',
    ['operation'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5, 10]
)

# System Metrics
MEMORY_USAGE_BYTES = Gauge(
    'memory_usage_bytes',
    'Current memory usage in bytes'
)

ACTIVE_CONNECTIONS = Gauge(
    'active_database_connections',
    'Number of active database connections'
)

class MetricsCollector:
    """Centralized metrics collection for the reconciliation system."""
    
    def __init__(self, port: int = 8000):
        self.port = port
        self.server_started = False
    
    def start_metrics_server(self):
        """Start Prometheus metrics server."""
        if not self.server_started:
            try:
                # Validate port range for security
                if not (8000 <= self.port <= 9999):
                    raise ValueError(f"Invalid port {self.port}. Must be between 8000-9999")
                    
                start_http_server(self.port)
                self.server_started = True
                logger.info(f"Metrics server started on port {self.port}")
            except Exception as e:
                logger.error(f"Failed to start metrics server: {e}")
    
    def record_reconciliation_run(self, processor: str, status: str, duration: float):
        """Record reconciliation run metrics."""
        RECONCILIATION_RUNS_TOTAL.labels(processor=processor, status=status).inc()
        RECONCILIATION_DURATION_SECONDS.labels(processor=processor).observe(duration)
    
    def record_transactions_processed(self, processor: str, source: str, count: int):
        """Record transaction processing metrics."""
        TRANSACTIONS_PROCESSED_TOTAL.labels(processor=processor, source=source).inc(count)
    
    def record_missing_transactions(self, processor: str, count: int, amount: float):
        """Record missing transaction metrics."""
        MISSING_TRANSACTIONS_TOTAL.labels(processor=processor).inc(count)
        DISCREPANCY_AMOUNT_TOTAL.labels(processor=processor).inc(amount)
    
    def record_api_request(self, processor: str, endpoint: str, status: str, duration: float):
        """Record API request metrics."""
        API_REQUESTS_TOTAL.labels(processor=processor, endpoint=endpoint, status=status).inc()
        API_REQUEST_DURATION_SECONDS.labels(processor=processor, endpoint=endpoint).observe(duration)
    
    def record_database_operation(self, operation: str, status: str, duration: float):
        """Record database operation metrics."""
        DATABASE_OPERATIONS_TOTAL.labels(operation=operation, status=status).inc()
        DATABASE_OPERATION_DURATION_SECONDS.labels(operation=operation).observe(duration)
    
    def update_system_metrics(self, memory_bytes: int, db_connections: int):
        """Update system resource metrics."""
        MEMORY_USAGE_BYTES.set(memory_bytes)
        ACTIVE_CONNECTIONS.set(db_connections)

# Global metrics collector instance
metrics = MetricsCollector()

def track_duration(metric_name: str, labels: Dict[str, str] = None):
    """Decorator to track function execution duration."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                if metric_name == 'reconciliation':
                    processor = labels.get('processor', 'unknown') if labels else 'unknown'
                    metrics.record_reconciliation_run(processor, 'success', duration)
                elif metric_name == 'api_request':
                    processor = labels.get('processor', 'unknown') if labels else 'unknown'
                    endpoint = labels.get('endpoint', 'unknown') if labels else 'unknown'
                    metrics.record_api_request(processor, endpoint, 'success', duration)
                elif metric_name == 'database':
                    operation = labels.get('operation', 'unknown') if labels else 'unknown'
                    metrics.record_database_operation(operation, 'success', duration)
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                
                if metric_name == 'reconciliation':
                    processor = labels.get('processor', 'unknown') if labels else 'unknown'
                    metrics.record_reconciliation_run(processor, 'error', duration)
                elif metric_name == 'api_request':
                    processor = labels.get('processor', 'unknown') if labels else 'unknown'
                    endpoint = labels.get('endpoint', 'unknown') if labels else 'unknown'
                    metrics.record_api_request(processor, endpoint, 'error', duration)
                elif metric_name == 'database':
                    operation = labels.get('operation', 'unknown') if labels else 'unknown'
                    metrics.record_database_operation(operation, 'error', duration)
                
                raise e
        return wrapper
    return decorator

def get_system_metrics() -> Dict[str, Any]:
    """Get current system metrics for monitoring."""
    try:
        import psutil
        import os
        
        # Only allow metrics collection for current process
        current_pid = os.getpid()
        process = psutil.Process(current_pid)
        
        # Validate process belongs to current user
        if process.pid != current_pid:
            raise ValueError("Process validation failed")
            
        memory_info = process.memory_info()
        
        return {
            'memory_rss_bytes': memory_info.rss,
            'memory_vms_bytes': memory_info.vms,
            'cpu_percent': process.cpu_percent(),
            'open_files': len(process.open_files()),
            'threads': process.num_threads()
        }
    except Exception as e:
        logger.warning(f"Failed to collect system metrics: {e}")
        return {}