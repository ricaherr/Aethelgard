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
from models.signal import Signal, ConnectorType, MarketRegime
from core_brain.position_size_monitor import PositionSizeMonitor, CalculationStatus
from core_brain.risk_calculator import RiskCalculator
from core_brain.multi_timeframe_limiter import MultiTimeframeLimiter
from core_brain.market_utils import normalize_price, normalize_volume, calculate_pip_size
from core_brain.instrument_manager import InstrumentManager

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
        monitor: Optional[PositionSizeMonitor] = None
    ):
        """
        Initialize RiskManager with dependency injection.
        
        Args:
            storage: StorageManager instance (REQUIRED - dependency injection).
            initial_capital: Starting capital amount.
            monitor: PositionSizeMonitor instance (DI).
        """
        self.storage = storage
        self.capital = initial_capital
        
        if monitor is None:
            logger.warning("RiskManager initialized without explicit monitor! Violates strict DI.")
            from core_brain.position_size_monitor import PositionSizeMonitor
            self.monitor = PositionSizeMonitor()
        else:
            self.monitor = monitor
        
        # 1. Load settings from DB (Single Source of Truth)
        # Rule 14: Config reside en la BD. 
        risk_settings = self.storage.get_risk_settings()
        dynamic_params = self.storage.get_dynamic_params()
        
        # MIGRATION FALLBACK: If DB is empty, try to load from JSON and migrate to DB
        if not risk_settings or not dynamic_params:
            logger.warning("DB config empty. Attempting migration from JSON files...")
            self._migrate_config_from_json()
            risk_settings = self.storage.get_risk_settings()
            dynamic_params = self.storage.get_dynamic_params()

        self.risk_per_trade = dynamic_params.get('risk_per_trade', 0.005) # Defensivo 0.5%
        self.max_consecutive_losses = risk_settings.get('max_consecutive_losses', 
                                                        dynamic_params.get('max_consecutive_losses', 3))
        self.max_account_risk_pct = risk_settings.get('max_account_risk_pct', 5.0)  # Default 5%

        # 3. Persistencia de Lockdown
        system_state = self.storage.get_system_state()
        self.lockdown_mode = system_state.get('lockdown_mode', False)
        lockdown_date = system_state.get('lockdown_date', None)
        lockdown_balance = system_state.get('lockdown_balance', None)
        
        # ADAPTIVE LOCKDOWN: Auto-reset based on market conditions, not calendar
        if self.lockdown_mode:
            should_reset, reason = self._should_reset_lockdown(
                lockdown_date=lockdown_date,
                lockdown_balance=lockdown_balance,
                current_balance=initial_capital
            )
            
            if should_reset:
                logger.warning(
                    f"Lockdown auto-reset triggered: {reason}. "
                    f"Lockdown was active since {lockdown_date or 'unknown'}."
                )
                self.lockdown_mode = False
                self.storage.update_system_state({
                    'lockdown_mode': False,
                    'lockdown_date': None,
                    'lockdown_balance': None,
                    'consecutive_losses': 0
                })
                logger.info(f"✅ Lockdown deactivated: {reason}. Trading enabled.")
            else:
                logger.info(
                    f"Lockdown still active (since {lockdown_date}). "
                    f"Waiting for: balance recovery or 24h system rest."
                )
        
        self.consecutive_losses = 0 # Se resetea, la persistencia está en el estado de lockdown
        
        logger.info(
            f"RiskManager initialized: Capital=${initial_capital:,.2f}, "
            f"Dynamic Risk={self.risk_per_trade*100:.2f}%, Lockdown={self.lockdown_mode}, "
            f"Max Risk={self.max_account_risk_pct}%"
        )

    def _migrate_config_from_json(self) -> None:
        """Migrates JSON config files to DB as a fallback one-time action."""
        import json
        from pathlib import Path
        
        # Paths hardcoded ONLY here for migration/legacy support
        RISK_JSON = Path('config/risk_settings.json')
        DYNAMIC_JSON = Path('config/dynamic_params.json')
        
        if RISK_JSON.exists():
            try:
                with open(RISK_JSON, 'r') as f:
                    data = json.load(f)
                    self.storage.update_risk_settings(data)
                    logger.info(f"Migrated {RISK_JSON} to DB")
            except Exception as e:
                logger.error(f"Failed to migrate {RISK_JSON}: {e}")
                
        if DYNAMIC_JSON.exists():
            try:
                with open(DYNAMIC_JSON, 'r') as f:
                    data = json.load(f)
                    self.storage.update_dynamic_params(data)
                    logger.info(f"Migrated {DYNAMIC_JSON} to DB")
            except Exception as e:
                logger.error(f"Failed to migrate {DYNAMIC_JSON}: {e}")

    # =========================================================================
    # ACCOUNT RISK VALIDATION
    # =========================================================================
    
    def can_take_new_trade(self, signal: Signal, connector: Any) -> tuple[bool, str]:
        """
        Validates if a new trade can be taken without exceeding max account risk.
        
        This is the critical validation that prevents the account from being overexposed.
        Should be called BEFORE calculating position size in Executor.
        
        Args:
            signal: Signal to validate
            connector: Broker connector to get account balance and open positions
            
        Returns:
            tuple[bool, str]: (can_trade, reason)
                - (True, "") if signal can be executed
                - (False, "reason") if signal must be rejected
        
        Example:
            >>> can_trade, reason = risk_manager.can_take_new_trade(signal, connector)
            >>> if not can_trade:
            >>>     logger.warning(f"Signal rejected: {reason}")
            >>>     return False
        """
        try:
            # 1. Get account balance
            account_balance = self._get_account_balance(connector)
            if account_balance <= 0:
                return False, f"Invalid account balance: ${account_balance}"
            
            # 2. Calculate current risk from open positions
           # Get open positions from connector
            try:
                open_positions = connector.get_open_positions()
            except AttributeError:
                # Connector doesn't have get_open_positions (e.g., PaperConnector in tests)
                # Fall back to calculating risk from storage
                logger.debug(f"Connector {type(connector).__name__} doesn't have get_open_positions, using storage fallback")
                open_positions = []
            
            current_risk_usd = 0.0
            for pos in open_positions:
                # Calculate risk from position: volume * (entry - SL) * point_value
                try:
                    symbol = pos.get("symbol", "")
                    volume = pos.get("volume", 0.0)
                    entry_price = pos.get("entry_price", pos.get("price_open", 0.0))
                    stop_loss = pos.get("stop_loss", pos.get("sl", 0.0))
                    
                    if stop_loss > 0:
                        # Get symbol info for point value calculation
                        symbol_info = connector.get_symbol_info(symbol)
                        if symbol_info:
                            # Calculate risk
                            price_diff = abs(entry_price - stop_loss)
                            contract_size = getattr(symbol_info, 'trade_contract_size', 100000)
                            point = getattr(symbol_info, 'point', 0.00001)
                            pips = price_diff / point
                            risk_usd = (pips * point) * contract_size * volume
                            current_risk_usd += risk_usd
                except Exception as e:
                    logger.warning(f"Error calculating risk for position {pos.get('ticket', 'unknown')}: {e}")
                    continue
            
            # 3. Calculate risk of new signal
            # Use a simplified calculation: risk_per_trade * balance
            # (Actual position size calculation happens later if approved)
            signal_risk_usd = account_balance * self.risk_per_trade
            
            # 4. Calculate total risk if signal is executed
            total_risk_usd = current_risk_usd + signal_risk_usd
            total_risk_pct = (total_risk_usd / account_balance) * 100
            
            # 5. Compare against max_account_risk_pct
            if total_risk_pct > self.max_account_risk_pct:
                reason = (
                    f"Account risk would exceed {self.max_account_risk_pct}% "
                    f"(current: {current_risk_usd / account_balance * 100:.1f}% "
                    f"+ signal: {signal_risk_usd / account_balance * 100:.1f}% "
                    f"= {total_risk_pct:.1f}%)"
                )
                logger.warning(f"[{signal.symbol}] Signal rejected: {reason}")
                return False, reason
            
            # 6. Approved: within risk limits
            logger.info(
                f"[{signal.symbol}] Risk check passed: "
                f"Total risk {total_risk_pct:.1f}% / {self.max_account_risk_pct}%"
            )
            return True, ""
            
        except Exception as e:
            logger.error(f"Error validating account risk: {e}")
            # Defensive: reject trade on error
            return False, f"Risk validation error: {str(e)}"

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
                symbol=signal.symbol,
                connector=connector
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
            # 1. Sanity Check: Garantizar que NUNCA excedemos riesgo objetivo (crítico)
            is_sane, sanity_msg = self._validate_risk_sanity(
                position_size_final, stop_loss_distance_pips, point_value, risk_amount_usd, account_balance
            )
            
            if not is_sane:
                logger.error(f"🔥 CALCULATION REJECTED: {sanity_msg}")
                # Record CRITICAL failure
                self.monitor.record_calculation(
                    symbol=signal.symbol,
                    position_size=position_size_final,
                    risk_target=risk_amount_usd,
                    risk_actual=position_size_final * stop_loss_distance_pips * point_value,
                    status=CalculationStatus.CRITICAL,
                    error_message=sanity_msg
                )
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
    
    def _calculate_pip_size(self, symbol: str, connector: Any = None) -> float:
        """
        Calcula pip size basado en el símbolo y la información del broker.
        Usa la utilidad global agnóstica de mercado.
        """
        symbol_info = self._get_symbol_info(connector, symbol) if connector else None
        
        # Obtener InstrumentManager (asumiendo que está disponible o se puede instanciar)
        # En una arquitectura real, esto se inyectaría. Por ahora creamos uno local si es necesario
        # o usamos una instancia global si existe.
        im = InstrumentManager()
        
        return calculate_pip_size(symbol_info, symbol, im)
    
    def _calculate_point_value(
        self,
        symbol_info: Any,
        pip_size: float,
        entry_price: float,
        symbol: str,
        connector: Any
    ) -> float:
        try:
            contract_size = symbol_info.trade_contract_size
            account_currency = "USD" # TODO: Obtener dinámicamente de account_info
            
            # Caso 1: Símbolo termina en la moneda de la cuenta (Major)
            if symbol.endswith(account_currency):
                point_value = contract_size * pip_size
                
            # Caso 2: Símbolo empieza con la moneda de la cuenta (Directe)
            # Ej: USDJPY (Quote=JPY). 1 Pip en USD = (contract * pip) / price
            elif symbol.startswith(account_currency):
                point_value = (contract_size * pip_size) / entry_price
                
            # Caso 3: Cruce (Triangulación)
            # Ej: GBPJPY (Quote=JPY). Necesitamos USDJPY para convertir JPY -> USD.
            else:
                quote_currency = symbol[-3:]
                # Buscar par de conversión USD + Moneda de Cotización
                conv_symbol = f"USD{quote_currency}"
                
                # Intentar obtener precio de conversión a través del connector
                from connectors.generic_data_provider import GenericDataProvider
                conv_price = 0.0
                if hasattr(connector, 'get_current_price'):
                    conv_price = connector.get_current_price(conv_symbol)
                
                if conv_price and conv_price > 0:
                    # En JPY (USDJPY), dividimos por el precio (1 USD = 150 JPY)
                    point_value = (contract_size * pip_size) / conv_price
                    logger.debug(f"[JPY FIX] Using triangulation via {conv_symbol} @ {conv_price}")
                else:
                    # Fallback agresivo: Si no hay par USDXXX, intentar XXXUSD
                    conv_symbol_inv = f"{quote_currency}USD"
                    if hasattr(connector, 'get_current_price'):
                        conv_price_inv = connector.get_current_price(conv_symbol_inv)
                        if conv_price_inv and conv_price_inv > 0:
                            point_value = (contract_size * pip_size) * conv_price_inv
                            logger.debug(f"[JPY FIX] Using triangulation via {conv_symbol_inv} @ {conv_price_inv}")
                        else:
                            # Fallback final a heurística EURUSD-style
                            point_value = (contract_size * pip_size) / entry_price
                            logger.warning(f"[JPY FIX] Triangulation failed for {symbol}, using entry_price fallback")
            
            logger.info(
                f"[RISK] {symbol} Point Value calculated: ${point_value:.4f}/pip "
                f"(Contract={contract_size}, Pip={pip_size}, Price={entry_price})"
            )
            
            return point_value
            
        except Exception as e:
            logger.error(f"Error calculating point_value: {e}")
            return 10.0  # Default fallback para forex estándar
    
    def _validate_risk_sanity(
        self,
        lots: float,
        sl_pips: float,
        point_value: float,
        target_usd: float,
        balance: float
    ) -> tuple[bool, str]:
        """
        Capa de validación adicional para evitar errores de cálculo catastróficos.
        """
        actual_risk_usd = lots * sl_pips * point_value
        
        if target_usd > 0:
            # Calculate deviation
            if actual_risk_usd > target_usd:
                # OVER-RISK: Strict tolerance (10%)
                error_pct = (actual_risk_usd - target_usd) / target_usd
                if error_pct > 0.1:
                    return False, f"OVER-RISK: Multiplier error or rounding led to {error_pct:.1%} higher risk (${actual_risk_usd:.2f} vs ${target_usd:.2f})"
            else:
                # UNDER-RISK: Lenient tolerance (30%) - rounding down is safe
                # This is common in small accounts where 1 lot step is > 10% of total risk
                error_pct = (target_usd - actual_risk_usd) / target_usd
                if error_pct > 0.3:
                    return False, f"UNDER-RISK: Deviation too high {error_pct:.1%} (${actual_risk_usd:.2f} vs ${target_usd:.2f})"
        
        # 2. Hard limit por trade (NUNCA más de 2.5% de la cuenta, pase lo que pase)
        risk_of_balance = actual_risk_usd / balance
        if risk_of_balance > 0.03: # Slight increase to avoid edge case rejections on tiny accounts
            return False, f"ABSOLUTE RISK LIMIT REACHED: {risk_of_balance:.1%} of account (${actual_risk_usd:.2f})"
            
        # 3. Lotaje anómalo (Protección contra errores de contract_size)
        if lots > 1000: # Heurística de seguridad
            return False, f"Anomalous lot size detected: {lots:.2f}"
            
        return True, ""

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
        Aplica límites de broker (min/max volume) y redondea al step usando utilidades globales.
        """
        return normalize_volume(position_size, symbol_info)
    
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
        """Activa y persiste el modo lockdown con fecha y balance."""
        if not self.lockdown_mode:
            from datetime import datetime, timezone
            from core_brain.market_utils import to_utc
            now = datetime.now(timezone.utc).isoformat()
            
            self.lockdown_mode = True
            self.storage.update_system_state({
                'lockdown_mode': True,
                'lockdown_date': now,
                'lockdown_balance': self.capital,  # Save balance for recovery tracking
                'consecutive_losses': self.consecutive_losses
            })
            logger.error(
                f"🔒 LOCKDOWN ACTIVATED: {self.consecutive_losses} consecutive losses at {now}. "
                f"Balance: ${self.capital:,.2f}. "
                "Trading disabled until balance recovers or system rests 24h."
            )

    def _deactivate_lockdown(self) -> None:
        """Desactiva y persiste el modo lockdown."""
        if self.lockdown_mode:
            self.lockdown_mode = False
            self.consecutive_losses = 0
            self.storage.update_system_state({
                'lockdown_mode': False,
                'lockdown_date': None,
                'lockdown_balance': None,
                'consecutive_losses': 0
            })
            logger.info("✅ Lockdown DEACTIVATED. Trading resumed.")
    
    def _should_reset_lockdown(
        self, 
        lockdown_date: Optional[str], 
        lockdown_balance: Optional[float],
        current_balance: float
    ) -> tuple[bool, str]:
        """
        Adaptive lockdown reset logic based on market conditions, not calendar.
        
        Resets lockdown if:
        1. Balance recovered (account recovered from drawdown), OR
        2. System rested (24h without trading)
        
        Args:
            lockdown_date: ISO timestamp when lockdown was activated
            lockdown_balance: Account balance when lockdown was activated
            current_balance: Current account balance
            
        Returns:
            tuple[bool, str]: (should_reset, reason)
        """
        from datetime import datetime, timedelta, timezone
        from core_brain.market_utils import to_utc
        
        # Safety: If no lockdown_date, assume it's old and reset
        if not lockdown_date:
            return True, "No lockdown date found (stale lockdown)"
        
        try:
            lockdown_time = to_utc(lockdown_date)
        except (ValueError, TypeError):
            return True, "Invalid lockdown date format"
        
        # Criterion 1: Balance Recovery (PRIORITY)
        # If balance recovered 2% from lockdown level, conditions likely improved
        if lockdown_balance and current_balance >= lockdown_balance * 1.02:
            recovery_pct = ((current_balance - lockdown_balance) / lockdown_balance) * 100
            return True, f"Balance recovered +{recovery_pct:.1f}% from lockdown level"
        
        # Criterion 2: System Rest (24h without trading)
        # Get last trade time from storage
        try:
            conn = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(timestamp) 
                FROM trades 
                WHERE timestamp > ?
            """, (lockdown_date,))
            result = cursor.fetchone()
            last_trade_time = result[0] if result and result[0] else None
            conn.close()
            
            if last_trade_time:
                # There were trades after lockdown - check if system rested since then
                try:
                    last_trade = to_utc(last_trade_time)
                    hours_since_trade = (datetime.now(timezone.utc) - last_trade).total_seconds() / 3600
                    
                    if hours_since_trade >= 24:
                        return True, f"System rested {hours_since_trade:.1f}h without trading"
                except (ValueError, TypeError):
                    pass
            else:
                # No trades since lockdown - check time since lockdown
                hours_since_lockdown = (datetime.now(timezone.utc) - lockdown_time).total_seconds() / 3600
                
                if hours_since_lockdown >= 24:
                    return True, f"System rested {hours_since_lockdown:.1f}h since lockdown"
        
        except Exception as e:
            logger.error(f"Error checking trade history for lockdown reset: {e}")
            # Don't reset on error - be conservative
        
        # Lockdown persists
        hours_since_lockdown = (datetime.now(timezone.utc) - lockdown_time).total_seconds() / 3600
        return False, f"Lockdown active for {hours_since_lockdown:.1f}h - waiting for recovery or 24h rest"
            
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
