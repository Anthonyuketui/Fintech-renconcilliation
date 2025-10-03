"""
Entry point and orchestrator for the FinTech Transaction Reconciliation System.

This script parses CLI arguments, sets up structured logging, initializes service
classes, and manages the reconciliation workflow for each payment processor.
Each processor run is isolated to ensure failures are handled gracefully.
"""

from __future__ import annotations
import argparse
import sys
from datetime import date
from typing import List
import logging
import structlog
from dotenv import load_dotenv

# Import service modules
from aws_manager import AWSManager
from data_fetcher import DataFetcher
from database_manager import DatabaseManager
from models import Settings
from notification_service import NotificationService
from reconciliation_engine import ReconciliationEngine
from report_generator import ReportGenerator

# Load environment variables early
load_dotenv()

# Initialize structured logger
logger = structlog.get_logger()

# Load application settings from environment or .env file
try:
    SETTINGS = Settings()
except Exception as e:
    logger.error(
        "Failed to load environment settings. Check your .env file.", error=str(e)
    )
    sys.exit(1)


class ReconciliationSystem:
    """
    Manages the end-to-end reconciliation workflow for all payment processors.

    Initializes dependencies and coordinates reconciliation, reporting, and notifications.
    Each processor run is isolated to prevent cascading failures.
    """

    def __init__(self):
        """Initialize all service components and ensure report directory exists."""
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
        Execute the reconciliation workflow for one processor.

        Implements isolated failure principle: errors in one processor do not affect others.
        Workflow includes auditing, data fetch, reconciliation, reporting, archival, and notifications.
        """
        logger.info(
            "Starting reconciliation", processor=processor_name, date=target_date_str
        )
        run_id = None
        target_date = date.fromisoformat(target_date_str)
        local_report_dir = SETTINGS.REPORT_OUTPUT_DIR / f"{processor_name}_{target_date_str}"
        csv_path = json_path = None
        s3_uploaded = False

        try:
            # Step 1: Audit Start
            run_id = self.database_manager.create_reconciliation_run(target_date, processor_name)
            if run_id is None:
                logger.error("Could not start database audit record. Aborting processor run.")
                return False
            logger.debug("Database run record created", run_id=run_id)

            # Step 2: Data Acquisition
            fetcher = DataFetcher(
                processor_api_base_url=SETTINGS.PROCESSOR_API_BASE_URL,
                internal_api_base_url=SETTINGS.INTERNAL_API_BASE_URL,
                processor_name=processor_name,
            )
            proc_txns = fetcher.fetch_processor_data(run_date=target_date)
            internal_txns = fetcher.fetch_internal_data(processor_txns=proc_txns, run_date=target_date)
            fetcher.close()
            logger.info("Data fetched successfully", proc_count=len(proc_txns), internal_count=len(internal_txns))

            # Step 3: Core Reconciliation
            result = self.reconciliation_engine.reconcile(proc_txns, internal_txns, target_date, processor_name)

            # Step 4: Store metrics and missing transactions
            self.database_manager.store_reconciliation_result(run_id, result)
            logger.debug("Reconciliation metrics and details stored in DB.")

            # Step 5: Reporting
            csv_path, summary_text, json_path = self.report_generator.generate_all_reports(result, local_report_dir)
            logger.info(
                "Reports generated locally",
                csv_path=str(csv_path.as_posix()),
                json_path=str(json_path.as_posix()),
            )

            # Step 6: Archival (AWS S3)
            s3_location = presigned_url = None
            try:
                s3_location = self.aws_manager.upload_report(csv_path)
                s3_uploaded = self.aws_manager.is_s3_path(s3_location)

                if s3_uploaded:
                    self.database_manager.update_s3_report_key(run_id, s3_location)
                    presigned_url = self.aws_manager.generate_presigned_url(s3_location)
                    logger.info("Report uploaded to S3", s3_key=s3_location)
                else:
                    local_path = s3_location.replace("file://", "")
                    self.database_manager.update_s3_report_key(run_id, local_path)
                    logger.info("Report stored locally (S3 unavailable)", local_path=local_path)

            except Exception as e:
                logger.warning(
                    "S3 upload failed, reports available locally",
                    error=str(e),
                    local_path=str(csv_path.as_posix()),
                )
                s3_uploaded = False

            # Step 7: Communication (Email notifications)
            try:
                if s3_uploaded and presigned_url:
                    notification_sent = self.notification_service.send_reconciliation_notification(
                        result, target_date, report_url=presigned_url, report_attachment=None
                    )
                else:
                    notification_sent = self.notification_service.send_reconciliation_notification(
                        result, target_date, report_url=None, report_attachment=str(csv_path)
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
                self.database_manager.update_reconciliation_status(run_id, "failed", str(e))

            # Attempt to send failure alert
            try:
                self.notification_service.send_failure_alert(processor_name, target_date_str, error_msg)
            except Exception as alert_err:
                logger.warning("Could not send failure alert", error=str(alert_err))

            return False

        finally:
            # Cleanup local files if successfully uploaded to S3
            if s3_uploaded:
                for path in [csv_path, json_path]:
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

    def run(self, target_date: str, processors: List[str]):
        """
        Run reconciliation workflow for all specified processors.

        Logs overall success or failure after completion.
        """
        overall_success = True
        for processor in processors:
            if not self._process_single_processor(processor, target_date):
                overall_success = False

        if overall_success:
            logger.info("All specified processors reconciled successfully.")
        else:
            logger.warning("One or more processor reconciliations failed. Check logs.")


def setup_logging():
    """
    Configure structured logging for monitoring and debugging.

    Uses structlog to produce JSON-formatted logs.
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
        required=True,
        help="List of processors to reconcile (e.g., stripe paypal).",
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
