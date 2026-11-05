"""Gmail SMTP でHTMLレポートを送信するモジュール。"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def send_html(
    html: str,
    subject: str,
    gmail_address: str,
    gmail_app_password: str,
    recipient: str,
) -> None:
    """HTMLメールを送信する。"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html", "utf-8"))

    logger.info("メール送信中: %s → %s", gmail_address, recipient)
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.send_message(msg)
    logger.info("メール送信完了: %s", subject)
