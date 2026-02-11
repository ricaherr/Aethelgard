"""
Telegram Auto-Provisioner for Aethelgard
Auto-detects chat_id and validates bot_token via Telegram API
"""
import logging
import asyncio
from typing import Optional, Dict, Tuple
import httpx

logger = logging.getLogger(__name__)


class TelegramProvisioner:
    """Handles automatic Telegram bot setup and validation"""
    
    def __init__(self):
        self.api_base = "https://api.telegram.org/bot"
    
    async def validate_bot_token(self, bot_token: str) -> Tuple[bool, Optional[Dict]]:
        """
        Validates bot_token by calling getMe endpoint
        
        Args:
            bot_token: Telegram bot token from @BotFather
        
        Returns:
            (is_valid: bool, bot_info: dict or error_message: str)
        """
        if not bot_token or len(bot_token) < 40:
            return False, {"error": "Invalid token format"}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.api_base}{bot_token}/getMe")
                data = response.json()
                
                if data.get("ok"):
                    bot_info = data.get("result", {})
                    logger.info(f"✅ Bot validado: @{bot_info.get('username')}")
                    return True, {
                        "username": bot_info.get("username"),
                        "first_name": bot_info.get("first_name"),
                        "id": bot_info.get("id")
                    }
                else:
                    error_desc = data.get("description", "Unknown error")
                    logger.warning(f"❌ Token inválido: {error_desc}")
                    return False, {"error": error_desc}
                    
        except httpx.TimeoutException:
            logger.error("⏱️ Timeout conectando a Telegram API")
            return False, {"error": "Timeout - verifica tu conexión a internet"}
        except Exception as e:
            logger.error(f"❌ Error validando bot token: {e}")
            return False, {"error": str(e)}
    
    async def get_chat_id_from_updates(self, bot_token: str) -> Tuple[bool, Optional[str]]:
        """
        Auto-detects chat_id by reading latest updates
        User must send /start to the bot first
        
        Args:
            bot_token: Telegram bot token
        
        Returns:
            (success: bool, chat_id: str or error_message: str)
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.api_base}{bot_token}/getUpdates",
                    params={"limit": 1, "offset": -1}
                )
                data = response.json()
                
                if not data.get("ok"):
                    return False, {"error": data.get("description", "Failed to get updates")}
                
                updates = data.get("result", [])
                if not updates:
                    return False, {
                        "error": "no_messages",
                        "hint": "Envía /start al bot para detectar tu chat_id"
                    }
                
                # Extract chat_id from latest message
                latest_update = updates[0]
                message = latest_update.get("message", {})
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                
                if chat_id:
                    username = chat.get("username", "Unknown")
                    logger.info(f"✅ Chat ID detectado: {chat_id} (@{username})")
                    return True, {
                        "chat_id": str(chat_id),
                        "username": username,
                        "first_name": chat.get("first_name", "")
                    }
                else:
                    return False, {"error": "No chat_id found in updates"}
                    
        except Exception as e:
            logger.error(f"❌ Error obteniendo chat_id: {e}")
            return False, {"error": str(e)}
    
    async def send_test_message(self, bot_token: str, chat_id: str) -> Tuple[bool, Optional[str]]:
        """
        Sends a test message to verify configuration
        
        Args:
            bot_token: Telegram bot token
            chat_id: Target chat ID
        
        Returns:
            (success: bool, message_id: str or error: str)
        """
        test_message = """
🧠 <b>Aethelgard Conectado</b>

✅ Tu bot de Telegram está configurado correctamente.

📊 Recibirás notificaciones cuando:
• Cambie el régimen de mercado
• Se detecte una señal de trading
• Ocurra un evento importante del sistema

<i>Sistema autónomo listo para operar</i>
"""
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_base}{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": test_message,
                        "parse_mode": "HTML"
                    }
                )
                data = response.json()
                
                if data.get("ok"):
                    message_id = data.get("result", {}).get("message_id")
                    logger.info(f"✅ Mensaje de prueba enviado (ID: {message_id})")
                    return True, {"message_id": message_id}
                else:
                    error_desc = data.get("description", "Failed to send message")
                    logger.error(f"❌ Error enviando mensaje: {error_desc}")
                    return False, {"error": error_desc}
                    
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje de prueba: {e}")
            return False, {"error": str(e)}
    
    def get_setup_instructions(self) -> Dict[str, str]:
        """Returns human-friendly setup instructions in Spanish"""
        return {
            "step_1": {
                "title": "1. Crear tu Bot de Telegram",
                "description": "Abre Telegram y busca @BotFather (bot oficial de Telegram con verificación azul)"
            },
            "step_2": {
                "title": "2. Obtener Token del Bot",
                "description": "Envía el comando /newbot y sigue las instrucciones. BotFather te dará un token (algo como: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)"
            },
            "step_3": {
                "title": "3. Pegar Token Aquí",
                "description": "Copia el token completo y pégalo en el campo de abajo"
            },
            "step_4": {
                "title": "4. Auto-detectar tu Chat ID",
                "description": "Envía /start a tu bot en Telegram y luego haz clic en 'Obtener mi Chat ID' abajo"
            },
            "tips": {
                "security": "⚡ Tu token se guarda encriptado en la base de datos local",
                "privacy": "🔒 Aethelgard NUNCA comparte tus datos con terceros"
            }
        }


async def test_provisioner() -> None:
    """Test the provisioner with example workflow"""
    provisioner = TelegramProvisioner()
    
    # Print instructions
    instructions = provisioner.get_setup_instructions()
    print("\n" + "=" * 60)
    print("📱 CONFIGURACIÓN DE TELEGRAM - INSTRUCCIONES")
    print("=" * 60)
    for key, value in instructions.items():
        if isinstance(value, dict):
            print(f"\n{value.get('title', key)}")
            print(f"   {value.get('description', '')}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_provisioner())
