"""
Strategy Engine Factory - Dynamic Strategy Loader Service Layer
TRACE_ID: FACTORY-STRATEGY-ENGINES-2026

Orquesta la carga de TODAS las estrategias desde BD (SSOT) en tiempo de inicialización.
Compila cada estrategia UNA SOLA VEZ y conserva en memoria para reutilización eficiente.

GOBERNANZA:
- DEVELOPMENT_GUIDELINES 1.6: Service Layer separado de routers
- DEVELOPMENT_GUIDELINES 1.4: Explora primero antes de crear
- DEVELOPMENT_GUIDELINES 4.3: Try/except con comportamiento definido
- MANIFESTO II.3-II.4: StrategyRegistry v2.0 - compilación única

PRINCIPIOS:
1. Zero hardcoding: Todas las estrategias desde BD
2. Compilación única: Cada estrategia se instancia UNA sola vez en __init__()
3. Agnóstico: Funciona con BaseStrategy y UniversalStrategyEngine
4. Resiliente: Falta dependencia = skip, no bloquea otras estrategias
5. Trazable: Logging exhaustivo de cada paso
"""

import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StrategyDependency:
    """Especificación de dependencia de una estrategia."""
    name: str
    available: bool = False
    reason: Optional[str] = None


class StrategyEngineFactory:
    """
    Factory Service que instancia estrategias desde BD.
    
    Responsabilidades:
    1. Leer todas las estrategias de tabla `usr_strategies` (SSOT)
    2. Filtrar por readiness (READY_FOR_ENGINE)
    3. Validar dependencias pre-instanciación
    4. Instanciar dinámicamente (BaseStrategy o UniversalStrategyEngine)
    5. Retornar Dict en memoria para lookup O(1)
    
    Inyección de Dependencias Obligatoria:
    - storage: StorageManager (para leer tabla usr_strategies)
    - config: Dict con parámetros dinámicos (dynamic_params)
    """
    
    def __init__(
        self,
        storage: Any,  # StorageManager (DI)
        config: Optional[Dict[str, Any]] = None,
        available_sensors: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ):
        """
        Inicializa el factory.
        
        Args:
            storage: StorageManager instance (inyectada) - implementa SSOT (Dominio 08)
            config: Configuración dinámica (dynamic_params)
            available_sensors: Dict de sensores disponibles en MainOrchestrator {name: instance}
            user_id: User identifier para multi-tenancy (inyección a estrategias). Ver Dominio 01.
        """
        self.storage = storage
        self.config = config or {}
        self.available_sensors = available_sensors or {}
        self.user_id = user_id or (storage.user_id if hasattr(storage, 'user_id') else None)
        self.active_engines: Dict[str, Any] = {}
        self.load_errors: Dict[str, str] = {}
    
    def instantiate_all_sys_strategies(self) -> Dict[str, Any]:
        """
        Carga TODAS las estrategias desde BD e instancia aquellas que cumplan:
        1. readiness = READY_FOR_ENGINE (no LOGIC_PENDING)
        2. Todas sus dependencias están disponibles
        
        Returns:
            Dict[strategy_id: engine_instance] en memoria
            
        Raises:
            RuntimeError: Si no se logra instanciar NINGUNA estrategia
        """
        logger.info("[FACTORY] Iniciando carga dinámica de estrategias desde BD...")
        
        try:
            # Paso 1: Leer todas las estrategias desde tabla `sys_strategies` (SSOT global)
            all_sys_strategies = self.storage.get_all_sys_strategies()
            logger.info(f"[FACTORY] ✓ Leídas {len(all_sys_strategies)} estrategias de BD")
            
        except Exception as e:
            logger.error(f"[FACTORY] ✗ Error al leer tabla sys_strategies: {e}")
            raise RuntimeError(f"[FACTORY] CRITICAL: No se pudo acceder a tabla sys_strategies: {e}")
        
        if not all_sys_strategies:
            logger.warning("[FACTORY] ⚠ Tabla sys_strategies vacía - Sin estrategias pre-cargadas")
            return {}
        
        # Paso 2: Filtrar, validar y instanciar cada estrategia
        for strategy_spec in all_sys_strategies:
            try:
                self._load_single_strategy(strategy_spec)
            except Exception as e:
                # Capturar error pero continuar con otras estrategias
                strategy_id = strategy_spec.get("class_id", "UNKNOWN")
                if isinstance(e, ValueError) and "readiness=LOGIC_PENDING" in str(e):
                    logger.warning(f"[FACTORY] ⊘ {strategy_id}: {e} [expected governance block]")
                else:
                    logger.error(f"[FACTORY] ✗ {strategy_id}: {e}")
                self.load_errors[strategy_id] = str(e)
        
        # Paso 3: Validar resultado
        if not self.active_engines:
            logger.error(
                f"[FACTORY] ✗ CRÍTICO: No se instanció ninguna estrategia. "
                f"Errores: {self.load_errors}"
            )
            raise RuntimeError("[FACTORY] CRITICAL: No sys_strategies instantiated")
        
        logger.info(
            f"[FACTORY] ✓ Carga completada: {len(self.active_engines)} estrategias activas, "
            f"{len(self.load_errors)} skipped"
        )
        
        return self.active_engines
    
    def _load_single_strategy(self, strategy_spec: Dict[str, Any]) -> None:
        """
        Carga una estrategia individual.
        
        Args:
            strategy_spec: Dict con class_id, type, readiness, etc.
            
        Raises:
            Exception: Si hay error en validación o instanciación
        """
        strategy_id = strategy_spec.get("class_id", "UNKNOWN")
        strategy_type = strategy_spec.get("type", "UNKNOWN")
        readiness = strategy_spec.get("readiness", "UNKNOWN")
        
        # Validación 1: ¿Está lista? (Jerarquía: LOGIC_PENDING BLOQUEA TODO)
        if readiness == "LOGIC_PENDING":
            logger.warning(
                f"[FACTORY] ⊘ {strategy_id}: readiness=LOGIC_PENDING (código no validado) → BLOQUEADO per § 7.2"
            )
            raise ValueError(f"Strategy {strategy_id} blocked: readiness=LOGIC_PENDING (code not validated yet)")
        
        if readiness != "READY_FOR_ENGINE":
            logger.warning(
                f"[FACTORY] ⊘ {strategy_id}: readiness={readiness} (esperado READY_FOR_ENGINE)"
            )
            raise ValueError(f"Strategy {strategy_id} not ready: readiness={readiness}")
        
        # Validación 2: ¿Tipo válido?
        if strategy_type not in ["PYTHON_CLASS", "JSON_SCHEMA"]:
            logger.warning(f"[FACTORY] ⊘ {strategy_id}: type={strategy_type} inválido")
            raise ValueError(f"Unknown strategy type: {strategy_type}")
        
        # Validación 3: ¿Execution_mode es válido? (Lee de usr_performance)
        execution_mode = self._get_execution_mode(strategy_id)
        if execution_mode not in ["SHADOW", "LIVE", "QUARANTINE", "BACKTEST"]:
            logger.warning(
                f"[FACTORY] ⊘ {strategy_id}: execution_mode={execution_mode} inválido"
            )
            raise ValueError(f"Unknown execution_mode for {strategy_id}: {execution_mode}")
        
        logger.debug(f"[FACTORY] {strategy_id}: execution_mode={execution_mode}")
        
        # Validación 4: ¿Dependencias disponibles? (Solo para PYTHON_CLASS)
        # JSON_SCHEMA usr_strategies se cargan dinámicamente sin validación previa de sensores
        if strategy_type == "PYTHON_CLASS":
            required_sensors = strategy_spec.get("required_sensors", [])
            missing_sensors = self._validate_dependencies(strategy_id, required_sensors)
            
            if missing_sensors:
                logger.warning(
                    f"[FACTORY] ⊘ {strategy_id}: Sensors faltantes={missing_sensors}"
                )
                raise ValueError(f"Missing sensors: {missing_sensors}")
        
        # Paso 4: Instanciar según tipo
        if strategy_type == "PYTHON_CLASS":
            engine = self._instantiate_python_strategy(strategy_spec)
            # Inyectar snapshot DB-backed de metadata estratégica (SSOT)
            self._inject_metadata_snapshot(engine, strategy_spec)
        elif strategy_type == "JSON_SCHEMA":
            engine = self._instantiate_json_schema_strategy(strategy_spec)
        else:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
        
        # Fase 5: Aplicar execution_mode flags (QUARANTINE = trading deshabilitado)
        if execution_mode == "QUARANTINE":
            # Marcar estrategia como en cuarentena (no enviar órdenes)
            if hasattr(engine, 'no_send_usr_orders'):
                engine.no_send_usr_orders = True
            engine.execution_mode = "QUARANTINE"
            logger.info(f"[FACTORY] 🔒 {strategy_id}: QUARANTINE mode activated (no_send_usr_orders=True)")
        elif execution_mode == "LIVE":
            # Modo LIVE = trading habilitado
            if hasattr(engine, 'no_send_usr_orders'):
                engine.no_send_usr_orders = False
            engine.execution_mode = "LIVE"
            logger.info(f"[FACTORY] ✓ {strategy_id}: LIVE mode (usr_orders enabled)")
        elif execution_mode == "SHADOW":
            # Modo SHADOW = testing sin enviar órdenes
            if hasattr(engine, 'no_send_usr_orders'):
                engine.no_send_usr_orders = True
            engine.execution_mode = "SHADOW"
            logger.info(f"[FACTORY] 👁️  {strategy_id}: SHADOW mode (testing, no live usr_orders)")
        elif execution_mode == "BACKTEST":
            # Modo BACKTEST = estrategia en evaluación, sin órdenes live (igual que SHADOW)
            if hasattr(engine, 'no_send_usr_orders'):
                engine.no_send_usr_orders = True
            engine.execution_mode = "BACKTEST"
            logger.info(f"[FACTORY] 🔬 {strategy_id}: BACKTEST mode (bajo evaluación, no live usr_orders)")
        
        # Guardar en Dict
        self.active_engines[strategy_id] = engine
        logger.info(f"[FACTORY] ✓ {strategy_id} compilada a memoria (type={strategy_type}, mode={execution_mode})")
    
    def _validate_dependencies(
        self,
        strategy_id: str,
        required_sensors: List[str]
    ) -> List[str]:
        """
        Valida que todas las dependencias (sensors) estén disponibles.
        
        Args:
            strategy_id: Para logging
            required_sensors: Lista de nombres de sensores requeridos (o pipe-separated string)
            
        Returns:
            Lista de sensores faltantes (vacía = todas disponibles)
        """
        missing = []
        
        # Handle both list and pipe-separated string formats
        if isinstance(required_sensors, str):
            sensor_list = [s.strip() for s in required_sensors.split("|") if s.strip()]
        else:
            sensor_list = required_sensors or []
        
        # JSON_SCHEMA usr_strategies don't require sensors (they use indicator_provider)
        if not sensor_list:
            return []
        
        for sensor_name in sensor_list:
            if sensor_name not in self.available_sensors:
                missing.append(sensor_name)
                logger.debug(f"[FACTORY] ⊘ {strategy_id}: Sensor faltante={sensor_name}")
            else:
                logger.debug(f"[FACTORY] ✓ {strategy_id}: Sensor disponible={sensor_name}")
        
        return missing
    
    def _get_execution_mode(self, strategy_id: str) -> str:
        """
        Obtiene el modo de ejecución desde sys_strategies.mode (SSOT canónico).

        Lee exclusivamente desde sys_strategies para evitar drift con sys_signal_ranking.
        sys_signal_ranking.execution_mode es un dato derivado e histórico; no gobierna
        la autorización de carga inicial.

        Args:
            strategy_id: Identificador de la estrategia.

        Returns:
            execution_mode (SHADOW | LIVE | QUARANTINE | BACKTEST).
            Retorna SHADOW si el valor es inválido o hay error de DB (safe default).

        Trace_ID: SSOT-EXECMODE-DRIFT-FIX-2026-04-09
        """
        try:
            mode = self.storage.get_strategy_lifecycle_mode(strategy_id)
            if mode in ("SHADOW", "LIVE", "QUARANTINE", "BACKTEST"):
                return mode
            # Valor inesperado (ej: NULL migrado, bug de seed) → safe default
            logger.error(
                f"[FACTORY] ⚠️  {strategy_id}: mode='{mode}' no reconocido, "
                f"usando SHADOW como safe default"
            )
            return "SHADOW"
        except Exception as e:
            logger.error(f"[FACTORY] ✗ {strategy_id}: Error leyendo sys_strategies: {e}")
            return "SHADOW"  # Safe default on error
    
    def _instantiate_python_strategy(self, strategy_spec: Dict[str, Any]) -> Any:
        """
        Instancia una estrategia PYTHON_CLASS con inyección inteligente de dependencias.
        
        Utiliza introspección para determinar qué parámetros requiere el constructor
        y los obtiene de available_sensors + storage.
        
        Args:
            strategy_spec: Dict con class_file, class_name, etc.
            
        Returns:
            Instancia de BaseStrategy (compilada una sola vez)
            
        Raises:
            ImportError: Si no encuentra el archivo o la clase
            AttributeError: Si la clase no existe
            TypeError: Si el constructor tiene parámetros incorrectos
        """
        import inspect
        
        strategy_id = strategy_spec.get("class_id", "UNKNOWN")
        class_file = strategy_spec.get("class_file")
        class_name = strategy_spec.get("class_name")
        
        if not class_file or not class_name:
            raise ValueError(f"{strategy_id}: Missing class_file or class_name in registry")
        
        logger.debug(f"[FACTORY] ↓ {strategy_id}: Importando {class_file}.{class_name}...")
        
        try:
            # Convertir ruta a módulo Python
            module_path = class_file.replace("/", ".").replace(".py", "")
            
            # Importar módulo
            module = __import__(module_path, fromlist=[class_name])
            
            # Obtener clase
            StrategyClass = getattr(module, class_name)
            
            logger.debug(f"[FACTORY] ↓ {strategy_id}: Clase {class_name} encontrada, instanciando...")
            
            # Usar introspección para obtener los parámetros del constructor
            sig = inspect.signature(StrategyClass.__init__)
            required_params = {}
            
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                
                # Buscar en available_sensors
                if param_name in self.available_sensors:
                    required_params[param_name] = self.available_sensors[param_name]
                    logger.debug(f"[FACTORY] ↓ {strategy_id}: {param_name} ← {type(self.available_sensors[param_name]).__name__}")
                
                # Si es storage_manager, pasar self.storage
                elif param_name == "storage_manager":
                    required_params[param_name] = self.storage
                    logger.debug(f"[FACTORY] ↓ {strategy_id}: storage_manager ← StorageManager")
                
                # Si es config, pasar self.config
                elif param_name == "config":
                    required_params[param_name] = self.config
                    logger.debug(f"[FACTORY] ↓ {strategy_id}: config ← config dict")
                
                # Si es trace_id, generar uno
                elif param_name == "trace_id":
                    required_params[param_name] = f"INIT-{strategy_id}-FACTORY"
                    logger.debug(f"[FACTORY] ↓ {strategy_id}: trace_id ← generated")
                
                # Si es user_id, inyectar si está disponible
                elif param_name == "user_id":
                    required_params[param_name] = self.user_id
                    logger.debug(f"[FACTORY] ↓ {strategy_id}: user_id ← {self.user_id}")
                
                # Si tiene default, no es requerido
                elif param.default != inspect.Parameter.empty:
                    logger.debug(f"[FACTORY] ↓ {strategy_id}: {param_name} tiene default, saltando")
                    continue
                
                # Si no encontramos el parámetro y es requerido
                elif param.default == inspect.Parameter.empty:
                    logger.warning(f"[FACTORY] ⊘ {strategy_id}: Parámetro '{param_name}' no encontrado")
            
            # Instanciar con los parámetros inyectados
            logger.debug(f"[FACTORY] ↓ {strategy_id}: Instanciando con params: {list(required_params.keys())}")
            instance = StrategyClass(**required_params)
            
            logger.debug(f"[FACTORY] ✓ {strategy_id}: Instancia creada")
            return instance
            
        except ImportError as e:
            raise ImportError(f"Cannot import {class_file}: {e}")
        except AttributeError as e:
            raise AttributeError(f"Class {class_name} not found in {class_file}: {e}")
        except TypeError as e:
            raise TypeError(f"Error instantiating {class_name}: {e}")
        except Exception as e:
            raise Exception(f"Unexpected error instantiating {strategy_id}: {e}")
    
    def _instantiate_json_schema_strategy(self, strategy_spec: Dict[str, Any]) -> Any:
        """
        Instancia una estrategia JSON_SCHEMA usando UniversalStrategyEngine.
        
        UniversalStrategyEngine requiere indicator_provider (DI obligatoria).
        Metadata se carga dinámicamente en runtime via strategy_id.
        
        Args:
            strategy_spec: Dict con class_id, logic, indicators, etc.
            
        Returns:
            Instancia de UniversalStrategyEngine wrapper
        """
        strategy_id = strategy_spec.get("class_id", "UNKNOWN")
        
        logger.debug(f"[FACTORY] ↓ {strategy_id}: Creando UniversalStrategyEngine...")
        
        try:
            from core_brain.universal_strategy_engine import UniversalStrategyEngine
            from core_brain.tech_utils import TechnicalAnalyzer
            
            # Create indicator_provider (TechnicalAnalyzer instance)
            # UniversalStrategyEngine needs this for indicator calculations
            indicator_provider = TechnicalAnalyzer()
            
            # UniversalStrategyEngine requiere indicator_provider
            instance = UniversalStrategyEngine(
                indicator_provider=indicator_provider,
                storage=self.storage
            )

            # Pre-load spec into engine cache — avoids DB round-trip per cycle (N2-1)
            logic_data = strategy_spec.get("logic")
            if logic_data:
                if isinstance(logic_data, str):
                    try:
                        logic_data = json.loads(logic_data)
                    except Exception:
                        logic_data = None
                if isinstance(logic_data, dict):
                    schema = dict(logic_data)
                    schema.setdefault("strategy_id", strategy_id)
                    instance._schema_cache[strategy_id] = schema
                    logger.debug(f"[FACTORY] ✓ {strategy_id}: schema pre-loaded into engine cache")

            logger.debug(f"[FACTORY] ✓ {strategy_id}: UniversalStrategyEngine creado")
            return instance
            
        except Exception as e:
            raise Exception(f"Error creating UniversalStrategyEngine for {strategy_id}: {e}")
    
    def _inject_metadata_snapshot(
        self,
        instance: Any,
        strategy_spec: Dict[str, Any]
    ) -> None:
        """
        Inyecta snapshot de metadata estratégica DB-backed en una instancia PYTHON_CLASS.

        Construye un snapshot inmutable con affinity_scores, market_whitelist y
        execution_params leídos desde sys_strategies (SSOT). Lo entrega mediante
        apply_metadata_snapshot() si la instancia lo implementa.

        Estrategias que no implementen el método siguen funcionando con sus
        constantes locales (compatibilidad regresiva, sin excepción).

        Args:
            instance: Instancia de BaseStrategy recién creada.
            strategy_spec: Dict de sys_strategies con metadata ya parseada.

        Trace_ID: EDGE-STRATEGY-SSOT-SYNC-2026-04-13
        """
        if not hasattr(instance, "apply_metadata_snapshot"):
            return

        strategy_id = strategy_spec.get("class_id", "UNKNOWN")

        # Parsear execution_params desde JSON si llega como string
        raw_exec = strategy_spec.get("execution_params") or "{}"
        if isinstance(raw_exec, str):
            try:
                execution_params: Dict[str, Any] = json.loads(raw_exec)
            except Exception:
                execution_params = {}
        else:
            execution_params = raw_exec if isinstance(raw_exec, dict) else {}

        snapshot: Dict[str, Any] = {
            "affinity_scores":  strategy_spec.get("affinity_scores") or {},
            "market_whitelist": strategy_spec.get("market_whitelist") or [],
            "execution_params": execution_params,
        }

        try:
            instance.apply_metadata_snapshot(snapshot)
            logger.debug(
                f"[FACTORY] ✓ {strategy_id}: metadata snapshot inyectado "
                f"(assets={list(snapshot['affinity_scores'].keys())}, "
                f"whitelist={snapshot['market_whitelist']})"
            )
        except Exception as e:
            logger.warning(
                f"[FACTORY] ⚠ {strategy_id}: apply_metadata_snapshot falló: {e}. "
                f"La estrategia operará con sus constantes locales."
            )

    def get_engine(self, strategy_id: str) -> Optional[Any]:
        """
        Obtiene una estrategia compilada del cache.
        
        Args:
            strategy_id: Identificador de la estrategia
            
        Returns:
            Instancia del motor, o None si no existe
        """
        return self.active_engines.get(strategy_id)
    
    def get_all_engines(self) -> Dict[str, Any]:
        """Retorna todos los motores instantiados (Dict en memoria)."""
        return self.active_engines.copy()
    
    def get_load_errors(self) -> Dict[str, str]:
        """Retorna errores de carga para auditoría."""
        return self.load_errors.copy()
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas de carga."""
        return {
            "active_engines": len(self.active_engines),
            "failed_loads": len(self.load_errors),
            "load_errors": self.load_errors
        }
