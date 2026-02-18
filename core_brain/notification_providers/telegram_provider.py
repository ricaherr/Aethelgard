import logging
import httpx
from typing import Dict, Any, Optional
from .base_provider import BaseNotificationProvider

logger = logging.getLogger(__name__)

class TelegramProvider(BaseNotificationProvider):
    """
    Telegram Notification Provider.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.bot_token = config.get('bot_token')
        # Soportar ambos formatos para backward compatibility + soporte frontal
        self.chat_id_basic = config.get('basic_chat_id') or config.get('chat_id_basic')
        self.chat_id_premium = config.get('premium_chat_id') or config.get('chat_id_premium')
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(self, message: str, membership: str = 'basic', **kwargs) -> bool:
        chat_id = self.chat_id_premium if membership == 'premium' else self.chat_id_basic
        if not chat_id or not self.bot_token:
            self.logger.warning(f"Telegram not configured for {membership} users")
            return False
            
        return await self._execute_send(chat_id, message)

    async def send_alert(self, title: str, body: str, membership: str = 'basic', **kwargs) -> bool:
        message = f"<b>{title}</b>\n\n{body}"
        return await self.send_message(message, membership=membership)

    async def _execute_send(self, chat_id: str, message: str) -> bool:
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    return True
                else:
                    self.logger.error(f"Telegram error: {response.text}")
                    return False
        except Exception as e:
            self.logger.error(f"Error sending Telegram message: {e}")
            return False

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id_basic)
