"""
main.py: The primary orchestrator for the FinTech Transaction Reconciliation System.

Handles CLI arguments, sets up structured logging, initializes all service classes,
and manages the resilient, isolated workflow for each payment processor.
"""

from __future__ import annotations
import argparse
import os
import sys
import logging
from datetime import date
from typing import List
from pathlib import Path

# Setup environment variables early
from dotenv import load_dotenv
load_dotenv()

# Setup structured logging
import structlog
logger = structlog.get_logger()

# FIXED: Removed 'src.' prefix from all imports
from aws_manager import AWSManager
from data_fetcher import DataFetcher
from database_manager import DatabaseManager
from notification_service import NotificationService
from reconciliation_engine import ReconciliationEngine
from report_generator import ReportGenerator
from models import Settings, ReconciliationResult

# Load settings from environment
try:
    SETTINGS = Settings()
except Exception as e:
    logger.error("Failed to load environment settings. Check your .env file.", error=str(e))
    sys.exit(1)


class ReconciliationSystem:
    """Manages the end-to-end reconciliation process."""

    def __init__(self):
        """Initializes all service components using Dependency Injection."""
        SETTINGS.REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.aws_manager = AWSManager(
            bucket_name=SETTINGS.AWS_BUCKET_NAME,
            region=SETTINGS.AWS_REGION
        )
        self.database_manager = DatabaseManager(settings=SETTINGS)
        self.notification_service = NotificationService()
        self.report_generator = ReportGenerator()
        self.reconciliation_engine = ReconciliationEngine()

    def _process_single_processor(self, processor_name: str, target_date_str: str) -> bool:
        """
        Executes the full, isolated reconciliation workflow for one processor.
        Implements the Isolated Failure Principle.
        """
        logger.info("Starting reconciliation", processor=processor_name, date=target_date_str)
        run_id = None
        target_date = date.fromisoformat(target_date_str)
        local_report_dir = SETTINGS.REPORT_OUTPUT_DIR / f"{processor_name}_{target_date_str}"
        csv_path = None
        json_path = None
        s3_upload_success = False
        try:
            # 1. Audit Start
            run_id = self.database_manager.create_reconciliation_run(target_date, processor_name)
            if run_id is None:
                logger.error("Could not start database audit record. Aborting processor run.")
                return False

            logger.debug("Database run record created", run_id=run_id)

            # 2. Data Acquisition
            fetcher = DataFetcher(
                processor_api_base_url=SETTINGS.PROCESSOR_API_BASE_URL,
                internal_api_base_url=SETTINGS.INTERNAL_API_BASE_URL,
                processor_name=processor_name
            )
            proc_txns = fetcher.fetch_processor_data(run_date=target_date)
            internal_txns = fetcher.fetch_internal_data(run_date=target_date)
            fetcher.close()

            logger.info("Data fetched successfully",
                        proc_count=len(proc_txns),
                        internal_count=len(internal_txns))

            # 3. Core Logic
            result = self.reconciliation_engine.reconcile(
                proc_txns, internal_txns, target_date, processor_name
            )

            # 4. Store Metrics & Missing Transactions
            self.database_manager.store_reconciliation_result(run_id, result)
            logger.debug("Reconciliation metrics and details stored in DB.")

            # 5. Reporting
            csv_path, summary_text, json_path = self.report_generator.generate_all_reports(
                result, local_report_dir
            )
            logger.info("Reports generated locally", csv_path=str(csv_path), json_path=str(json_path))

            # 6. Archival & Audit
            s3_key = self.aws_manager.upload_report(csv_path)
            s3_upload_success = s3_key is not None and not str(csv_path) in str(s3_key)
            
            if s3_upload_success:
                self.database_manager.update_s3_report_key(run_id, s3_key)
                presigned_url = self.aws_manager.generate_presigned_url(s3_key)
            else:
                # S3 upload failed or not configured - keep local reports
                self.database_manager.update_s3_report_key(run_id, str(csv_path))
                presigned_url = None
                logger.info("Reports kept locally (S3 not configured)", 
                           csv_path=str(csv_path), json_path=str(json_path))

            # 7. Communication - FIXED: Added target_date parameter
            self.notification_service.send_reconciliation_notification(
                result, target_date, presigned_url, report_attachment=str(csv_path)
            )

            logger.info("Reconciliation complete and notification sent", processor=processor_name)
            return True

        except Exception as e:
            error_msg = str(e)[:500]
            logger.error("Reconciliation failed for processor", processor=processor_name, error=error_msg, exc_info=True)
            if run_id:
                self.database_manager.update_reconciliation_status(run_id, 'failed', str(e))
            self.notification_service.send_failure_alert(processor_name, target_date_str, error_msg)
            return False

        finally:
            # Only cleanup if S3 upload was successful
            if s3_upload_success:
                if csv_path and hasattr(csv_path, "exists") and csv_path.exists():
                    try:
                        csv_path.unlink()
                        logger.info("Deleted local CSV after S3 upload", path=str(csv_path))
                    except Exception as e:
                        logger.warning("Failed to delete CSV file", path=str(csv_path), error=str(e))

                if json_path and hasattr(json_path, "exists") and json_path.exists():
                    try:
                        json_path.unlink()
                        logger.info("Deleted local JSON after S3 upload", path=str(json_path))
                    except Exception as e:
                        logger.warning("Failed to delete JSON file", path=str(json_path), error=str(e))

                if local_report_dir and local_report_dir.is_dir():
                    try:
                        local_report_dir.rmdir()
                    except OSError:
                        pass  # Directory not empty or doesn't exist

    def run(self, target_date: str, processors: List[str]):
        """Runs the reconciliation for all specified processors."""
        overall_success = True
        for processor in processors:
            if not self._process_single_processor(processor, target_date):
                overall_success = False

        if overall_success:
            logger.info("All specified processors reconciled successfully.")
        else:
            logger.warning("One or more processor reconciliations failed. Check logs.")


def setup_logging():
    """Configures structured logging for production readiness."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        stream=sys.stdout
    )


if __name__ == "__main__":
    setup_logging()

    parser = argparse.ArgumentParser(
        description="FinTech Transaction Reconciliation System.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --date 2024-05-15 --processors stripe
  python main.py --date 2024-05-15 --processors stripe paypal square
        """
    )
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Target date for reconciliation (YYYY-MM-DD). Defaults to today."
    )
    parser.add_argument(
        "--processors",
        type=str,
        nargs='+',
        required=True,
        help="List of processors to reconcile (e.g., stripe paypal)."
    )

    args = parser.parse_args()

    # Validate date format
    try:
        date.fromisoformat(args.date)
    except ValueError:
        logger.error("Invalid date format. Use YYYY-MM-DD.", provided_date=args.date)
        sys.exit(1)

    system = ReconciliationSystem()
    system.run(args.date, args.processors)