import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from decimal import Decimal
from pathlib import Path
from email.mime.multipart import MIMEMultipart

from notification_service import NotificationService
from models import ReconciliationResult, ReconciliationSummary


# -------------------------------
# ENVIRONMENT PATCH
# -------------------------------
@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set environment variables required by NotificationService."""
    monkeypatch.setenv("SMTP_SERVER", "smtp.test.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("EMAIL_USER", "user@test.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "password")
    monkeypatch.setenv("OPERATIONS_EMAIL", "ops@test.com")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/mock/url")


# -------------------------------
# SERVICE FIXTURE
# -------------------------------
@pytest.fixture
def service():
    """Return a NotificationService instance."""
    return NotificationService()


# -------------------------------
# MOCK SMTP / SSL / SLACK
# -------------------------------
@pytest.fixture(autouse=True)
def mock_email_and_slack():
    """Patch SMTP, SMTP_SSL, and requests.post for testing email and Slack notifications."""
    with patch("smtplib.SMTP") as mock_smtp, \
         patch("smtplib.SMTP_SSL") as mock_smtp_ssl, \
         patch("requests.post") as mock_requests_post:

        # Mock STARTTLS server
        mock_server = MagicMock()
        mock_server.starttls.return_value = None
        mock_server.login.return_value = None
        mock_server.sendmail.return_value = {}
        mock_smtp.return_value.__enter__.return_value = mock_server

        # Mock SSL server
        mock_ssl_server = MagicMock()
        mock_ssl_server.login.return_value = None
        mock_ssl_server.sendmail.return_value = {}
        mock_smtp_ssl.return_value.__enter__.return_value = mock_ssl_server

        # Mock Slack POST
        mock_requests_post.return_value = MagicMock(status_code=200)

        yield


# -------------------------------
# RECONCILIATION FIXTURE
# -------------------------------
@pytest.fixture
def mock_reconciliation_result():
    """Return a ReconciliationResult with medium severity for testing notifications."""
    summary = ReconciliationSummary(
        processor="TestProcessor",
        reconciliation_date=date(2025, 1, 1),
        processor_transactions=1000,
        internal_transactions=990,
        missing_transactions_count=10,
        total_discrepancy_amount=Decimal("1500.00")
    )
    return ReconciliationResult(
        processor="TestProcessor",
        reconciliation_date=date(2025, 1, 1),
        summary=summary,
        missing_transactions_details=[]
    )


# -------------------------------
# REPORT FILE FIXTURE
# -------------------------------
@pytest.fixture
def mock_report_file(tmp_path):
    """Create a temporary CSV report file for attachment tests."""
    file_path = tmp_path / "test_report.csv"
    file_path.write_text("id,amount\n1,10.00\n2,20.00")
    return str(file_path)


# -------------------------------
# TESTS: NotificationService
# -------------------------------

# Email / STARTTLS
def test_send_reconciliation_notification_success(service, mock_reconciliation_result):
    """Test sending reconciliation email via STARTTLS."""
    success = service.send_reconciliation_notification(
        mock_reconciliation_result, date(2025, 1, 1)
    )
    assert success is True


def test_send_reconciliation_notification_with_s3_url(service, mock_reconciliation_result):
    """Test sending email with S3 report URL."""
    success = service.send_reconciliation_notification(
        mock_reconciliation_result,
        date(2025, 1, 1),
        report_url="s3://mock-bucket/key/report.csv"
    )
    assert success is True


def test_send_reconciliation_notification_with_attachment(service, mock_reconciliation_result, mock_report_file):
    """Test sending email with a local CSV attachment."""
    success = service.send_reconciliation_notification(
        mock_reconciliation_result,
        date(2025, 1, 1),
        report_attachment=mock_report_file
    )
    assert success is True


def test_send_failure_alert_success(service):
    """Test sending a failure alert email."""
    success = service.send_failure_alert(
        processor="TestProcessor",
        date="2025-01-01",
        run_id="uuid-12345",
        error_message="Connection timed out"
    )
    assert success is True


def test_send_slack_notification(service):
    """Test sending a Slack notification."""
    success = service._send_slack({"text": "Test alert"})
    assert success is True


# -------------------------------
# TESTS: Internal helper methods
# -------------------------------
def test_determine_severity(service, mock_reconciliation_result):
    """Test severity determination logic."""
    severity = service._determine_severity(mock_reconciliation_result)
    assert severity == "medium"


def test_create_email_message(service, mock_reconciliation_result):
    """Test creation of email message object."""
    msg = service._create_email_message(
        result=mock_reconciliation_result,
        reconciliation_date=date(2025, 1, 1),
        severity="medium"
    )
    assert isinstance(msg, MIMEMultipart)
    assert "TestProcessor" in msg.as_string()


def test_generate_email_body_contains_recommendations(service, mock_reconciliation_result):
    """Test that email body contains actionable recommendations."""
    body = service._generate_email_body(
        mock_reconciliation_result, date(2025, 1, 1), "medium"
    )
    assert "📊 Review during business hours" in body


def test_generate_email_recommendations(service, mock_reconciliation_result):
    """Test HTML recommendations generation for critical severity."""
    rec_html = service._generate_email_recommendations(mock_reconciliation_result, "critical")
    assert "Immediate action required" in rec_html or "🚨" in rec_html


def test_attach_report_creates_attachment(service, mock_report_file):
    """Test that CSV report attachment is added to email message."""
    msg = MIMEMultipart()
    service._attach_report(msg, mock_report_file)
    attached_files = [part.get_filename() for part in msg.get_payload() if part.get_filename()]
    assert Path(mock_report_file).name in attached_files
