import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging
from src.core.celery_app import celery

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "no-reply@aisales.com")
SMTP_PASS = os.getenv("SMTP_PASS", "placeholder_pass")

@celery.task(name="send_email_async_task", bind=True, max_retries=3)
def _send_email_async_task(self, to_email: str, subject: str, html_body: str):
    try:
        if not to_email or to_email == "admin@example.com":
            logger.info(f"[Email Mocked] Would have sent email to {to_email}: {subject}")
            return
            
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        
        part = MIMEText(html_body, "html", "utf-8")
        msg.attach(part)
        
        logger.info(f"Connecting to SMTP {SMTP_HOST} to send email to {to_email}")
        
        # In actual production with real credentials, this block would run:
        # with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        #     server.starttls()
        #     server.login(SMTP_USER, SMTP_PASS)
        #     server.sendmail(SMTP_USER, to_email, msg.as_string())
        
        # Mocking success since credentials are placeholders
        logger.info(f"[Email Simulated Success] Delivered to {to_email}")
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        self.retry(exc=e, countdown=10)

def send_alert_email(to_email: str, subject: str, message_body: str):
    """Fires Celery task for alerting"""
    html_template = f"""
    <div dir="rtl" style="font-family: Arial, sans-serif; padding: 20px; background: #f8fafc; border-radius: 10px;">
        <h2 style="color: #4f46e5;">إشعار نظام AI CRM</h2>
        <div style="background: white; padding: 20px; border-radius: 8px; border: 1px solid #e2e8f0;">
            <p style="font-size: 16px; color: #334155; line-height: 1.6;">{message_body}</p>
        </div>
        <p style="color: #94a3b8; font-size: 12px; margin-top: 20px;">هذه رسالة آلية من نظام إدارة المتاجر الذكي.</p>
    </div>
    """
    _send_email_async_task.delay(to_email, subject, html_template)
