import logging
import httpx
from typing import Dict, Any, Optional
from .base_provider import BaseNotificationProvider

logger = logging.getLogger(__name__)

class WhatsAppProvider(BaseNotificationProvider):
    """
    WhatsApp (Twilio) Notification Provider.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.account_sid = config.get('account_sid')
        self.auth_token = config.get('auth_token')
        self.from_whatsapp = config.get('from_whatsapp') # e.g. 'whatsapp:+14155238886'
        self.to_whatsapp = config.get('to_whatsapp')

    async def send_message(self, message: str, **kwargs) -> bool:
        if not self.is_configured():
            self.logger.warning("WhatsApp provider not fully configured")
            return False
            
        return await self._execute_send(message)

    async def send_alert(self, title: str, body: str, **kwargs) -> bool:
        message = f"*{title}*\n\n{body}"
        return await self.send_message(message)

    async def _execute_send(self, message: str) -> bool:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        auth = (self.account_sid, self.auth_token)
        payload = {
            "From": self.from_whatsapp,
            "To": self.to_whatsapp,
            "Body": message
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, data=payload, auth=auth)
                if response.status_code in [200, 201]:
                    return True
                else:
                    self.logger.error(f"WhatsApp error: {response.text}")
                    return False
        except Exception as e:
            self.logger.error(f"Error sending WhatsApp message: {e}")
            return False

    def is_configured(self) -> bool:
        return all([self.account_sid, self.auth_token, self.from_whatsapp, self.to_whatsapp])
