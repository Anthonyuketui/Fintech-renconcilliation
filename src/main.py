"""
main.py - FIXED VERSION

Entry point and orchestrator for the FinTech Transaction Reconciliation System.

This script parses CLI arguments, sets up structured logging, initializes all service classes,
and manages the resilient, isolated workflow for each payment processor. It ensures that
each processor's reconciliation run is atomic and failures are handled gracefully.
"""

from __future__ import annotations
import argparse
import sys
from datetime import date
from typing import List
import logging
import structlog
from dotenv import load_dotenv

# Import all service modules
from aws_manager import AWSManager
from data_fetcher import DataFetcher
from database_manager import DatabaseManager
from models import Settings
from notification_service import NotificationService
from reconciliation_engine import ReconciliationEngine
from report_generator import ReportGenerator
# Load environment variables as early as possible for configuration
load_dotenv()
# Set up structured logging for observability and debugging
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

    This class initializes all dependencies and coordinates the reconciliation,
    reporting, and notification steps for each processor. Each processor run is
    isolated to prevent cascading failures.
    """

    def __init__(self):
        """
        Initialize all service components using Dependency Injection.

        Ensures the report output directory exists and sets up all service classes.
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
        Executes the full, isolated reconciliation workflow for one processor.

        This method implements the Isolated Failure Principle: errors in one processor's run
        do not affect others. All steps (audit, data fetch, reconciliation, reporting, archival,
        notification) are performed in sequence, with robust error handling.
        """
        logger.info(
            "Starting reconciliation", processor=processor_name, date=target_date_str
        )
        run_id = None
        target_date = date.fromisoformat(target_date_str)
        local_report_dir = (
            SETTINGS.REPORT_OUTPUT_DIR / f"{processor_name}_{target_date_str}"
        )
        csv_path = None
        json_path = None
        s3_uploaded = False

        try:
            # Step 1: Audit Start
            run_id = self.database_manager.create_reconciliation_run(
                target_date, processor_name
            )
            if run_id is None:
                logger.error(
                    "Could not start database audit record. Aborting processor run."
                )
                return False

            logger.debug("Database run record created", run_id=run_id)

            # Step 2: Data Acquisition
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

            # Step 3: Core Logic
            result = self.reconciliation_engine.reconcile(
                proc_txns, internal_txns, target_date, processor_name
            )

            # Step 4: Store Metrics & Missing Transactions
            self.database_manager.store_reconciliation_result(run_id, result)
            logger.debug("Reconciliation metrics and details stored in DB.")

            # Step 5: Reporting
            csv_path, summary_text, json_path = (
                self.report_generator.generate_all_reports(result, local_report_dir)
            )
            logger.info(
                "Reports generated locally",
                csv_path=str(csv_path.as_posix()),
                json_path=str(json_path.as_posix()),
            )

            # Step 6: Archival (Optional - AWS S3)
            s3_location = None
            presigned_url = None
            try:
                s3_location = self.aws_manager.upload_report(csv_path)

                # FIXED: Use the helper method to properly detect S3 vs local
                s3_uploaded = self.aws_manager.is_s3_path(s3_location)

                if s3_uploaded:
                    # It's in S3
                    self.database_manager.update_s3_report_key(run_id, s3_location)
                    presigned_url = self.aws_manager.generate_presigned_url(s3_location)
                    logger.info("Report uploaded to S3", s3_key=s3_location)
                else:
                    # It's local storage (has file:// prefix)
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

            # Step 7: Communication (Optional - Email)
            try:
                # Pass the correct parameters based on storage type
                if s3_uploaded and presigned_url:
                    notification_sent = (
                        self.notification_service.send_reconciliation_notification(
                            result,
                            target_date,
                            report_url=presigned_url,
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

            # Try to send failure alert (optional)
            try:
                self.notification_service.send_failure_alert(
                    processor_name, target_date_str, error_msg
                )
            except Exception as alert_err:
                logger.warning("Could not send failure alert", error=str(alert_err))

            return False

        finally:
            # Only delete local files if they were successfully uploaded to S3
            if s3_uploaded:
                if csv_path and csv_path.exists():
                    try:
                        csv_path.unlink()
                        logger.debug(
                            "Deleted local CSV after S3 upload",
                            path=str(csv_path.as_posix()),
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to delete CSV file",
                            path=str(csv_path.as_posix()),
                            error=str(e),
                        )

                if json_path and json_path.exists():
                    try:
                        json_path.unlink()
                        logger.debug(
                            "Deleted local JSON after S3 upload",
                            path=str(json_path.as_posix()),
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to delete JSON file",
                            path=str(json_path.as_posix()),
                            error=str(e),
                        )

                if local_report_dir and local_report_dir.is_dir():
                    try:
                        local_report_dir.rmdir()
                        logger.debug("Cleaned up report directory after S3 upload")
                    except OSError:
                        pass  # Directory not empty or doesn't exist
            else:
                logger.info(
                    "Local reports preserved",
                    directory=str(local_report_dir.as_posix()),
                )

    def run(self, target_date: str, processors: List[str]):
        """
        Runs the reconciliation workflow for all specified processors.

        Logs overall success or failure at the end of the run.
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
    Configures structured logging for production readiness.

    Uses structlog for JSON logs, suitable for monitoring and debugging.
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

    # Validate date format before proceeding
    try:
        date.fromisoformat(args.date)
    except ValueError:
        logger.error("Invalid date format. Use YYYY-MM-DD.", provided_date=args.date)
        sys.exit(1)

    system = ReconciliationSystem()
    system.run(args.date, args.processors)
