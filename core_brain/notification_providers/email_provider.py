import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from .base_provider import BaseNotificationProvider

logger = logging.getLogger(__name__)

class EmailProvider(BaseNotificationProvider):
    """
    Email (SMTP) Notification Provider.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.smtp_server = config.get('smtp_server')
        self.smtp_port = config.get('smtp_port', 587)
        self.smtp_user = config.get('smtp_user')
        self.smtp_password = config.get('smtp_password')
        self.sender_email = config.get('sender_email')
        self.receiver_email = config.get('receiver_email')

    async def send_message(self, message: str, **kwargs) -> bool:
        if not self.is_configured():
            self.logger.warning("Email provider not fully configured")
            return False
            
        subject = kwargs.get('subject', 'Aethelgard Notification')
        return await self._execute_send(subject, message)

    async def send_alert(self, title: str, body: str, **kwargs) -> bool:
        return await self.send_message(body, subject=title)

    async def _execute_send(self, subject: str, body: str) -> bool:
        msg = MIMEMultipart()
        msg['From'] = self.sender_email
        msg['To'] = self.receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            # run_in_executor to avoid blocking the event loop (smtplib is sync)
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_sync, msg)
            return True
        except Exception as e:
            self.logger.error(f"Error sending Email: {e}")
            return False

    def _send_sync(self, msg: MIMEMultipart) -> None:
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)

    def is_configured(self) -> bool:
        return all([self.smtp_server, self.smtp_user, self.smtp_password, self.sender_email, self.receiver_email])
