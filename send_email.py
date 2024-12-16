import smtplib
from email.mime.text import MIMEText
import logging

from manage_files import create_email_fail_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],  # This will output to terminal
)
logger = logging.getLogger(__name__)


def send_email(
    from_email: str,
    password: str,
    to_email: str,
    domain: str,
    message: str,
    current_time: str,
    event_type: str,
    check_type: str,
    libelle: str,
):
    """If the event type is alert: Send alert email when domain is down or returns non-200 status or ping does not work
    If the event type is recovery: Send recovery email when domain is up or returns 200 status or ping works
    """

    if event_type == "alert":
        # subject = f"Alert: {libelle} - {domain} is having issues - {check_type} "
        subject = f"Alerte : {libelle} - {domain} est DOWN - {check_type}"
        body = f"{message}"
    elif event_type == "recovery":
        # subject = f"Recovery: {libelle} - {domain} is back up"
        subject = f"UP : {libelle} - {domain} est de nouveau UP - {check_type}"
        body = f"{message}"

    # SMTP Configuration for Outlook
    smtp_server_config(
        from_email, password, to_email, subject, body, current_time, event_type
    )


def smtp_server_config(
    from_email: str,
    password: str,
    to_email: str,
    subject: str,
    body: str,
    current_time: str,
    event_type: str,
):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    # SMTP Configuration for Outlook
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_USERNAME = from_email  # Your Gmail email
    SMTP_PASSWORD = password  # Your Gmail app password
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.connect(SMTP_SERVER, SMTP_PORT)
            server.starttls()  # Enable TLS
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"{event_type} email sent to {to_email}")
    except Exception as e:
        error_msg = f"Failed to send {event_type} email to {to_email}: {str(e)}"
        logger.error(error_msg)
        create_email_fail_file(error_msg, current_time, to_email)

    return msg, SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD
