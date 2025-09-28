import os
import sys
import argparse
import structlog
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from models import Settings, ReportBundle, ReconciliationResult 
from data_fetcher import DataFetcher
from reconciliation_engine import ReconciliationEngine
from report_generator import ReportGenerator
from notification_service import NotificationService
from database_manager import DatabaseManager
from aws_manager import AWSManager

load_dotenv()

# CRITICAL: Configuration Initialization (Fail-Fast)
try:
    SETTINGS = Settings() 
except Exception as e:
    print(f"FATAL CONFIG ERROR: Missing critical environment variables. {e}")
    sys.exit(1)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level, structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level, structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(), structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict, logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()

class ReconciliationSystem:
    def __init__(self):
        # Dependency Injection
        self.data_fetcher = DataFetcher()
        self.reconciliation_engine = ReconciliationEngine()
        self.report_generator = ReportGenerator()
        self.notification_service = NotificationService()
        self.database_manager = DatabaseManager(db_url=SETTINGS.DB_URL)
        self.aws_manager = AWSManager(bucket_name=SETTINGS.AWS_BUCKET_NAME) 
        
        SETTINGS.REPORT_OUTPUT_DIR.mkdir(exist_ok=True)
        logger.info("Reconciliation system initialized", output_dir=str(SETTINGS.REPORT_OUTPUT_DIR))
    
    def run_daily_reconciliation(self, target_date: str = None, processors: list = None):
        if not target_date: target_date = datetime.now().strftime('%Y-%m-%d')
        if not processors: processors = ['stripe', 'paypal', 'square']
        
        overall_success = True
        # Resilience Loop
        for processor in processors:
            try:
                success = self._process_single_processor(processor, target_date)
                if not success: overall_success = False
            except Exception as e:
                logger.error("Processor reconciliation failed critically", processor=processor, error=str(e), exc_info=True)
                overall_success = False
        return overall_success
    
    def _process_single_processor(self, processor_name: str, target_date: str) -> bool:
        logger.info("Processing reconciliation", processor=processor_name, date=target_date)
        run_id = None
        report_bundle: ReportBundle = None 
        
        try:
            # 1. Start Audit Trail
            run_id = self.database_manager.create_reconciliation_run(target_date, processor_name)
            
            # 2. Fetch, Validate, Reconcile
            processor_txns = self.data_fetcher.fetch_processor_transactions(processor_name, target_date)
            internal_txns = self.data_fetcher.fetch_internal_transactions(target_date)
            processor_txns = self.reconciliation_engine.validate_transaction_data(processor_txns)
            internal_txns = self.reconciliation_engine.validate_transaction_data(internal_txns)
            reconciliation_result: ReconciliationResult = self.reconciliation_engine.reconcile_transactions(
                processor_txns, internal_txns, processor_name, target_date
            )
            
            # 3. Generate Reports
            report_bundle = self.report_generator.generate_all_reports(
                reconciliation_result, SETTINGS.REPORT_OUTPUT_DIR
            )
            
            # 4. Upload and Generate URL
            s3_key_or_path = self.aws_manager.upload_report(report_bundle.csv_path) 
            report_url = None
            if not Path(s3_key_or_path).is_absolute(): report_url = self.aws_manager.generate_presigned_url(s3_key_or_path)
            
            # 5. Persistence, Audit, Notification
            self.database_manager.update_reconciliation_run(run_id, status='completed', report_s3_key=s3_key_or_path, 
                                                           processor_transaction_count=len(processor_txns),
                                                           missing_transaction_count=reconciliation_result.summary.missing_transactions_count,
                                                           total_discrepancy_amount=reconciliation_result.summary.total_discrepancy_amount)
            self.database_manager.save_missing_transactions(run_id, reconciliation_result.missing_transactions)
            self.notification_service.send_reconciliation_notification(
                reconciliation_result, report_url, str(report_bundle.csv_path) if not report_url else None
            )
            self.database_manager.log_audit_event('reconciliation_completed', 'reconciliation_runs', run_id, new_values={'status': 'completed'})
            
            return True
            
        except Exception as e:
            # Failure Handling & Audit
            if run_id:
                try:
                    self.database_manager.update_reconciliation_run(run_id, status='failed')
                    self.database_manager.log_audit_event('reconciliation_failed', 'reconciliation_runs', run_id, new_values={'error': str(e)})
                except Exception: logger.error("Failed to update run status in DB during crash", run_id=run_id)
            logger.error("Processor reconciliation failed", processor=processor_name, error=str(e), exc_info=True)
            return False 

        finally: 
            # CRITICAL: ATOMIC LOCAL FILE CLEANUP
            if report_bundle and report_bundle.s3_key_or_path and not Path(report_bundle.s3_key_or_path).is_absolute():
                logger.debug("Starting atomic local file cleanup...")
                for path in [report_bundle.csv_path, report_bundle.json_path]:
                    try:
                        if path.exists(): path.unlink() 
                    except Exception as clean_e: logger.warning("Failed to clean up local file", path=str(path), error=str(clean_e))

def main():
    parser = argparse.ArgumentParser(description='FinTech Transaction Reconciliation System')
    parser.add_argument('--date', help='Target date (YYYY-MM-DD)', default=None)
    parser.add_argument('--processors', nargs='+', help='Processors to reconcile', 
                         default=['stripe', 'paypal', 'square'])
    
    args = parser.parse_args()
    
    try:
        system = ReconciliationSystem()
        success = system.run_daily_reconciliation(args.date, args.processors)
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error("Reconciliation system failed critically", error=str(e))
        sys.exit(1)

if __name__ == '__main__':
    main()