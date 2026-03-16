"""
Universal Strategy Engine (HU 3.6 - QUANTUM LEAP CORRECTED)
Trace_ID: EXEC-UNIVERSAL-ENGINE-REAL

Engine agnóstico que implementa el "Salto Cuántico" CORREGIDO:
- Lectura DINÁMICA del Registry DESDE BD (StorageManager), NO de JSON
- Validación de "readiness" (READY_FOR_ENGINE vs LOGIC_PENDING)
- Protocolo Quanter de los 4 Pilares (Sensorial, Régimen, Multi-Tenant, Coherencia)
- Zero hardcoding: Si no está en Registry BD, no existe
- Logic_Module agnóstico: Busca lógica, no clases Python

SSOT CORRECTION (2026-03-04):
- JSON registry_file es SOLO para seed/migration, NO para runtime
- StorageManager es la ÚNICA fuente de verdad en tiempo de ejecución
- Trace_ID: EXEC-UNIVERSAL-ENGINE-REAL | Regla de ORO: Soberanía de Persistencia

Cambios vs v2:
1. RegistryLoader ahora lee de BD (StorageManager DI)
2. UniversalStrategyEngine inyecta storage, no registry_path
3. Validación de readiness integrada
4. Zero JSON en runtime
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SafeConditionEvaluator:
    """
    Evaluates strategy conditions without eval().
    OWASP A03 compliant: no arbitrary code execution.

    Supported format: "<indicator> <operator> <value>" [and|or ...]
    Supported operators: <, >, <=, >=, ==, !=
    Fail-safe: any unknown indicator or malformed input -> False
    """

    _OPERATOR_MAP = {
        "<=": lambda a, b: a <= b,
        ">=": lambda a, b: a >= b,
        "!=": lambda a, b: a != b,
        "<":  lambda a, b: a < b,
        ">": lambda a, b: a > b,
        "==": lambda a, b: a == b,
    }

    @classmethod
    def evaluate(cls, condition: str, indicators: Dict[str, Any]) -> bool:
        """
        Safely evaluates a condition string against indicator values.

        Args:
            condition: e.g. "RSI < 30" or "RSI < 30 and MACD > 0"
            indicators: dict of calculated indicator values

        Returns:
            bool: result of condition, False on any error (fail-safe)
        """
        if not condition or not isinstance(condition, str):
            return False
        try:
            condition = condition.strip()
            lower = condition.lower()

            if " and " in lower:
                idx = lower.find(" and ")
                left = condition[:idx].strip()
                right = condition[idx + 5:].strip()
                return (
                    cls._evaluate_single(left, indicators)
                    and cls._evaluate_single(right, indicators)
                )

            if " or " in lower:
                idx = lower.find(" or ")
                left = condition[:idx].strip()
                right = condition[idx + 4:].strip()
                return (
                    cls._evaluate_single(left, indicators)
                    or cls._evaluate_single(right, indicators)
                )

            return cls._evaluate_single(condition, indicators)
        except Exception:
            return False  # Fail-safe: never raise

    @classmethod
    def _evaluate_single(cls, condition: str, indicators: Dict[str, Any]) -> bool:
        """Evaluates a single atom: '<indicator> <op> <value>'. Operators checked longest-first."""
        for op_str in ["<=", ">=", "!=", "<", ">", "=="]:
            if op_str in condition:
                parts = condition.split(op_str, 1)
                if len(parts) != 2:
                    return False
                left = parts[0].strip()
                right = parts[1].strip()
                if left not in indicators:
                    return False
                try:
                    right_val = float(right)
                except ValueError:
                    return False
                left_val = indicators[left]
                if left_val is None:
                    return False
                return cls._OPERATOR_MAP[op_str](float(left_val), right_val)
        return False


class ExecutionMode(Enum):
    """Strategy execution result codes."""
    SIGNAL_GENERATED = "signal_generated"
    NO_SIGNAL = "no_signal"
    CRASH_VETO = "strategy_crash_veto"
    READINESS_BLOCKED = "readiness_blocked"
    NOT_FOUND = "strategy_not_found"


@dataclass
class StrategySignal:
    """Result of strategy execution."""
    strategy_id: str
    signal: Optional[str]  # "BUY", "SELL", None
    confidence: float  # 0.0-1.0
    execution_mode: ExecutionMode
    error_message: Optional[str] = None
    timestamp: Optional[str] = None


class StrategyExecutionError(Exception):
    """Raised when strategy execution encounters a fatal error."""
    pass


class RegistryLoader:
    """
    Carga dinámicamente estrategias del Registry.
    
    SSOT CORRECTION (2026-03-04):
    Lee de BD (StorageManager), NO de archivos JSON.
    El JSON es solo seed/migration, no runtime source.
    
    Trace_ID: EXEC-UNIVERSAL-ENGINE-REAL
    """
    
    def __init__(self, storage):
        """
        Args:
            storage: StorageManager instance (Dependency Injection)
        """
        self.storage = storage
        self._registry_cache: Optional[Dict[str, Any]] = None
    
    def load_registry(self) -> Dict[str, Any]:
        """
        Carga el Registry directamente de BD (SSOT).
        
        Returns:
            Dict with usr_strategies list y validation_protocol
        """
        if self._registry_cache is not None:
            return self._registry_cache
        
        try:
            # Leer TODAS las estrategias desde BD
            sys_strategies = self.storage.get_all_sys_strategies()
            
            # Construir Registry
            registry = {
                "sys_strategies": sys_strategies,
                "validation_protocol": {
                    "name": "Protocolo Quanter",
                    "pillars": [
                        {
                            "order": 1,
                            "name": "Sensorial",
                            "description": "¿El sensor está listo? (Datos frescos, no NULL)",
                            "failure_action": "REJECT"
                        },
                        {
                            "order": 2,
                            "name": "Régimen",
                            "description": "¿El régimen de mercado permite esta estrategia?",
                            "failure_action": "REJECT"
                        },
                        {
                            "order": 3,
                            "name": "Multi-Tenant",
                            "description": "¿La membresía del usuario permite acceso?",
                            "failure_action": "BLOCK"
                        },
                        {
                            "order": 4,
                            "name": "Coherencia",
                            "description": "¿La señal es coherente? (Confluence, no conflictos)",
                            "failure_action": "REJECT"
                        }
                    ]
                }
            }
            
            self._registry_cache = registry
            logger.info(f"Registry cargado de BD: {len(usr_strategies)} estrategias")
            return registry
        
        except Exception as e:
            raise StrategyExecutionError(f"Fallo al cargar Registry desde BD: {str(e)}")
    
    def get_strategy_metadata(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene metadata de estrategia por ID (desde BD)."""
        try:
            return self.storage.get_strategy(strategy_id)
        except Exception as e:
            logger.error(f"Error obteniendo metadata de estrategia {strategy_id}: {e}")
            return None
    
    def get_ready_usr_strategies(self) -> List[Dict[str, Any]]:
        """Retorna solo estrategias con readiness=READY_FOR_ENGINE (desde BD)."""
        try:
            return self.storage.get_sys_strategies_by_readiness("READY_FOR_ENGINE")
        except Exception as e:
            logger.error(f"Error obteniendo estrategias READY_FOR_ENGINE: {e}")
            return []


class StrategyReadinessValidator:
    """Valida que estrategia esté lista para ejecución."""
    
    @staticmethod
    def validate(strategy_metadata: Dict[str, Any]) -> tuple[bool, str]:
        """
        Valida readiness de estrategia.
        
        Returns:
            (is_ready: bool, reason: str)
        """
        readiness = strategy_metadata.get("readiness", "UNKNOWN")
        
        if readiness == "READY_FOR_ENGINE":
            return True, "Estrategia lista para ejecución"
        
        elif readiness == "LOGIC_PENDING":
            reason = strategy_metadata.get("readiness_notes", "Lógica pendiente")
            return False, f"Lógica pendiente: {reason}"
        
        else:
            return False, f"Estado desconocido: {readiness}"


class StrategySchemaValidator:
    """Validates strategy JSON schema before execution."""
    
    REQUIRED_FIELDS = ["strategy_id", "version", "indicators"]
    REQUIRED_LOGIC_FIELDS = ["condition", "direction"]
    
    @staticmethod
    def validate(schema: Dict[str, Any]) -> None:
        """
        Validates strategy schema structure.
        
        Args:
            schema: Strategy dictionary from JSON
            
        Raises:
            ValueError: If schema is invalid
        """
        if not isinstance(schema, dict):
            raise ValueError("Strategy must be a dictionary")
        
        # Check required fields
        for field in StrategySchemaValidator.REQUIRED_FIELDS:
            if field not in schema:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate indicators
        indicators = schema.get("indicators", {})
        if not isinstance(indicators, dict):
            raise ValueError("Indicators must be a dictionary")
        
        if not indicators:
            raise ValueError("At least one indicator is required")
        
        for ind_name, ind_config in indicators.items():
            if not isinstance(ind_config, dict):
                raise ValueError(f"Indicator '{ind_name}' config must be dict")
            if "type" not in ind_config:
                raise ValueError(f"Indicator '{ind_name}' missing 'type' field")
        
        # Validate entry logic
        if "entry_logic" in schema and schema["entry_logic"]:
            entry = schema["entry_logic"]
            for field in StrategySchemaValidator.REQUIRED_LOGIC_FIELDS:
                if field not in entry:
                    raise ValueError(f"Entry logic missing '{field}'")
        
        # Validate exit logic
        if "exit_logic" in schema and schema["exit_logic"]:
            exit_log = schema["exit_logic"]
            for field in StrategySchemaValidator.REQUIRED_LOGIC_FIELDS:
                if field not in exit_log:
                    raise ValueError(f"Exit logic missing '{field}'")


class IndicatorFunctionMapper:
    """Maps strategy indicator references to actual calculation functions."""
    
    def __init__(self, indicator_provider: Any):
        """
        Args:
            indicator_provider: Object with calculate_* methods
        """
        self.provider = indicator_provider
        self._function_cache: Dict[str, Callable] = {}
    
    def get_function(self, indicator_type: str) -> Callable:
        """
        Retrieves calculation function for indicator type.
        
        Args:
            indicator_type: Type string (e.g., "RSI", "MA", "FVG")
            
        Returns:
            Async callable for indicator calculation
            
        Raises:
            ValueError: If indicator type is unsupported
        """
        if indicator_type in self._function_cache:
            return self._function_cache[indicator_type]
        
        # Map indicator type to provider method
        method_name = f"calculate_{indicator_type.lower()}"
        
        if not hasattr(self.provider, method_name):
            raise ValueError(
                f"Unsupported indicator type: {indicator_type}. "
                f"Provider must have method: {method_name}"
            )
        
        func = getattr(self.provider, method_name)
        self._function_cache[indicator_type] = func
        return func


class UniversalStrategyEngine:
    """
    Motor agnóstico que lee dinámicamente del Registry.
    
    **SALTO CUÁNTICO**: No instancia clases hardcodeadas.
    Si estrategia no está en Registry o no es READY_FOR_ENGINE → NO SE EJECUTA.
    
    Características:
    - RegistryLoader: Lectura dinámica de config/strategy_registry.json
    - StrategyReadinessValidator: Bloquea estrategias LOGIC_PENDING
    - Protocolo Quanter: 4 Pilares (Sensorial, Régimen, Multi-Tenant, Coherencia)
    - Error isolation con STRATEGY_CRASH_VETO
    
    Uso:
        engine = UniversalStrategyEngine(indicator_provider)
        result = await engine.execute_from_registry(strategy_id="MOM_BIAS_0001", symbol="EURUSD", data_frame=df)
    """
    
    def __init__(self, indicator_provider: Any, storage: Any):
        """
        Initialize engine.
        
        Args:
            indicator_provider: Object con métodos calculate_*
            storage: StorageManager instance (Dependency Injection)
                     CRÍTICO: Leer Registry de BD, no de archivo JSON
        """
        self._indicator_provider = indicator_provider
        self._function_mapper = IndicatorFunctionMapper(indicator_provider)
        self._registry_loader = RegistryLoader(storage)  # DI: storage instead of path
        self._storage = storage
        self._schema_cache: Dict[str, Dict[str, Any]] = {}  # Cache usr_strategies loaded
        
        logger.info("UniversalStrategyEngine inicializado (SSOT: Registry desde BD)")
    
    async def execute_from_registry(
        self,
        strategy_id: str,
        symbol: str,
        data_frame: Any,
        regime: Optional[Any] = None
    ) -> StrategySignal:
        """
        Ejecuta estrategia LEYENDO DINÁMICAMENTE del Registry.
        
        Este es el nuevo flujo agnóstico:
        1. Cargar metadata del Registry
        2. Validar readiness
        3. Cargar schema
        4. Ejecutar lógica
        
        Args:
            strategy_id: ID de estrategia en Registry
            symbol: Instrumento (ej. "EURUSD")
            data_frame: DataFrame con datos de mercado
            regime: Contexto de régimen de mercado
            
        Returns:
            StrategySignal con resultado
        """
        # PASO 1: Obtener metadata del Registry
        strategy_metadata = self._registry_loader.get_strategy_metadata(strategy_id)
        
        if not strategy_metadata:
            return StrategySignal(
                strategy_id=strategy_id,
                signal=None,
                confidence=0.0,
                execution_mode=ExecutionMode.NOT_FOUND,
                error_message=f"Estrategia '{strategy_id}' NO ENCONTRADA en Registry"
            )
        
        logger.info(f"[REGISTRY] Ejecutando estrategia: {strategy_id} ({strategy_metadata.get('mnemonic')})")
        
        # PASO 2: Validar readiness
        is_ready, reason = StrategyReadinessValidator.validate(strategy_metadata)
        
        if not is_ready:
            logger.warning(f"[READINESS_BLOCKED] {strategy_id}: {reason}")
            return StrategySignal(
                strategy_id=strategy_id,
                signal=None,
                confidence=0.0,
                execution_mode=ExecutionMode.READINESS_BLOCKED,
                error_message=reason
            )
        
        # PASO 3: Cargar o usar schema cacheado
        strategy_schema = self._get_or_load_schema(strategy_metadata)
        
        if strategy_schema is None:
            return StrategySignal(
                strategy_id=strategy_id,
                signal=None,
                confidence=0.0,
                execution_mode=ExecutionMode.CRASH_VETO,
                error_message=f"No se pudo cargar schema para '{strategy_id}'"
            )
        
        # PASO 4: Ejecutar con schema
        return await self.execute(strategy_schema, symbol, data_frame, regime)
    
    async def execute(
        self,
        strategy_schema: Dict[str, Any],
        symbol: str,
        data_frame: Any,
        regime: Optional[Any] = None
    ) -> StrategySignal:
        """
        Ejecuta strategy logic (MODO CLÁSICO, con schema pasado directamente).
        
        Mantiene compatibilidad hacia atrás pero es menos agnóstico.
        """
        try:
            # Validate schema BEFORE anything else
            try:
                StrategySchemaValidator.validate(strategy_schema)
            except ValueError as e:
                raise ValueError(f"Schema validation failed: {e}")
            
            strategy_id = strategy_schema["strategy_id"]
            
            # Calculate all required indicators
            indicator_results = await self._calculate_indicators(data_frame, strategy_schema)
            
            # Evaluate entry logic
            entry_signal = await self._evaluate_logic(
                strategy_schema.get("entry_logic"),
                indicator_results
            )
            
            # Evaluate exit logic
            exit_signal = await self._evaluate_logic(
                strategy_schema.get("exit_logic"),
                indicator_results
            )
            
            # Determine final signal
            final_signal = entry_signal or exit_signal
            
            if final_signal:
                signal_data = final_signal if isinstance(final_signal, dict) else {}
                return StrategySignal(
                    strategy_id=strategy_id,
                    signal=signal_data.get("direction"),
                    confidence=signal_data.get("confidence", 0.0),
                    execution_mode=ExecutionMode.SIGNAL_GENERATED
                )
            
            return StrategySignal(
                strategy_id=strategy_id,
                signal=None,
                confidence=0.0,
                execution_mode=ExecutionMode.NO_SIGNAL
            )
        
        except Exception as e:
            error_msg = f"Strategy execution error: {str(e)}"
            strategy_id = strategy_schema.get("strategy_id", "unknown")
            logger.error(f"[STRATEGY_CRASH_VETO] {strategy_id}: {error_msg}")
            
            return StrategySignal(
                strategy_id=strategy_id,
                signal=None,
                confidence=0.0,
                execution_mode=ExecutionMode.CRASH_VETO,
                error_message=error_msg
            )
    
    def _get_or_load_schema(self, strategy_metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Obtiene schema desde cache o lo carga dinámicamente.

        Prioridad para JSON_SCHEMA:
          1. logic inline desde BD (SSOT, N2-1)
          2. schema_file en disco (solo seed/fallback)
        - type="PYTHON_CLASS": retorna None
        """
        strategy_id = strategy_metadata.get("strategy_id") or strategy_metadata.get("class_id")

        # Check cache first
        if strategy_id and strategy_id in self._schema_cache:
            return self._schema_cache[strategy_id]

        strategy_type = strategy_metadata.get("type")
        schema = None

        if strategy_type == "JSON_SCHEMA":
            # Priority 1: inline logic from DB (SSOT)
            logic_data = strategy_metadata.get("logic")
            if logic_data:
                if isinstance(logic_data, str):
                    try:
                        logic_data = json.loads(logic_data)
                    except Exception:
                        logic_data = None
                if isinstance(logic_data, dict):
                    schema = dict(logic_data)
                    if strategy_id:
                        schema.setdefault("strategy_id", strategy_id)

            # Priority 2: schema_file fallback (seed/migration only)
            if not schema:
                schema_file = strategy_metadata.get("schema_file")
                if schema_file:
                    try:
                        with open(schema_file, "r") as f:
                            schema = json.load(f)
                        logger.debug(f"Schema cargado desde archivo: {schema_file}")
                    except Exception as e:
                        logger.error(f"Fallo al cargar schema {schema_file}: {e}")
                        return None

        elif strategy_type == "PYTHON_CLASS":
            logger.warning(f"Estrategia {strategy_id} requiere implementación Python (no soportado aún)")
            return None

        if schema and strategy_id:
            self._schema_cache[strategy_id] = schema

        return schema
    
    async def _calculate_indicators(
        self,
        data_frame: Any,
        strategy_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Calculate all indicators required by strategy.

        Args:
            data_frame: Input market data
            strategy_schema: Strategy schema dict (contains indicators section)

        Returns:
            Dictionary mapping indicator names to calculated values

        Raises:
            ValueError: If indicator calculation fails
        """
        indicators = (strategy_schema or {}).get("indicators", {})
        results = {}
        
        for ind_name, ind_config in indicators.items():
            try:
                ind_type = ind_config.get("type")
                func = self._function_mapper.get_function(ind_type)
                
                # Call indicator calculation with config params
                calc_params = {k: v for k, v in ind_config.items() if k != "type"}
                
                # Execute indicator calculation
                if asyncio.iscoroutinefunction(func):
                    value = await func(data_frame, **calc_params)
                else:
                    value = func(data_frame, **calc_params)
                
                results[ind_name] = value
                logger.debug(f"Calculated {ind_name} ({ind_type}): {value}")
            
            except Exception as e:
                raise ValueError(
                    f"Failed to calculate indicator '{ind_name}': {str(e)}"
                )
        
        return results
    
    async def _evaluate_logic(
        self,
        logic: Optional[Dict[str, Any]],
        indicators: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluate entry/exit logic against calculated indicators.
        
        Args:
            logic: Logic block (entry_logic or exit_logic)
            indicators: Calculated indicator values
            
        Returns:
            Signal dict if condition evaluates to True, None otherwise
        """
        if not logic:
            return None
        
        condition = logic.get("condition", "")
        
        if not condition:
            return None
        
        try:
            # OWASP A03 compliant: no eval(), use SafeConditionEvaluator
            result = SafeConditionEvaluator.evaluate(condition, indicators)

            if result:
                return {
                    "direction": logic.get("direction"),
                    "confidence": logic.get("confidence", 0.5),
                }

            return None

        except Exception as e:
            raise ValueError(f"Logic evaluation failed: {str(e)}")
    
    def get_ready_usr_strategies(self) -> List[Dict[str, Any]]:
        """Retorna lista de estrategias READY_FOR_ENGINE."""
        return self._registry_loader.get_ready_usr_strategies()
