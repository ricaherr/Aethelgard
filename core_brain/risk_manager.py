"""
Risk Manager Module
Manages position sizing, risk allocation, and lockdown mode.
Aligned with Aethelgard's principles of Autonomy and Resilience.
"""
import json
import logging
from typing import Optional, Dict

# Dependencies aligned with the project structure
from data_vault.storage import StorageManager
from models.signal import MarketRegime

logger = logging.getLogger(__name__)

class RiskManager:
    """
    Manages trading risk by being adaptive, persistent, resilient, and agnostic.
    
    Features:
    - Auto-Adjusting Risk: Loads risk parameters from dynamic_params.json, allowing a Tuner to modify them.
    - Lockdown Persistence: Saves and restores lockdown state from the database.
    - Data Resilience: Handles None market regimes defensively.
    - Agnostic Sizing: Calculates position size based on explicit point/pip value.
    """
    
    def __init__(self, initial_capital: float, config_path='config/dynamic_params.json'):
        """
        Initialize RiskManager.
        
        Args:
            initial_capital: Starting capital amount.
            config_path: Path to the dynamic parameters configuration file.
        """
        self.capital = initial_capital
        
        # 1. Auto-ajuste: Cargar parámetros desde archivo dinámico
        try:
            with open(config_path, 'r') as f:
                dynamic_params = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning(f"Could not load {config_path}. Using defensive default values.")
            dynamic_params = {}

        self.risk_per_trade = dynamic_params.get('risk_per_trade', 0.005) # Defensivo 0.5%
        self.max_consecutive_losses = dynamic_params.get('max_consecutive_losses', 3)

        # 2. Persistencia de Lockdown: Integración con StorageManager
        self.storage = StorageManager()
        system_state = self.storage.get_system_state()
        self.lockdown_mode = system_state.get('lockdown_mode', False)
        
        self.consecutive_losses = 0 # Se resetea, la persistencia está en el estado de lockdown
        
        logger.info(
            f"RiskManager initialized: Capital=${initial_capital:,.2f}, "
            f"Dynamic Risk Per Trade={self.risk_per_trade*100}%, Lockdown Active={self.lockdown_mode}"
        )

    def calculate_position_size(
        self,
        account_balance: float,
        stop_loss_distance: float,
        point_value: float,
        current_regime: Optional[MarketRegime] = None
    ) -> float:
        """
        Calcula el tamaño de la posición de forma agnóstica y resiliente.
        
        Args:
            account_balance: Balance actual de la cuenta.
            stop_loss_distance: Distancia al stop loss en puntos o pips.
            point_value: Valor monetario de un punto/pip para el instrumento.
            current_regime: El régimen de mercado actual.
        
        Returns:
            Tamaño de la posición (0 si no es seguro operar).
        """
        # 3. Resiliencia de Datos: Comprobar lockdown y régimen nulo
        if self.lockdown_mode or not current_regime:
            if self.lockdown_mode:
                logger.warning("Position size = 0: Account is in LOCKDOWN mode.")
            if not current_regime:
                logger.warning("Position size = 0: Market regime is None. Adopting defensive posture.")
            return 0.0

        if stop_loss_distance <= 0 or point_value <= 0:
            logger.warning("Position size = 0: Invalid stop loss distance or point value.")
            return 0.0

        # Obtener multiplicador de volatilidad (ejemplo, puede ser más complejo)
        volatility_multiplier = self._get_volatility_multiplier(current_regime)
        risk_per_trade_adjusted = self.risk_per_trade * volatility_multiplier
        
        # 4. Agnosticismo: Usar point_value en el cálculo
        risk_amount_per_trade = account_balance * risk_per_trade_adjusted
        value_at_risk_per_lot = stop_loss_distance * point_value

        if value_at_risk_per_lot <= 0:
            return 0.0
            
        position_size = risk_amount_per_trade / value_at_risk_per_lot
        
        logger.debug(
            f"Position calc: Regime={current_regime.value}, Adjusted Risk={risk_per_trade_adjusted*100:.2f}%, "
            f"Risk Amount=${risk_amount_per_trade:.2f}, Pos Size={position_size:.2f}"
        )

        return round(position_size, 2)

    def record_trade_result(self, is_win: bool, pnl: float) -> None:
        """
        Record trade result and update risk state, including lockdown persistence.
        """
        self.capital += pnl
        
        if is_win:
            self.consecutive_losses = 0
            logger.info(f"WIN: PnL=${pnl:+.2f}, Capital=${self.capital:,.2f}")
            if self.lockdown_mode:
                self._deactivate_lockdown() # Opcional: un trade ganador podría desactivar el lockdown
        else:
            self.consecutive_losses += 1
            logger.warning(
                f"LOSS: PnL=${pnl:+.2f}, Capital=${self.capital:,.2f}, "
                f"Consecutive losses: {self.consecutive_losses}"
            )
            
            if self.consecutive_losses >= self.max_consecutive_losses:
                self._activate_lockdown()

    def _activate_lockdown(self):
        """Activa y persiste el modo lockdown."""
        if not self.lockdown_mode:
            self.lockdown_mode = True
            self.storage.update_system_state({'lockdown_mode': True})
            logger.error(
                f"LOCKDOWN ACTIVATED: {self.consecutive_losses} consecutive losses. "
                "Trading disabled."
            )

    def _deactivate_lockdown(self):
        """Desactiva y persiste el modo lockdown."""
        if self.lockdown_mode:
            self.lockdown_mode = False
            self.consecutive_losses = 0
            self.storage.update_system_state({'lockdown_mode': False})
            logger.info("Lockdown DEACTIVATED. Trading resumed.")
            
    def _get_volatility_multiplier(self, regime: MarketRegime) -> float:
        """Determina un multiplicador de riesgo basado en el régimen."""
        volatile_regimes = {MarketRegime.RANGE, MarketRegime.CRASH}
        if regime in volatile_regimes:
            return 0.5 # Reduce el riesgo a la mitad en mercados volátiles/inciertos
        return 1.0 # Riesgo normal
    
    def is_locked(self) -> bool:
        """
        Check if trading is locked due to lockdown mode.
        
        Returns:
            True if in lockdown mode, False otherwise
        """
        return self.lockdown_mode

    def get_status(self) -> Dict:
        """Get current risk manager status."""
        return {
            'capital': self.capital,
            'consecutive_losses': self.consecutive_losses,
            'is_locked': self.lockdown_mode,
            'dynamic_risk_per_trade': self.risk_per_trade,
            'max_consecutive_losses': self.max_consecutive_losses
        }
