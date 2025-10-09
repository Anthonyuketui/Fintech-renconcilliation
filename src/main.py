"""
FinTech Transaction Reconciliation System - Main Entry Point

Orchestrates daily reconciliation workflows across payment processors.
Handles CLI arguments, logging setup, and coordinates service components.
"""

from __future__ import annotations
import argparse
import os
import sys
from datetime import date
from typing import List
import logging
import structlog
from dotenv import load_dotenv


from aws_manager import AWSManager
from data_fetcher import DataFetcher
from database_manager import DatabaseManager
from models import Settings
from notification_service import NotificationService
from reconciliation_engine import ReconciliationEngine
from report_generator import ReportGenerator


load_dotenv()


logger = structlog.get_logger()


try:
    SETTINGS = Settings()
except Exception as e:
    logger.error(
        "Failed to load environment settings. Check your .env file.", error=str(e)
    )
    sys.exit(1)


class ReconciliationSystem:
    """
    Coordinates reconciliation workflow across payment processors.
    
    This class orchestrates the complete reconciliation process including:
    - Data fetching from processor and internal APIs
    - Transaction reconciliation and discrepancy identification
    - Report generation in CSV and JSON formats
    - S3 upload with local fallback
    - Email notifications with severity-based alerting
    - Database audit logging and error tracking
    
    Each processor run is isolated to prevent cascading failures.
    """

    def __init__(self) -> None:
        """
        Initialize service components and create report directory.
        
        Sets up all required service instances:
        - AWSManager for S3 operations with local fallback
        - DatabaseManager for PostgreSQL audit trails
        - NotificationService for email/Slack alerts
        - ReportGenerator for CSV/JSON report creation
        - ReconciliationEngine for transaction matching
        """
        SETTINGS.REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.aws_manager = AWSManager(
            bucket_name=SETTINGS.AWS_BUCKET_NAME, region=SETTINGS.AWS_REGION
        )
        self.database_manager = DatabaseManager(settings=SETTINGS)
        self.notification_service = NotificationService()
        self.report_generator = ReportGenerator()
        self.reconciliation_engine = ReconciliationEngine()

    def _process_single_processor(
        self, processor_name: str, target_date_str: str
    ) -> bool:
        """
        Execute reconciliation workflow for a single processor.
        Errors are isolated and do not affect other processors.
        """
        logger.info(
            "Starting reconciliation", processor=processor_name, date=target_date_str
        )
        run_id = None
        target_date = date.fromisoformat(target_date_str)
        local_report_dir = (
            SETTINGS.REPORT_OUTPUT_DIR / f"{processor_name}_{target_date_str}"
        )
        csv_path = json_path = None
        s3_uploaded = False

        try:
            # Create audit record
            run_id = self.database_manager.create_reconciliation_run(
                target_date, processor_name
            )
            if run_id is None:
                logger.error(
                    "Could not start database audit record. Aborting processor run."
                )
                return False
            logger.debug("Database run record created", run_id=run_id)

            # Fetch transaction data
            fetcher = DataFetcher(
                processor_api_base_url=SETTINGS.PROCESSOR_API_BASE_URL,
                internal_api_base_url=SETTINGS.INTERNAL_API_BASE_URL,
                processor_name=processor_name,
            )
            proc_txns = fetcher.fetch_processor_data(run_date=target_date)
            internal_txns = fetcher.fetch_internal_data(
                processor_txns=proc_txns, run_date=target_date
            )
            fetcher.close()
            logger.info(
                "Data fetched successfully",
                proc_count=len(proc_txns),
                internal_count=len(internal_txns),
            )

            # Perform reconciliation
            result = self.reconciliation_engine.reconcile(
                proc_txns, internal_txns, target_date, processor_name
            )

            # Store results
            self.database_manager.store_reconciliation_result(run_id, result)
            logger.debug("Reconciliation metrics and details stored in DB.")

            # Generate reports
            csv_path, summary_text, json_path = (
                self.report_generator.generate_all_reports(result, local_report_dir)
            )
            logger.info(
                "Reports generated locally",
                csv_path=str(csv_path.as_posix()),
                json_path=str(json_path.as_posix()),
            )

            # Upload to S3
            s3_location = s3_key = None
            try:
                s3_location = self.aws_manager.upload_report(csv_path)
                s3_uploaded = self.aws_manager.is_s3_path(s3_location)

                if s3_uploaded:
                    self.database_manager.update_s3_report_key(run_id, s3_location)
                    # Store S3 key for notification service
                    s3_key = f"s3://{self.aws_manager.bucket_name}/{s3_location}"
                    logger.info("Report uploaded to S3", s3_key=s3_location)
                else:
                    local_path = s3_location.replace("file://", "")
                    self.database_manager.update_s3_report_key(run_id, local_path)
                    logger.info(
                        "Report stored locally (S3 unavailable)", local_path=local_path
                    )

            except Exception as e:
                logger.warning(
                    "S3 upload failed, reports available locally",
                    error=str(e),
                    local_path=str(csv_path.as_posix()),
                )
                s3_uploaded = False

            # Send notifications
            try:
                if s3_uploaded and s3_key:
                    notification_sent = (
                        self.notification_service.send_reconciliation_notification(
                            result,
                            target_date,
                            report_url=s3_key,
                            report_attachment=None,
                        )
                    )
                else:
                    notification_sent = (
                        self.notification_service.send_reconciliation_notification(
                            result,
                            target_date,
                            report_url=None,
                            report_attachment=str(csv_path),
                        )
                    )

                if notification_sent:
                    logger.info("Notification sent successfully")
                else:
                    logger.info("Notification skipped - email not configured")
            except Exception as e:
                logger.warning("Failed to send notification", error=str(e))

            logger.info(
                "Reconciliation complete",
                processor=processor_name,
                s3_uploaded=s3_uploaded,
                local_path=str(csv_path.as_posix()),
            )
            return True

        except Exception as e:
            error_msg = str(e)[:500]
            logger.error(
                "Reconciliation failed for processor",
                processor=processor_name,
                error=error_msg,
                exc_info=True,
            )
            if run_id:
                self.database_manager.update_reconciliation_status(
                    run_id, "failed", str(e)
                )


            try:
                self.notification_service.send_failure_alert(
                    processor_name, target_date_str, run_id or "unknown", error_msg
                )
            except Exception as alert_err:
                logger.warning("Could not send failure alert", error=str(alert_err))

            return False

        finally:
            # Clean up local files after successful S3 upload
            cleanup_enabled = os.getenv('CLEANUP_LOCAL_REPORTS', 'false').lower() == 'true'
            logger.debug("Cleanup check", cleanup_enabled=cleanup_enabled, s3_uploaded=s3_uploaded)
            
            if cleanup_enabled and s3_uploaded:
                cleanup_paths = [csv_path, json_path]
                for path in cleanup_paths:
                    if path and path.exists():
                        try:
                            path.unlink()
                            logger.debug("Deleted local file after S3 upload", path=str(path.as_posix()))
                        except Exception as e:
                            logger.warning("Failed to delete file", path=str(path.as_posix()), error=str(e))

                if local_report_dir.is_dir():
                    try:
                        local_report_dir.rmdir()
                        logger.debug("Cleaned up report directory after S3 upload")
                    except OSError:
                        pass
            else:
                logger.info("Local reports preserved", directory=str(local_report_dir.as_posix()))

    def run(self, target_date: str, processors: List[str]) -> None:
        """
        Run reconciliation for all specified processors.
        
        Args:
            target_date: ISO format date string (YYYY-MM-DD)
            processors: List of processor names to reconcile
            
        Each processor is processed independently to prevent
        failures in one processor from affecting others.
        """
        overall_success = True
        for processor in processors:
            if not self._process_single_processor(processor, target_date):
                overall_success = False

        if overall_success:
            logger.info("All specified processors reconciled successfully.")
        else:
            logger.warning("One or more processor reconciliations failed. Check logs.")


def setup_logging() -> None:
    """
    Configure structured JSON logging for production observability.
    
    Sets up structlog with:
    - Timestamp formatting
    - Log level inclusion
    - Stack trace rendering
    - Exception info formatting
    - JSON output for log aggregation
    """
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stdout)


if __name__ == "__main__":
    setup_logging()

    parser = argparse.ArgumentParser(
        description="FinTech Transaction Reconciliation System.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --date 2024-05-15 --processors stripe
  python main.py --date 2024-05-15 --processors stripe paypal square
        """,
    )
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Target date for reconciliation (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--processors",
        type=str,
        nargs="+",
        default=["stripe", "paypal", "square"],
        help="List of processors to reconcile (e.g., stripe paypal). Defaults to all processors.",
    )

    args = parser.parse_args()


    try:
        date.fromisoformat(args.date)
    except ValueError:
        logger.error("Invalid date format. Use YYYY-MM-DD.", provided_date=args.date)
        sys.exit(1)

    system = ReconciliationSystem()
    system.run(args.date, args.processors)
