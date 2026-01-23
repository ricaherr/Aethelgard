import logging
from typing import Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AccountRotator:
    """
    Esquema (boilerplate) para automatizar el registro de cuentas de prueba de 14 días
    usando correos derivados (usuario+n@gmail.com) para plataformas como NinjaTrader.
    
    Esta clase provee la estructura y métodos para la gestión de cuentas,
    pero la implementación específica de la interacción con el sistema de registro
    de NinjaTrader (o similar) deberá ser añadida.
    """

    def __init__(self, base_email: str, base_password: str, domain: str = "@gmail.com"):
        """
        Inicializa el rotador de cuentas.
        
        Args:
            base_email: Parte principal del correo electrónico (ej. "usuario").
            base_password: Contraseña base a usar para las cuentas.
            domain: Dominio del correo electrónico (ej. "@gmail.com").
        """
        self.base_email = base_email
        self.base_password = base_password
        self.domain = domain
        self.accounts: Dict[str, Dict[str, Any]] = {}
        logger.info("AccountRotator inicializado para base_email: %s%s", self.base_email, self.domain)

    def _generate_email(self, index: int) -> str:
        """
        Genera un correo electrónico derivado (ej. usuario+1@gmail.com).
        """
        return f"{self.base_email}+{index}{self.domain}"

    def register_new_account(self, index: int) -> Optional[Dict[str, Any]]:
        """
        Simula el registro de una nueva cuenta de prueba.
        
        En una implementación real, aquí se interactuaría con la API o UI
        del proveedor de la cuenta (ej. NinjaTrader) para:
        1. Navegar a la página de registro.
        2. Rellenar formularios con el correo generado y la contraseña base.
        3. Confirmar el registro y manejar cualquier verificación (ej. captcha).
        4. Obtener credenciales de la cuenta de prueba (si aplica) y fecha de expiración.
        
        Returns:
            Dict con información de la cuenta registrada o None si falla.
        """
        email = self._generate_email(index)
        expiration_date = (datetime.now() + timedelta(days=14)).isoformat()
        
        logger.info("Simulando registro para email: %s", email)
        
        # --- LÓGICA DE REGISTRO REAL IRÍA AQUÍ ---
        # Ejemplo: 
        # api_client.register(email, self.base_password, ...)
        # response = api_client.get_account_details(email)
        # --- FIN LÓGICA DE REGISTRO REAL ---

        # Simulación de éxito
        account_info = {
            "email": email,
            "password": self.base_password, # En un sistema real, no guardar password así
            "registration_date": datetime.now().isoformat(),
            "expiration_date": expiration_date,
            "status": "active",
            "platform_credentials": {"username": f"user{index}", "broker_id": "demo_broker"}
        }
        self.accounts[email] = account_info
        logger.info("Cuenta simulada registrada: %s, expira: %s", email, expiration_date)
        return account_info

    def get_active_accounts(self) -> List[Dict[str, Any]]:
        """
        Devuelve una lista de cuentas activas (no expiradas).
        """
        active = []
        for email, info in self.accounts.items():
            exp_date = datetime.fromisoformat(info["expiration_date"])
            if exp_date > datetime.now() and info["status"] == "active":
                active.append(info)
        return active

    def refresh_accounts(self):
        """
        En una implementación real, esto verificaría el estado de las cuentas
        con el proveedor externo y las renovaría o registraría nuevas si fuera necesario.
        """
        logger.info("Simulando refresco de cuentas...")
        # Ejemplo: Si solo tenemos una cuenta y está a punto de expirar, registra una nueva
        if not self.accounts or (datetime.fromisoformat(list(self.accounts.values())[0]["expiration_date"]) - datetime.now()).days < 5:
            next_index = len(self.accounts) + 1
            self.register_new_account(next_index)
        
        logger.info("Refresco de cuentas simulado completado.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    rotator = AccountRotator("aethelgard_tester", "SecureP@ssw0rd")
    
    # Registrar algunas cuentas de prueba
    for i in range(1, 4):
        rotator.register_new_account(i)
        
    print("\n--- Cuentas Activas ---")
    for account in rotator.get_active_accounts():
        print(f"Email: {account['email']}, Expira: {account['expiration_date'][:10]}")

    print("\n--- Refrescando Cuentas ---")
    rotator.refresh_accounts() # Simula la creación de una nueva si es necesario
    
    print("\n--- Cuentas Activas Después de Refresco ---")
    for account in rotator.get_active_accounts():
        print(f"Email: {account['email']}, Expira: {account['expiration_date'][:10]}")
