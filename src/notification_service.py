"""
notification_service.py - CORRECTED VERSION
Sends email notifications for reconciliation results with severity-based alerting.
"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import structlog
from typing import Optional
from pathlib import Path
from datetime import date
from models import ReconciliationResult

logger = structlog.get_logger()


class NotificationService:
    """Handles email notifications for reconciliation results."""
    
    def __init__(self):
        """Initialize notification service with environment configuration."""
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.email_user = os.getenv('EMAIL_USER')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.operations_email = os.getenv('OPERATIONS_EMAIL', 'operations@fintech.com')

        # Notification severity levels
        self.severity_thresholds = {
            'critical': {'missing_count': 50, 'amount': 50000},
            'high': {'missing_count': 20, 'amount': 10000},
            'medium': {'missing_count': 5, 'amount': 1000},
            'low': {'missing_count': 0, 'amount': 0}
        }

    def send_reconciliation_notification(
        self,
        reconciliation_result: ReconciliationResult,
        reconciliation_date: date,
        report_url: Optional[str] = None,
        report_attachment: Optional[str] = None
    ) -> bool:
        """Send reconciliation notification with appropriate severity.
        
        Args:
            reconciliation_result: The reconciliation result object
            reconciliation_date: Date of the reconciliation run
            report_url: Optional S3 presigned URL to the report
            report_attachment: Optional local file path to attach to email
            
        Returns:
            True if email sent successfully, False otherwise
        """

        severity = self._determine_severity(reconciliation_result)

        try:
            # Create email message
            message = self._create_email_message(
                reconciliation_result, reconciliation_date, severity, report_url, report_attachment
            )

            # Send email if credentials are configured
            if not self.email_user or not self.email_password:
                logger.warning(
                    "Email credentials not configured, skipping notification",
                    processor=reconciliation_result.processor
                )
                return False

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)

                text = message.as_string()
                server.sendmail(self.email_user, self.operations_email, text)

            logger.info(
                "Reconciliation notification sent",
                processor=reconciliation_result.processor,
                severity=severity,
                missing_count=reconciliation_result.summary.missing_transactions_count
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to send notification",
                processor=reconciliation_result.processor,
                error=str(e)
            )
            return False

    def send_failure_alert(self, processor: str, date: str, error_message: str) -> bool:
        """Send alert email when reconciliation fails.
        
        Args:
            processor: Name of the payment processor
            date: Date of the failed reconciliation
            error_message: Error message describing the failure
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            if not self.email_user or not self.email_password:
                logger.warning("Email credentials not configured, skipping failure alert")
                return False

            message = MIMEMultipart()
            message['From'] = self.email_user
            message['To'] = self.operations_email
            message['Subject'] = f"🚨 CRITICAL: Reconciliation Failed - {processor} - {date}"

            body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .alert {{ background-color: #dc3545; color: white; padding: 20px; border-radius: 5px; }}
                    .details {{ background-color: #f8f9fa; padding: 15px; margin-top: 20px; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <div class="alert">
                    <h2>⚠️ Reconciliation System Failure</h2>
                    <p><strong>Processor:</strong> {processor.upper()}</p>
                    <p><strong>Date:</strong> {date}</p>
                </div>
                
                <div class="details">
                    <h3>Error Details</h3>
                    <pre>{error_message}</pre>
                </div>
                
                <div style="margin-top: 20px; padding: 15px; background-color: #fff3cd; border-radius: 5px;">
                    <h3>Immediate Actions Required</h3>
                    <ul>
                        <li>Check system logs for detailed error information</li>
                        <li>Verify database and API connectivity</li>
                        <li>Contact DevOps team if issue persists</li>
                        <li>Manual reconciliation may be required</li>
                    </ul>
                </div>
            </body>
            </html>
            """

            message.attach(MIMEText(body, 'html'))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.sendmail(self.email_user, self.operations_email, message.as_string())

            logger.info("Failure alert sent", processor=processor, date=date)
            return True

        except Exception as e:
            logger.error("Failed to send failure alert", processor=processor, error=str(e))
            return False

    def _determine_severity(self, result: ReconciliationResult) -> str:
        """Determine notification severity based on thresholds."""
        missing_count = result.summary.missing_transactions_count
        missing_amount = float(result.summary.total_discrepancy_amount)

        for severity, thresholds in self.severity_thresholds.items():
            if (
                missing_count >= thresholds['missing_count'] or
                missing_amount >= thresholds['amount']
            ):
                return severity

        return 'low'

    def _create_email_message(
        self,
        result: ReconciliationResult,
        reconciliation_date: date,
        severity: str,
        report_url: Optional[str] = None,
        report_attachment: Optional[str] = None
    ) -> MIMEMultipart:
        """Create email message with appropriate content."""

        message = MIMEMultipart()
        message['From'] = self.email_user
        message['To'] = self.operations_email

        # Subject with severity indicator
        severity_indicator = {
            'critical': '🚨 CRITICAL',
            'high': '⚠️ HIGH PRIORITY',
            'medium': '📊 ATTENTION',
            'low': '✅ INFO'
        }

        message['Subject'] = (
            f"{severity_indicator.get(severity, '📊')} "
            f"Daily Reconciliation Report - {result.processor} - {reconciliation_date}"
        )

        # Email body
        body = self._generate_email_body(result, reconciliation_date, severity, report_url)
        message.attach(MIMEText(body, 'html'))

        # Attach report if available
        if report_attachment and Path(report_attachment).exists():
            self._attach_report(message, report_attachment)

        return message

    def _generate_email_body(
        self,
        result: ReconciliationResult,
        reconciliation_date: date,
        severity: str,
        report_url: Optional[str] = None
    ) -> str:
        """Generate HTML email body."""

        # Color coding based on severity
        color_map = {
            'critical': '#dc3545',
            'high': '#fd7e14',
            'medium': '#ffc107',
            'low': '#28a745'
        }

        color = color_map.get(severity, '#6c757d')
        missing_count = result.summary.missing_transactions_count
        discrepancy_amount = result.summary.total_discrepancy_amount

        # Generate recommendations
        recommendations = self._generate_email_recommendations(result, severity)

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 15px; border-radius: 5px; }}
                .summary {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .metric {{ display: inline-block; margin: 10px 15px 10px 0; }}
                .metric-label {{ font-weight: bold; color: #6c757d; }}
                .metric-value {{ font-size: 18px; color: #495057; }}
                .recommendations {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .footer {{ color: #6c757d; font-size: 12px; margin-top: 30px; }}
                .button {{
                    background-color: #007bff; color: white; padding: 10px 20px;
                    text-decoration: none; border-radius: 5px; display: inline-block;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>Daily Transaction Reconciliation Report</h2>
                <p><strong>Processor:</strong> {result.processor.upper()} |
                   <strong>Date:</strong> {reconciliation_date} |
                   <strong>Severity:</strong> {severity.upper()}</p>
            </div>

            <div class="summary">
                <h3>Reconciliation Summary</h3>
                <div class="metric">
                    <div class="metric-label">Processor Transactions</div>
                    <div class="metric-value">{result.summary.processor_transactions:,}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Internal Matches</div>
                    <div class="metric-value">{result.summary.internal_transactions:,}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Missing Transactions</div>
                    <div class="metric-value" style="color: {color}; font-weight: bold;">
                        {missing_count:,}
                    </div>
                </div>
                <div class="metric">
                    <div class="metric-label">Discrepancy Amount</div>
                    <div class="metric-value" style="color: {color}; font-weight: bold;">
                        ${discrepancy_amount:,.2f}
                    </div>
                </div>
            </div>

            {recommendations}

            {'<div style="margin: 20px 0;"><a href="' + report_url + '" class="button">Download Full Report</a></div>' if report_url else ''}

            <div class="footer">
                <p>This is an automated notification from the FinTech Reconciliation System.<br>
                For questions, contact the DevOps team at devops@fintech.com</p>
                <p><strong>System:</strong> fintech-reconciliation-v1.0 |
                   <strong>Generated:</strong> {reconciliation_date}</p>
            </div>
        </body>
        </html>
        """

        return html_body

    def _generate_email_recommendations(self, result: ReconciliationResult, severity: str) -> str:
        """Generate recommendations section for email."""
        if severity == 'critical':
            recs = [
                "🚨 <strong>IMMEDIATE ACTION REQUIRED</strong>",
                "• Contact payment processor within 1 hour",
                "• Escalate to finance and compliance teams",
                "• Prepare incident report for leadership"
            ]
        elif severity == 'high':
            recs = [
                "⚠️ <strong>HIGH PRIORITY ACTIONS</strong>",
                "• Review missing transactions within 2 hours",
                "• Contact payment processor if needed",
                "• Monitor for pattern in discrepancies"
            ]
        elif severity == 'medium':
            recs = [
                "📊 <strong>STANDARD REVIEW PROCESS</strong>",
                "• Review missing transactions during business hours",
                "• Verify merchant account configurations",
                "• Schedule follow-up reconciliation"
            ]
        else:
            recs = [
                "✅ <strong>ALL CLEAR</strong>",
                "• No immediate action required",
                "• Continue standard monitoring",
                "• Archive report for compliance"
            ]

        return f'<div class="recommendations"><h3>Recommended Actions</h3>{"<br>".join(recs)}</div>'

    def _attach_report(self, message: MIMEMultipart, file_path: str):
        """Attach report file to email."""
        try:
            with open(file_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())

            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={Path(file_path).name}'
            )
            message.attach(part)

        except Exception as e:
            logger.warning("Failed to attach report", file_path=file_path, error=str(e))