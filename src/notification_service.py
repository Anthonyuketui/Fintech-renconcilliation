"""
Automated notification system for reconciliation results.

Handles email and Slack notifications with severity-based alerting.
Adapts thresholds based on transaction volume for accurate risk assessment.
"""

import os
import smtplib
import ssl
import html
from datetime import date
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional
import structlog
import requests
import boto3
from botocore.exceptions import ClientError
from models import ReconciliationResult

logger = structlog.get_logger()



class NotificationService:
    """Manages email and Slack notifications for reconciliation results."""

    def __init__(self) -> None:
        # Check if using SES or SMTP
        self.use_ses = os.getenv("USE_SES", "false").lower() == "true"
        
        if self.use_ses:
            # AWS SES configuration
            self.ses_client = boto3.client('ses', region_name=os.getenv("SES_REGION", "us-east-1"))
            self.sender_email = os.getenv("SENDER_EMAIL")
        else:
            # SMTP configuration
            self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
            try:
                self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
            except ValueError:
                self.smtp_port = 587
            self.email_user = os.getenv("EMAIL_USER")
            self.email_password = os.getenv("EMAIL_PASSWORD")
            
        self.operations_email = os.getenv("OPERATIONS_EMAIL", "operations@fintech.com")

        # Slack integration (optional)
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")


    def _send_email(self, message: MIMEMultipart) -> bool:
        """Send email via SES or SMTP."""
        if self.use_ses:
            return self._send_email_ses(message)
        else:
            return self._send_email_smtp(message)
    
    def _send_email_ses(self, message: MIMEMultipart) -> bool:
        """Send email via AWS SES."""
        if not self.sender_email:
            logger.warning("Sender email not configured for SES, skipping email send")
            return False

        try:
            response = self.ses_client.send_raw_email(
                Source=self.sender_email,
                Destinations=[self.operations_email],
                RawMessage={'Data': message.as_string()}
            )
            logger.info("Email sent successfully via SES", 
                       subject=message["Subject"], 
                       message_id=response['MessageId'])
            return True
        except ClientError as e:
            logger.error("Failed to send email via SES", 
                        error=str(e), 
                        subject=message["Subject"])
            return False
        except Exception as e:
            logger.error("Unexpected error sending email via SES", 
                        error=str(e), 
                        subject=message["Subject"])
            return False

    def _send_email_smtp(self, message: MIMEMultipart) -> bool:
        """Send email via SMTP with SSL or STARTTLS."""
        if not self.email_user or not self.email_password:
            logger.warning("Email credentials not configured, skipping email send")
            return False

        # SMTP server configurations with fallbacks
        smtp_configs = [
            ("smtp.gmail.com", 465),
            (self.smtp_server, self.smtp_port),
            ("smtp.gmail.com", 587),
            ("smtp-mail.outlook.com", 587)
        ]
        
        for smtp_server, smtp_port in smtp_configs:
            try:
                logger.debug(f"Attempting SMTP connection to {smtp_server}:{smtp_port}")
                
                if smtp_port == 465:
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(
                        smtp_server, smtp_port, context=context, timeout=10
                    ) as server:
                        server.login(self.email_user, self.email_password)
                        server.sendmail(
                            self.email_user, self.operations_email, message.as_string()
                        )
                else:
                    context = ssl.create_default_context()
                    with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                        server.starttls(context=context)
                        server.login(self.email_user, self.email_password)
                        server.sendmail(
                            self.email_user, self.operations_email, message.as_string()
                        )

                logger.info("Email sent successfully via SMTP", 
                           subject=message["Subject"], 
                           server=f"{smtp_server}:{smtp_port}")
                return True
                
            except Exception as e:
                logger.warning(
                    f"SMTP attempt failed for {smtp_server}:{smtp_port}", 
                    error=str(e)
                )
                continue
        
        logger.error(
            "All SMTP attempts failed", 
            subject=message["Subject"],
            attempted_servers=[f"{s}:{p}" for s, p in smtp_configs]
        )
        return False

    def _send_slack(self, payload: dict) -> bool:
        """Send Slack notification via webhook."""
        if not self.slack_webhook_url:
            logger.warning(
                "Slack webhook URL not configured, skipping Slack notification."
            )
            return False
        try:
            response = requests.post(self.slack_webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Slack notification sent successfully")
            return True
        except Exception as e:
            logger.error("Failed to send Slack notification", error=str(e))
            return False


    def send_reconciliation_notification(
        self,
        reconciliation_result: ReconciliationResult,
        reconciliation_date: date,
        report_url: Optional[str] = None,
        report_attachment: Optional[str] = None,
    ) -> bool:
        """Send daily reconciliation summary notification."""
        severity = self._determine_severity(reconciliation_result)
        try:
            # Generate presigned URL if S3 key provided
            download_url = None
            if report_url and report_url.startswith('s3://'):
                download_url = self._generate_presigned_url(report_url)
                if not download_url:
                    logger.warning("Presigned URL generation failed, email will not include download link",
                                 s3_url=report_url)
            elif report_url:
                download_url = report_url
                
            message = self._create_email_message(
                reconciliation_result,
                reconciliation_date,
                severity,
                download_url,
                report_attachment,
            )
            return self._send_email(message)
        except Exception as e:
            logger.error(
                "Failed to construct reconciliation notification",
                processor=reconciliation_result.processor,
                error=str(e),
            )
            return False

    def send_failure_alert(
        self, processor: str, date: str, run_id: str, error_message: str
    ) -> bool:
        """Send critical failure alert for reconciliation errors."""
        try:
            message = MIMEMultipart()
            message["From"] = self.sender_email if self.use_ses else self.email_user
            message["To"] = self.operations_email
            message["Subject"] = (
                f"🚨 CRITICAL: Reconciliation Failed - {processor} - {date}"
            )
            body = f"""
            <html><body style="font-family: Arial, sans-serif;">
                <div style="background:#dc3545;color:white;padding:20px;border-radius:5px;">
                    <h2>⚠️ Reconciliation System Failure</h2>
                    <p><strong>Run ID:</strong> {run_id}</p>
                    <p><strong>Processor:</strong> {processor.upper()}</p>
                    <p><strong>Date:</strong> {date}</p>
                </div>
                <div style="background:#f8f9fa;padding:15px;margin-top:20px;border-radius:5px;">
                    <h3>Error Details</h3>
                    <pre>{html.escape(error_message)}</pre>
                </div>
            </body></html>
            """
            message.attach(MIMEText(body, "html"))
            return self._send_email(message)
        except Exception as e:
            logger.error(
                "Failed to construct failure alert", processor=processor, error=str(e)
            )
            return False


    def _determine_severity(self, result: ReconciliationResult) -> str:
        """Determine alert severity based on discrepancy thresholds."""
        summary = result.summary

        total_tx = summary.processor_transactions or 1
        total_vol = float(summary.total_volume_processed or 1)
        missing_pct = summary.missing_transactions_count / total_tx
        amount_pct = float(summary.total_discrepancy_amount) / total_vol
        discrepancy = max(missing_pct, amount_pct)
        amount_abs = float(summary.total_discrepancy_amount)

        # Adaptive thresholds based on transaction volume
        if total_tx < 10_000:
            low, medium, high, critical = 0.02, 0.05, 0.10, 0.20
        elif total_tx < 100_000:
            low, medium, high, critical = 0.005, 0.02, 0.05, 0.10
        else:
            low, medium, high, critical = 0.001, 0.003, 0.005, 0.01


        if discrepancy > critical or amount_abs > 100_000:
            severity = "critical"
        elif discrepancy > high:
            severity = "high"
        elif discrepancy > medium:
            severity = "medium"
        else:
            severity = "low"

        logger.info(
            "Severity determined",
            severity=severity.upper(),
            missing_pct=f"{missing_pct:.2%}",
            amount_pct=f"{amount_pct:.2%}",
            amount_abs=f"${amount_abs:,.2f}",
            total_tx=f"{total_tx:,}",
        )
        return severity


    def _create_email_message(
        self,
        result: ReconciliationResult,
        reconciliation_date: date,
        severity: str,
        report_url: Optional[str] = None,
        report_attachment: Optional[str] = None,
    ) -> MIMEMultipart:
        """Create email message with summary and attachments."""
        message = MIMEMultipart()
        message["From"] = self.sender_email if self.use_ses else self.email_user
        message["To"] = self.operations_email

        severity_indicator = {
            "critical": "🚨 CRITICAL",
            "high": "⚠️ HIGH PRIORITY",
            "medium": "📊 ATTENTION",
            "low": "✅ INFO",
        }

        message["Subject"] = (
            f"{severity_indicator.get(severity, '📊')} "
            f"Daily Reconciliation Report - {result.processor} - {reconciliation_date}"
        )

        body = self._generate_email_body(
            result, reconciliation_date, severity, report_url
        )
        message.attach(MIMEText(body, "html"))

        if report_attachment and self._is_safe_path(report_attachment) and Path(report_attachment).exists():
            self._attach_report(message, report_attachment)

        return message

    def _generate_email_body(
        self,
        result: ReconciliationResult,
        reconciliation_date: date,
        severity: str,
        report_url: Optional[str] = None,
    ) -> str:
        """Generate HTML email body for reconciliation summary."""
        color_map = {
            "critical": "#dc3545",
            "high": "#fd7e14",
            "medium": "#ffc107",
            "low": "#28a745",
        }
        color = color_map.get(severity, "#6c757d")

        missing_count = result.summary.missing_transactions_count
        discrepancy_amount = result.summary.total_discrepancy_amount
        recommendations = self._generate_email_recommendations(result, severity)

        download_button = (
            f'<div style="margin:20px 0;"><a href="{report_url}" '
            f'style="background:#007bff;color:white;padding:10px 20px;'
            f'text-decoration:none;border-radius:5px;">Download Full Report</a></div>'
            if report_url
            else ""
        )

        # Escape data to prevent XSS
        processor_safe = html.escape(str(result.processor).upper())
        date_safe = html.escape(str(reconciliation_date))
        severity_safe = html.escape(severity.upper())

        return f"""
        <html><body style="font-family: Arial, sans-serif;">
            <div style="background:{color};color:white;padding:15px;border-radius:5px;">
                <h2>Daily Transaction Reconciliation Report</h2>
                <p><strong>Processor:</strong> {processor_safe} |
                   <strong>Date:</strong> {date_safe} |
                   <strong>Severity:</strong> {severity_safe}</p>
            </div>
            <div style="background:#f8f9fa;padding:15px;border-radius:5px;margin:15px 0;">
                <h3>Summary</h3>
                <p><strong>Processor Transactions:</strong> {result.summary.processor_transactions:,}</p>
                <p><strong>Internal Matches:</strong> {result.summary.internal_transactions:,}</p>
                <p><strong>Missing Transactions:</strong> {missing_count:,}</p>
                <p><strong>Discrepancy Amount:</strong> ${discrepancy_amount:,.2f}</p>
            </div>
            {recommendations}
            {download_button}
            <div style="color:#6c757d;font-size:12px;margin-top:30px;">
                <p>This is an automated notification from the FinTech Reconciliation System.</p>
            </div>
        </body></html>
        """

    def _generate_email_recommendations(
        self, result: ReconciliationResult, severity: str
    ) -> str:
        """Generate severity-based action recommendations."""
        recs = {
            "critical": [
                "🚨 Immediate action required",
                "Contact payment processor",
                "Escalate to compliance",
            ],
            "high": ["⚠️ Review within 2 hours", "Contact processor if needed"],
            "medium": [
                "📊 Review during business hours",
                "Verify account configurations",
            ],
            "low": ["✅ No immediate action required", "Archive report"],
        }
        items = "<br>".join(recs.get(severity, []))
        return (
            f'<div style="background:#fff3cd;padding:15px;border-radius:5px;margin:15px 0;">'
            f'<h3>Actions</h3>{items}</div>'
        )

    def _attach_report(self, message: MIMEMultipart, file_path: str):
        """Attach CSV report file to email."""
        # Validate file path for security
        if not self._is_safe_path(file_path):
            logger.error("Unsafe file path detected", file_path=file_path)
            return

        try:
            with open(file_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition", f"attachment; filename={Path(file_path).name}"
            )
            message.attach(part)
        except Exception as e:
            logger.warning("Failed to attach report", file_path=file_path, error=str(e))

    def _generate_presigned_url(self, s3_url: str) -> Optional[str]:
        """Generate presigned URL for S3 object download."""
        try:
            # Parse S3 URL: s3://bucket/key
            if not s3_url.startswith('s3://'):
                logger.debug("URL is not S3 format, returning as-is", url=s3_url)
                return s3_url
                
            s3_path = s3_url[5:]  # Remove 's3://'
            if '/' not in s3_path:
                logger.error("Invalid S3 URL format", s3_url=s3_url)
                return None
                
            bucket, key = s3_path.split('/', 1)
            logger.debug("Parsing S3 URL", bucket=bucket, key=key)
            
            # Use same region as environment
            region = os.getenv("AWS_REGION", "us-east-1")
            logger.debug("Creating S3 client", region=region)
            
            s3_client = boto3.client('s3', region_name=region)
            
            # Test if object exists first
            try:
                s3_client.head_object(Bucket=bucket, Key=key)
                logger.debug("S3 object exists", bucket=bucket, key=key)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.error("S3 object not found", bucket=bucket, key=key)
                    return None
                else:
                    logger.error("Error checking S3 object", bucket=bucket, key=key, error=str(e))
                    return None
            
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=86400  # 24 hours
            )
            
            logger.info("Generated presigned URL for S3 download", 
                       bucket=bucket, key=key, expires_in="24h", 
                       url_length=len(presigned_url))
            return presigned_url
            
        except Exception as e:
            logger.error("Failed to generate presigned URL", 
                        s3_url=s3_url, error=str(e), error_type=type(e).__name__)
            return None

    def _is_safe_path(self, file_path: str) -> bool:
        """Validate file path to prevent directory traversal."""
        try:
            import os
            # Normalize path and check for traversal attempts
            normalized = os.path.normpath(file_path)
            if ".." in normalized or normalized.startswith("/"):
                return False
                
            # Only allow files in safe directories
            safe_patterns = ["reports", "local_reports", "Sample_Output", "tmp"]
            return any(pattern in normalized for pattern in safe_patterns)
        except Exception:
            return False
