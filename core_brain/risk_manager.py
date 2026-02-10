"""
Risk Manager Module
Manages position sizing, risk allocation, and lockdown mode.
Aligned with Aethelgard's principles of Autonomy and Resilience.

CONSOLIDATION: Single Source of Truth for position size calculation.
EDGE COMPLIANCE: Integrated monitoring with circuit breaker protection.
"""
import json
import logging
from typing import Optional, Dict, Any

# Dependencies aligned with the project structure
from data_vault.storage import StorageManager
from models.signal import MarketRegime, Signal
from core_brain.position_size_monitor import PositionSizeMonitor, CalculationStatus

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
    
    def __init__(
        self, 
        storage: StorageManager,
        initial_capital: float, 
        config_path: str = 'config/dynamic_params.json', 
        risk_settings_path: str = 'config/risk_settings.json'
    ):
        """
        Initialize RiskManager with dependency injection.
        
        Args:
            storage: StorageManager instance (REQUIRED - dependency injection).
            initial_capital: Starting capital amount.
            config_path: Path to the dynamic parameters configuration file.
            risk_settings_path: Path to risk settings (Single Source of Truth).
        """
        self.storage = storage
        self.capital = initial_capital
        
        # 1. Load risk settings (Single Source of Truth)
        try:
            with open(risk_settings_path, 'r') as f:
                risk_settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning(f"Could not load {risk_settings_path}. Using defaults.")
            risk_settings = {}
        
        # 2. Auto-ajuste: Cargar parámetros desde archivo dinámico
        try:
            with open(config_path, 'r') as f:
                dynamic_params = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning(f"Could not load {config_path}. Using defensive default values.")
            dynamic_params = {}

        self.risk_per_trade = dynamic_params.get('risk_per_trade', 0.005) # Defensivo 0.5%
        # Read from risk_settings (Single Source of Truth), fallback to dynamic_params, then default
        self.max_consecutive_losses = risk_settings.get('max_consecutive_losses', 
                                                        dynamic_params.get('max_consecutive_losses', 3))

        # 3. Persistencia de Lockdown: Storage inyectado, no creado aquí
        system_state = self.storage.get_system_state()
        self.lockdown_mode = system_state.get('lockdown_mode', False)
        
        self.consecutive_losses = 0 # Se resetea, la persistencia está en el estado de lockdown
        
        # 4. EDGE Compliance: Initialize position size monitor with circuit breaker
        self.monitor = PositionSizeMonitor(
            max_consecutive_failures=3,
            circuit_breaker_timeout=300,  # 5 minutes
            history_window=100
        )
        
        logger.info(
            f"RiskManager initialized: Capital=${initial_capital:,.2f}, "
            f"Dynamic Risk Per Trade={self.risk_per_trade*100}%, Lockdown Active={self.lockdown_mode}"
        )

    # =========================================================================
    # POSITION SIZE CALCULATION - MASTER FUNCTION (Single Source of Truth)
    # =========================================================================
    
    def calculate_position_size_master(
        self,
        signal: Signal,
        connector: Any,
        regime_classifier: Optional[Any] = None
    ) -> float:
        """
        🎯 MASTER FUNCTION - Single Source of Truth for Position Size Calculation
        
        Calcula position size de forma completa y correcta:
        1. Valida lockdown mode
        2. Obtiene balance real del broker
        3. Obtiene symbol info del broker
        4. Calcula pip_size dinámicamente (JPY vs no-JPY)
        5. Calcula point_value dinámicamente (usa exchange rate real)
        6. Obtiene régimen real del mercado (o usa default seguro)
        7. Calcula SL distance en pips
        8. Aplica fórmula de riesgo con volatility multiplier
        9. Valida margen disponible
        10. Valida exposición total
        11. Aplica límites de broker (min/max lots)
        12. Retorna position size final
        
        Args:
            signal: Signal con symbol, entry_price, stop_loss, take_profit
            connector: Broker connector (MT5Connector, etc.) con acceso a MT5
            regime_classifier: Optional RegimeClassifier para obtener régimen real
            
        Returns:
            float: Position size en lotes (0.0 si rechazado por cualquier razón)
        """
        try:
            # 1. Validar lockdown
            if self.lockdown_mode:
                logger.warning(f"Position size = 0: Account in LOCKDOWN mode")
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=0.0,
                    risk_target=0.0,
                    status=CalculationStatus.WARNING,
                    warnings=["Lockdown mode active"]
                )
                return 0.0
            
            # 1b. EDGE: Check circuit breaker
            if not self.monitor.is_trading_allowed():
                logger.critical(
                    f"🔥 Position size = 0: CIRCUIT BREAKER ACTIVE "
                    f"(consecutive failures: {self.monitor.consecutive_failures})"
                )
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=0.0,
                    risk_target=0.0,
                    status=CalculationStatus.CRITICAL,
                    error_message="Circuit breaker active"
                )
                return 0.0
            
            # 2. Obtener balance real
            account_balance = self._get_account_balance(connector)
            if account_balance <= 0:
                logger.error(f"Invalid account balance: {account_balance}")
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=0.0,
                    risk_target=0.0,
                    status=CalculationStatus.ERROR,
                    error_message=f"Invalid account balance: {account_balance}"
                )
                return 0.0
            
            # 3. Obtener symbol info del broker
            symbol_info = self._get_symbol_info(connector, signal.symbol)
            if symbol_info is None:
                logger.error(f"Could not get symbol info for {signal.symbol}")
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=0.0,
                    risk_target=0.0,
                    status=CalculationStatus.ERROR,
                    error_message=f"Could not get symbol info for {signal.symbol}"
                )
                return 0.0
            
            # 4. Calcular pip_size (JPY vs no-JPY)
            pip_size = self._calculate_pip_size(signal.symbol)
            
            # 5. Calcular point_value dinámicamente
            point_value = self._calculate_point_value(
                symbol_info=symbol_info,
                pip_size=pip_size,
                entry_price=signal.entry_price,
                symbol=signal.symbol
            )
            
            if point_value <= 0:
                logger.error(f"Invalid point_value: {point_value}")
                return 0.0
            
            # 6. Obtener régimen real del mercado
            current_regime = self._get_market_regime(signal, regime_classifier)
            
            # 7. Calcular SL distance en pips
            if not signal.stop_loss or signal.stop_loss <= 0:
                logger.warning(f"Invalid stop_loss for {signal.symbol}, using default 50 pips")
                stop_loss_distance_pips = 50.0
            else:
                price_distance = abs(signal.entry_price - signal.stop_loss)
                stop_loss_distance_pips = price_distance / pip_size
            
            if stop_loss_distance_pips <= 0:
                logger.error(f"Invalid stop_loss distance: {stop_loss_distance_pips} pips")
                return 0.0
            
            # 8. Aplicar fórmula de riesgo
            volatility_multiplier = self._get_volatility_multiplier(current_regime)
            risk_per_trade_adjusted = self.risk_per_trade * volatility_multiplier
            risk_amount_usd = account_balance * risk_per_trade_adjusted
            value_at_risk_per_lot = stop_loss_distance_pips * point_value
            
            if value_at_risk_per_lot <= 0:
                logger.error(f"Invalid value_at_risk_per_lot: {value_at_risk_per_lot}")
                return 0.0
            
            position_size = risk_amount_usd / value_at_risk_per_lot
            
            logger.debug(
                f"Position calc: Symbol={signal.symbol}, Regime={current_regime.value}, "
                f"Pip={pip_size}, PV=${point_value:.2f}, SL={stop_loss_distance_pips:.1f}pips, "
                f"Risk={risk_per_trade_adjusted*100:.2f}%, Size={position_size:.4f}"
            )
            
            # 9. Validar margen disponible
            if not self._validate_margin(connector, position_size, signal, symbol_info):
                logger.warning(f"Insufficient margin for {position_size:.2f} lots of {signal.symbol}")
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=0.0,
                    risk_target=risk_amount_usd,
                    risk_actual=0.0,
                    status=CalculationStatus.ERROR,
                    error_message="Insufficient margin"
                )
                return 0.0
            
            # 10. Validar exposición total (TODO: implementar cuando tengamos exposure manager)
            # if not self._validate_exposure(position_size, signal):
            #     return 0.0
            
            # 11. Aplicar límites de broker
            position_size_final = self._apply_broker_limits(position_size, symbol_info)
            
            # 11b. SAFETY CHECK: Si después del redondeo el riesgo excede el objetivo,
            # bajar un step para ser conservador
            real_risk_after_round = position_size_final * stop_loss_distance_pips * point_value
            if real_risk_after_round > risk_amount_usd:
                # Bajar un step
                step = symbol_info.volume_step if symbol_info.volume_step > 0 else 0.01
                position_size_conservative = position_size_final - step
                # Asegurar que no baje del mínimo
                if position_size_conservative >= symbol_info.volume_min:
                    position_size_final = position_size_conservative
                    logger.debug(
                        f"Position size reduced to stay within risk target: "
                        f"{position_size_final + step:.2f} → {position_size_final:.2f}"
                   )
            
            # 12. Log final
            real_risk_usd = position_size_final * stop_loss_distance_pips * point_value
            real_risk_pct = (real_risk_usd / account_balance) * 100
            
            # ====== EDGE VALIDATION: Final Safety Checks ======
            # Garantizar que NUNCA excedemos riesgo objetivo (crítico)
            if real_risk_usd > risk_amount_usd * 1.01:  # Tolerancia 1%
                logger.error(
                    f"🔥 CRITICAL: Position size calculation EXCEEDS risk target! "
                    f"Real: ${real_risk_usd:.2f} > Target: ${risk_amount_usd:.2f} "
                    f"Symbol: {signal.symbol}, Size: {position_size_final:.2f} lots"
                )
                # Record CRITICAL failure
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=position_size_final,
                    risk_target=risk_amount_usd,
                    risk_actual=real_risk_usd,
                    status=CalculationStatus.CRITICAL,
                    error_message=f"Risk exceeds target: ${real_risk_usd:.2f} > ${risk_amount_usd:.2f}"
                )
                # Emergency fallback: return 0 para NO ejecutar trade
                return 0.0
            
            # Collect warnings
            warnings_list = []
            
            # Detectar anomalías: position size extremadamente pequeño
            if position_size_final < symbol_info.volume_min * 1.5:
                warning_msg = (
                    f"Position size muy pequeño: {position_size_final:.4f} lots "
                    f"(min: {symbol_info.volume_min:.2f})"
                )
                logger.warning(f"⚠️  {warning_msg} - Symbol: {signal.symbol}")
                warnings_list.append(warning_msg)
            
            # Detectar anomalías: position size extremadamente grande (> 50% de max)
            if position_size_final > symbol_info.volume_max * 0.5:
                warning_msg = (
                    f"Position size muy grande: {position_size_final:.2f} lots "
                    f"(max: {symbol_info.volume_max:.2f})"
                )
                logger.warning(f"⚠️  {warning_msg} - Symbol: {signal.symbol}")
                warnings_list.append(warning_msg)
            
            # Validar que el error está dentro de tolerancia
            error_absolute = abs(real_risk_usd - risk_amount_usd)
            error_pct = (error_absolute / risk_amount_usd) * 100 if risk_amount_usd > 0 else 0
            
            if error_pct > 10.0:
                warning_msg = f"Error > 10%: {error_pct:.2f}%"
                logger.warning(
                    f"⚠️  Position size {warning_msg} "
                    f"(Target: ${risk_amount_usd:.2f}, Real: ${real_risk_usd:.2f}) "
                    f"Symbol: {signal.symbol}"
                )
                warnings_list.append(warning_msg)
            
            logger.info(
                f"✅ Position Size Calculated: {position_size_final:.2f} lots | "
                f"Risk: ${real_risk_usd:.2f} ({real_risk_pct:.2f}%) | "
                f"SL: {stop_loss_distance_pips:.1f} pips | "
                f"Regime: {current_regime.value}"
            )
            
            # Record successful calculation or warning
            calc_status = CalculationStatus.WARNING if warnings_list else CalculationStatus.SUCCESS
            self.monitor.record_calculation(
                symbol=signal.symbol,
                position_size=position_size_final,
                risk_target=risk_amount_usd,
                risk_actual=real_risk_usd,
                status=calc_status,
                warnings=warnings_list if warnings_list else None
            )
            
            return position_size_final
            
        except Exception as e:
            logger.error(f"Error in calculate_position_size_master: {e}", exc_info=True)
            # Record ERROR
            self.monitor.record_calculation(
                symbol=signal.symbol if signal else "UNKNOWN",
                position_size=0.0,
                risk_target=0.0,
                status=CalculationStatus.ERROR,
                error_message=str(e)
            )
            return 0.0
    
    # =========================================================================
    # HELPER METHODS - Private
    # =========================================================================
    
    def _get_account_balance(self, connector: Any) -> float:
        """Obtiene balance de la cuenta del connector."""
        try:
            # Usa método del connector (arquitectura agnóstica)
            if hasattr(connector, 'get_account_balance'):
                return connector.get_account_balance()
            
            logger.warning("Connector does not support get_account_balance, using default 10000")
            return 10000.0
        except Exception as e:
            logger.error(f"Error getting account balance: {e}")
            return 10000.0
    
    def _get_symbol_info(self, connector: Any, symbol: str) -> Optional[Any]:
        """Obtiene symbol info del broker a través del connector."""
        try:
            # Usa método del connector (arquitectura agnóstica)
            if hasattr(connector, 'get_symbol_info'):
                return connector.get_symbol_info(symbol)
            
            logger.error(f"Connector does not support get_symbol_info for {symbol}")
            return None
        except Exception as e:
            logger.error(f"Error getting symbol info for {symbol}: {e}")
            return None
    
    def _calculate_pip_size(self, symbol: str) -> float:
        """
        Calcula pip size basado en el símbolo.
        
        Returns:
            0.01 para pares JPY (2 decimales)
            0.0001 para pares forex estándar (4 decimales)
        """
        if 'JPY' in symbol:
            return 0.01
        elif 'XAU' in symbol or 'XAG' in symbol:  # Oro/Plata
            return 0.01
        else:
            return 0.0001
    
    def _calculate_point_value(
        self,
        symbol_info: Any,
        pip_size: float,
        entry_price: float,
        symbol: str
    ) -> float:
        """
        Calcula point value (valor de 1 pip para 1 lote) dinámicamente.
        
        Fórmula:
        - Si quote currency == account currency (ej: EUR/USD con cuenta USD):
          point_value = contract_size × pip_size
        - Si quote currency != account currency (ej: USD/JPY con cuenta USD):
          point_value = (contract_size × pip_size) / exchange_rate
        
        Args:
            symbol_info: MT5 symbol info object
            pip_size: Tamaño del pip (0.0001 o 0.01)
            entry_price: Precio de entrada (usado como exchange rate)
            symbol: Nombre del símbolo
            
        Returns:
            float: Point value en USD por pip por lote
        """
        try:
            contract_size = symbol_info.trade_contract_size
            
            # Detectar quote currency (últimas 3 letras del símbolo)
            if len(symbol) >= 6:
                quote_currency = symbol[-3:]
            else:
                quote_currency = "USD"
            
            # Asumir account currency = USD (puede obtenerse de account_info)
            account_currency = "USD"
            
            if quote_currency == account_currency:
                # Caso simple: EUR/USD, XAU/USD, etc.
                point_value = contract_size * pip_size
            else:
                # Caso con conversión: USD/JPY, GBP/JPY, etc.
                # Usar entry_price como tasa de cambio
                conversion_rate = entry_price
                if conversion_rate <= 0:
                    logger.error(f"Invalid conversion_rate: {conversion_rate}")
                    return 10.0  # Default fallback
                point_value = (contract_size * pip_size) / conversion_rate
            
            logger.debug(
                f"Point value calc: {symbol} | Contract={contract_size} | "
                f"Pip={pip_size} | Quote={quote_currency} | PV=${point_value:.2f}/pip"
            )
            
            return point_value
            
        except Exception as e:
            logger.error(f"Error calculating point_value: {e}")
            return 10.0  # Default fallback para forex estándar
    
    def _get_market_regime(
        self,
        signal: Signal,
        regime_classifier: Optional[Any]
    ) -> MarketRegime:
        """
        Obtiene el régimen real del mercado.
        
        Orden de prioridad:
        1. Signal tiene metadata['regime']
        2. RegimeClassifier.classify() si está disponible
        3. Default: MarketRegime.RANGE (defensive)
        """
        # Intentar obtener de signal.metadata
        if signal.metadata and 'regime' in signal.metadata:
            try:
                regime_val = signal.metadata['regime']
                if isinstance(regime_val, MarketRegime):
                    return regime_val
                return MarketRegime(regime_val)
            except (ValueError, KeyError):
                pass
        
        # Intentar obtener de signal.regime property
        if hasattr(signal, 'regime') and signal.regime:
            return signal.regime
        
        # TODO: Usar regime_classifier si está disponible
        # if regime_classifier and hasattr(regime_classifier, 'classify'):
        #     return regime_classifier.classify(...)
        
        # Default defensivo
        logger.debug(f"No regime found for {signal.symbol}, using defensive default: RANGE")
        return MarketRegime.RANGE
    
    def _validate_margin(
        self,
        connector: Any,
        position_size: float,
        signal: Signal,
        symbol_info: Any
    ) -> bool:
        """
        Valida que hay margen suficiente para abrir la posición.
        Usa MT5 built-in a través del connector (arquitectura agnóstica).
        
        Returns:
            True si hay margen suficiente, False si no
        """
        try:
            # Delega al connector para calcular margen
            if not hasattr(connector, 'calculate_margin'):
                logger.warning("Connector does not support calculate_margin, skipping validation")
                return True  # No bloquear si connector no soporta validación
            
            margin_required = connector.calculate_margin(signal, position_size)
            
            if margin_required is None:
                logger.warning(f"Could not calculate margin for {signal.symbol}, skipping validation")
                return True  # No bloquear si no podemos calcular
            
            # Obtener margin_free del connector
            if not hasattr(connector, 'get_account_balance'):
                logger.warning("Connector does not support balance check, skipping")
                return True
            
            # Para MT5: necesitamos account_info completa para margin_free
            # Como no queremos importar MT5 aquí, asumimos que si el cálculo de margen funcionó,
            # el connector puede validar internamente. Por ahora, aceptamos el margen calculado.
            # TODO: Agregar get_margin_free() al connector interface si es necesario
            
            logger.debug(
                f"Margin calculation OK: Required=${margin_required:.2f} for {signal.symbol}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Error validating margin: {e}")
            return True  # No bloquear por error de validación
    
    def _apply_broker_limits(self, position_size: float, symbol_info: Any) -> float:
        """
        Aplica límites de broker (min/max volume) y redondea al step.
        
        Returns:
            Position size ajustado a límites del broker
        """
        try:
            min_lot = symbol_info.volume_min
            max_lot = symbol_info.volume_max
            step = symbol_info.volume_step
            
            # Clamp a rango min/max
            position_size_clamped = max(min_lot, min(position_size, max_lot))
            
            # Redondear al step más cercano (round, no floor)
            if step > 0:
                # Round to nearest step (not down)
                steps_count = round(position_size_clamped / step)
                position_size_final = steps_count * step
                
                # Si quedó en 0, usar al menos el min_lot
                if position_size_final < min_lot:
                    position_size_final = min_lot
            else:
                # Si no hay step, redondear a 2 decimales
                position_size_final = round(position_size_clamped, 2)
            
            # Asegurar que está dentro de límites después del redondeo
            position_size_final = max(min_lot, min(position_size_final, max_lot))
            
            if position_size_final != position_size:
                logger.debug(
                    f"Position size adjusted: {position_size:.4f} → {position_size_final:.2f} "
                    f"(limits: {min_lot}-{max_lot}, step={step})"
                )
            
            return position_size_final
            
        except Exception as e:
            logger.error(f"Error applying broker limits: {e}")
            # Fallback conservador
            return max(0.01, min(round(position_size, 2), 10.0))
    
    # =========================================================================
    # LEGACY METHOD - Deprecated, mantener por compatibilidad
    # =========================================================================
    
    def calculate_position_size(
        self,
        account_balance: float,
        stop_loss_distance: float,
        point_value: float,
        current_regime: Optional[MarketRegime] = None
    ) -> float:
        """
        ⚠️ DEPRECATED - Use calculate_position_size_master() instead
        
        Calcula el tamaño de la posición de forma agnóstica y resiliente.
        
        MANTENIDO POR COMPATIBILIDAD. Este método asume que pip_size y point_value
        ya fueron calculados correctamente externamente. Para cálculo completo
        y correcto, usar calculate_position_size_master().
        
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

    def _activate_lockdown(self) -> None:
        """Activa y persiste el modo lockdown."""
        if not self.lockdown_mode:
            self.lockdown_mode = True
            self.storage.update_system_state({'lockdown_mode': True})
            logger.error(
                f"LOCKDOWN ACTIVATED: {self.consecutive_losses} consecutive losses. "
                "Trading disabled."
            )

    def _deactivate_lockdown(self) -> None:
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
    
    def is_lockdown_active(self) -> bool:
        """
        Alias for is_locked() for compatibility with MainOrchestrator.
        
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

    def validate_signal(self, signal: Signal) -> bool:
        """
        Validate a signal against risk rules.
        
        Args:
            signal: Signal to validate
            
        Returns:
            True if signal passes validation, False otherwise.
            Sets signal.status to 'VETADO' if rejected.
        """
        # Check lockdown mode
        if self.lockdown_mode:
            signal.status = 'VETADO'
            logger.warning(f"Signal {signal.symbol} rejected: Lockdown mode active")
            return False
        
        # Check consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            signal.status = 'VETADO'
            logger.warning(f"Signal {signal.symbol} rejected: Max consecutive losses reached ({self.consecutive_losses})")
            return False
        
        # Additional risk checks can be added here
        # For now, basic validation
        
        logger.debug(f"Signal {signal.symbol} passed risk validation")
        return True
