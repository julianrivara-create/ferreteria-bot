
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from app.core.config import get_settings
import structlog

logger = structlog.get_logger()
settings = get_settings()

class EmailService:
    @staticmethod
    def send_email(to_email, subject, content):
        message = Mail(
            from_email=settings.EMAIL_FROM,
            to_emails=to_email,
            subject=subject,
            html_content=content
        )
        try:
            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
            response = sg.send(message)
            return response.status_code
        except Exception as e:
            logger.error("email_send_error", error=str(e))
            return None
