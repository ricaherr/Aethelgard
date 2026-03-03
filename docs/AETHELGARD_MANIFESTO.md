# AETHELGARD MANIFESTO

## I. La Visión (El Alma)
**Aethelgard** es una entidad de inteligencia cuantitativa diseñada para la **Supremacía de Contexto**. Su propósito es procesar flujos de datos a una velocidad y profundidad inalcanzables para el cerebro humano, detectando patrones de micro-estructura y anomalías líquidas en tiempo real.

Aethelgard opera bajo un modelo de **Autonomía Delegada** donde el humano mantiene la soberanía de veto y limitación granular por componente o mercado, garantizando que el sistema sirva a la preservación del capital mientras domina el tablero analítico.

### Principios Fundamentales
1. **Autonomía**: El sistema busca, procesa y ejecuta sin esperar validación en el flujo estándar. Sin embargo, su autonomía es una concesión revocable por el operador humano.
2. **Resiliencia & Antifragilidad**: Detección proactiva de fallos y drift. El sistema no solo sobrevive al caos, sino que aprende a extraer valor de las anomalías del mercado.
3. **Evolución Continua**: Proceso de 'Auto-Tune' y meta-aprendizaje sobre el desempeño de la propia infraestructura (latencia, slippage) y el mercado.

## II. Pilares Operativos (Quanteer Focus)
La arquitectura de Aethelgard se rige por el rigor matemático y la independencia técnica.

1. **Agnosticismo Total**: El **Core Brain** es ciego a la plataforma de ejecución. Utiliza conectores modulares para interactuar con el mundo exterior, garantizando que la lógica institucional sea inmutable e independiente del broker.
2. **Unidades R (Universal Normalization)**: El riesgo es la única constante. Aethelgard no opera instrumentos, sino **Volatilidad Normalizada**. El riesgo en USD es la única métrica de entrada válida para cualquier operación, garantizando una aritmética decimal institucional.
3. **Shadow Ranking (The Strategy Jury)**: El mérito sobre la fe. Un motor de **Darwinismo Algorítmico** evalúa estrategias en tiempo real. La promoción de una estrategia de *Shadow* a *Live* requiere un Profit Factor > 1.5 sostenido bajo condiciones de mercado reales.
4. **Adaptatividad de Régimen**: Priorizar el **"Contexto sobre la Señal"**. Ninguna estrategia tiene permiso de ejecución sin la validación previa y positiva del `RegimeClassifier`.
5. **Hiper-Detección Multi-Escalar**: Vigilancia eterna desde micro-velas hasta tendencias macro. El sistema detecta la huella institucional mediante el análisis de absorción y liquidez en múltiples temporalidades simultáneamente.
6. **Antifragilidad Operativa**: El sistema está diseñado para nutrirse del caos y las anomalías (Cisnes Negros). Las desviaciones estadísticas extremas no se evitan, se analizan para generar Alpha en momentos de pánico o euforia irracional.

## III. Gobernanza y Seguridad (CTO Focus)
La libertad del sistema termina donde empieza la seguridad del capital.

1. **Estructura Orgánica (Los 10 Dominios)**: El desarrollo y operación de Aethelgard se rige por 10 Dominios Críticos que garantizan la trazabilidad y especialización del sistema:
    - **01_IDENTITY_SECURITY**: SaaS, Auth, Isolation.
    - **02_CONTEXT_INTELLIGENCE**: Regime, Multi-Scale.
    - **03_ALPHA_GENERATION**: Signal Factory, Indicators.
    - **04_RISK_GOVERNANCE**: Unidades R, Safety Governor, Veto.
    - **05_UNIVERSAL_EXECUTION**: EMS, Conectores FIX.
    - **06_PORTFOLIO_INTELLIGENCE**: Shadow, Performance.
    - **07_ADAPTIVE_LEARNING**: EdgeTuner, Feedback Loops.
    - **08_DATA_SOVEREIGNTY**: SSOT, Persistence.
    - **09_INSTITUTIONAL_INTERFACE**: UI/UX, Terminal.
    - **10_INFRASTRUCTURE_RESILIENCY**: Health, Self-Healing.

2. **Safety Governor & Context Awareness**: Reglas de gobernanza inyectadas en el aprendizaje autónomo para prevenir el sobreajuste (overfitting). Se aplican límites de suavizado (Smoothing) y fronteras de peso (Floor/Ceiling) infranqueables. Adicionalmente, el orquestador de riesgo (RiskManager) interroga al motor de liquidez (`LiquidityService`) para asegurar precisión contextual, emitiendo advertencias de mitigación si las ejecuciones ocurren fuera de zonas de alta probabilidad institucional (FVG y Order Blocks).
3. **Single Source of Truth (SSOT)**: Configuración, credenciales y estados residen exclusivamente en la base de datos central. El sistema prohíbe la redundancia de datos externos para evitar discrepancias operativas.
4. **Integridad Sistémica**: El sistema se audita a sí mismo en cada ciclo, garantizando que todos los módulos cumplan con el protocolo de inyección de dependencias y los estándares de validación técnica.
5. **Soberanía de Intervención**: El derecho inalienable del humano a restringir la autonomía del sistema (ej. Habilitar Forex Autónomo, pero mantener Veto en Crypto) sin comprometer la integridad de la lógica central. La configuración `module_governance.json` es la representación técnica de esta soberanía.
6. **Protocolo de Dependencias**: Cualquier instalación de módulos o dependencias externas debe ser informada previamente para su validación técnica y requiere la aprobación explícita del operador humano. Ningún componente tiene permiso para autogestionar librerías nuevas sin consentimiento.
7. **Seguridad Criptográfica (Bcrypt)**: El sistema prohíbe el uso de librerías de abstracción de alto nivel (como Passlib) que impongan límites arbitrarios a la entropía de las contraseñas (ej. 72 bytes). Se exige el uso de `bcrypt` de forma directa para garantizar una verificación de credenciales robusta y transparente.
8. **Lineamiento de Fidelidad Shadow (F-001)**: Para garantizar la viabilidad del modelo SaaS, todo rendimiento en el *Shadow Portfolio* debe incluir un factor de **Penalización de Latencia** y **Slippage Estimado**. No se aceptarán métricas teóricas "limpias" como base para la promoción a capital real.
9. **Patrón de Carga Lazy (Zero-Leak)**: En cumplimiento con la seguridad institucional, el frontend tiene prohibido establecer conexiones WebSocket (Cerebro Link) o realizar peticiones de telemetría operativa antes de una autenticación exitosa. El motor de datos debe ser inyectado solo en rutas protegidas.
10. **Inmutabilidad de Testing Institucional**: Está terminantemente prohibido relajar los umbrales de seguridad y riesgo (ej. Safety Governor) durante las pruebas automatizadas (TDD). Todo test debe enfrentarse a las restricciones exactas de producción. Si un mock falla por validaciones de gobernanza, se debe ajustar la matemática del mock (precisión de pips, balance simulado) y nunca el centinela del sistema.

## IV. El Ecosistema (SaaS & Futuro)
Aethelgard está diseñado para la escala, la privacidad y el rendimiento comercial.

1. **Escalabilidad Comercial**: Funcionalidades y señales filtradas por niveles de membresía, permitiendo una oferta SaaS estructurada y profesional.
2. **Multi-tenancy & Isolation**: Arquitectura orientada al aislamiento total de datos y ejecución por cliente, garantizando la privacidad de las estrategias y la integridad del capital.
3. **Ética del Dato**: Priorización del aprendizaje de calidad. El sistema depura y calibra su memoria histórica para alimentar un cerebro eficiente y resiliente al ruido del mercado.
4. **Excelencia en la Construcción**: Todo desarrollo debe seguir estrictamente la [Guía de Estilo y Desarrollo](DEVELOPMENT_GUIDELINES.md). El aislamiento multi-tenant y el agnosticismo de datos son dogmas innegociables que garantizan la integridad sistémica.
5. **Principio de Filtrado en el Edge (Edge Filtering)**: El sistema implementa una capa de filtrado en el perímetro de ingesta de datos que rechaza o desestima instrumentos cuyo **Score de Afinidad** cae por debajo del umbral de confianza configurado. Este mecanismo garantiza que solo los activos con señales estadísticamente significativas acceden al pipeline de cálculo (CoherenceService, RiskManager, Executor), reduciendo carga computacional y minimizando ruido de mercado. El **Edge Filter** valida tanto la compatibilidad del instrumento con estrategias activas (regime alignment, volatilidad normalizada) como la disponibilidad de datos suficientes (lookback histórico). Instrumentos rechazados se registran en `system_health.filtered_instruments` para auditoría y posterior revisión.

#### Estándar de Identidad de Alpha (Trazabilidad Institucional)
Cada estrategia/firma operativa genera su propia **Identidad Digital de Alpha** inmutable para garantizar trazabilidad entre el Core Brain, la Data Vault y los Logs del sistema.

**Componentes Obligatorios del ID de Alpha**:

| Componente | Formato | Ejemplo | Propósito |
|-----------|---------|---------|-----------|
| **Strategy Class ID** | `CLASE_XXXX` | `BRK_OPEN_0001` | Identificador único persistente de la estrategia (no cambia) |
| **Mnemonic Name** | `CCC_NAME_MARKET` | `BRK_OPEN_NY_STRIKE` | Nombre legible describiendo mercado, patrón y sesión operativa |
| **Instance ID** | UUID v4 | `a4e7f2c1-9d8b-4f3a-b7c2-e8d1f9a3b5c7` | Identificador único por operación/sesión (infinito, cada trade tiene uno) |

**Reglas de Gobernanza**:
- ✅ **Inmutable**: Strategy Class ID NO puede cambiar una vez registrado (SSOT en BD).
- ✅ **Trazable**: Instance ID se registra en TODOS los eventos (ejecución, cierre, logging, auditoría).
- ✅ **Única Fuente de Verdad**: El registro de Alpha reside en `strategies DB` con versionamiento semántico (v1.0, v1.1, v2.0).
- ✅ **Coherencia Multi-Dominio**: Todos los dominios (Brain, DataVault, Logger, UI) referencia el mismo Strategy ID.

**Almacenamiento**:
- **`data_vault/strategies_db.py`**: Tabla `strategies` con columns `class_id`, `mnemonic`, `version`, `created_at`, `status`.
- **`core_brain/signal_factory.py`**: Inyecta `strategy_class_id` + `instance_id` en cada OutputSignal emitido.
- **`SYSTEM_LEDGER.md`**: Registro histórico de todas las Alphas institucionalizadas con fecha de primera operación.

**Ejemplo de Flujo Completo**:
```
1. Se crea BRK_OPEN_0001 (NY Strike, Market Open Gap en EUR/USD)
   - Class ID: BRK_OPEN_0001
   - Mnemonic: BRK_OPEN_NY_STRIKE
   - Registrado en BD con status "SHADOW"

2. Scanner dispara señal el 2 de Marzo, 2026 09:15 EST
   - Genera Instance ID: a4e7f2c1-9d8b-4f3a-b7c2-e8d1f9a3b5c7
   - Signal emitida: {strategy_class_id: "BRK_OPEN_0001", instance_id: "...", ...}

3. RiskManager valida y ejecuta
   - Posición abierta con trace_id = BRK_OPEN_0001_a4e7f2c1...
   - Registrada en execution_db.trades

4. CoherenceService monitorea coherencia
   - Registra shadow vs live en signal_events con Instance ID
   - Calcula score y persiste en coherence_db

5. Trade cierra, instance_id completado en ejecutados
   - SYSTEM_LEDGER actualizado automáticamente
   - Auditoría: pull por BRK_OPEN_0001 + Instance ID = trazabilidad 100%
```

**Impacto Comercial (SaaS**):
- Cada tenant ve solo las Alphas de su nivel de membresía.
- Premium/Institutional pueden custom-calibrate parámetros de BRK_OPEN_0001 sin crear duplicado (misma Class ID).
- Reportes financieros pueden filtrar por Strategy ID para atribuir P&L exacto.
- Regulación: trazabilidad auditada para cada operación con chain of custody digital.

## V. Protocolo Quanter: Los 4 Pilares de la Firma Operativa
El motor doble de generación de estrategias (UniversalStrategyEngine) opera bajo un conjunto de principios constitucionales que garantizan la coherencia, adaptabilidad y supremacía de contexto en la ejecución de firmas operativas.

### 1. **Pilar Sensorial: Compatibilidad de Inputs**
Toda firma operativa es un composición estructurada de **inputs sensoriales** (indicadores, patrones, anomalías) que el sistema traduce en un **namespace de variables calculadas**.

**Regla Constitucional**: 
- Los inputs (Sensors) se definen como parámetros dinámicos (ej. RSI Period=14, FVG Sensitivity=0.5).
- El motor verifica que TODOS los indicadores requeridos estén disponibles en el `IndicatorFunctionMapper`.
- Si falta un indicador → **STRATEGY_INCOMPATIBLE_VETO**: la estrategia se marca como inoperable en este mercado/timeframe.
- Los inputs se persist en el Schema JSON bajo `"inputs": { "param_name": value, ...}`.

**Implementación**: `UniversalStrategyEngine.__init__()` valida el schema y genera el namespace antes de cualquier evalación de lógica.

### 2. **Pilar de Régimen: Type de Mercado y Hábitat Operativo**
Ninguna firma operativa puede ejecutarse sin la aprobación previa del **RegimeClassifier**. El mercado tiene un tipo de comportamiento (Tendencia, Media Reversion, Anomalía) y la firma debe estar diseñada para prosperar en ese hábitat específico.

**Regla Constitucional**:
- **regime_filter**: Atributo obligatorio del Schema que especifica los regímenes permitidos (ej. ["TREND_UP", "EXPANSION"]).
- **RegimeService** calcula el régimen actual en M15, H1, H4 (Multi-Scale Fractal Veto).
- Si el régimen actual NO está en `regime_filter` → **REGIME_VETO**: se rechaza la entrada de nuevas posiciones.
- Posiciones activas respetan el veto de liquidación (SL se ejecuta, pero se bloquean nuevas señales).

**Implementación**: `RiskManager.execute()` consulta `RegimeService.get_current_regime()` durante la evaluación de confianza.

### 3. **Pilar de Coherencia: Health Check del Modelo**
El rendimiento teórico (Shadow) y la ejecución real (Live) deben navegar en la misma dirección. La divergencia sostenida es una señal de que el mercado ha cambiado o el modelo está sobreajustado.

**Regla Constitucional**:
- **CoherenceService** monitorea continuamente la desviación entre shadow y live execution.
- **coherence_score**: 0-100%. Se recalcula tras cada operación cerrada.
  - 100% → Perfecta sincronía (raro, pero ideal).
  - 75-99% → Operativo (slippage + latencia normales).
  - 50-74% → Atención (posible drift; no se promueven nuevas estrategias a este nivel).
  - <50% → **COHERENCE_VETO**: la firma se retira a shadow mode automáticamente.
- Veto persistente en `system_state.coherence_veto` (SSOT).

**Implementación**: `ExecutionService` loguea detalles de trade shadow y live; `CoherenceService.calculate_coherence()` compara post-cierre.

### 4. **Pilar Multi-tenant: Aislamiento Operativo y Configuración Personalizada**
Cada tenant tiene su propio alquiler de estrategias, ajustes de riesgo y niveles de membresía. Las firmas operativas se distribuyen según el nivel comercial.

**Regla Constitucional**:
- **tenant_id**: Obligatorio en todo contexto de ejecución. Aísla datos, configuración y persisintencia.
- **membership_level**: [Basic, Premium, Institutional] determina qué estrategias están disponibles.
  - **Basic**: Estrategias de baja volatilidad, régimen único (Trend).
  - **Premium**: Acceso a Market Open Gap, apertura de micro-estructuras, multi-régimen.
  - **Institutional**: Acceso a adaptación dinámica de regímenes, custom thresholds, feedback loops avanzados.
- **strategy_params**: Configurables por tenant en `tenant_config` (SSOT en BD), permitiendo custom RSI periods, TP/SL ratios, etc.
- Se rechaza cualquier firma que requiera features de nivel superior al del tenant.

**Implementación**: `MainOrchestrator.initialize()` carga `tenant_config` desde BD; `StrategyModeSelector` valida membership antes de habilitar estrategias.

---

### Estructura Plug-and-Play de Entrega
Todas las Firmas Operativas deben seguir este formato estricto para garantizar compatibilidad con el Doble Motor:

```json
{
  "name": "EUR/USD - Market Open Gap",
  "market": "Forex",
  "timeframe_primary": "H1",
  "inputs": {
    "lookback_minutes": 60,
    "fvg_sensitivity": 0.5,
    "regime_check_periods": [15, 60, 240]
  },
  "regime_filter": ["TREND_UP", "EXPANSION", "ANOMALY"],
  "entry_logic": {
    "condition": "AND(price_in_fvg, h4_trend_positive, coherence_score >= 75)",
    "trigger": "consecutive_encroachment_50pct"
  },
  "exit_logic": {
    "take_profit": "R2_institutional_level",
    "stop_loss": "0.5R_or_candle_close",
    "trailing": "1.5R_partial_lock"
  },
  "risk_management": {
    "position_size_pct": 1.0,
    "max_consecutive_losses": 3,
    "min_coherence_threshold": 75
  },
  "membership_required": "Premium"
}
```

Este formato es la ley constitucional para todas las futuras firmas operativas. Cualquier desviación requiere validación explícita por el Protocolo de Gobernanza.

## V. Standards Técnicos - Manejo de Fechas y Timezones

### Contexto: Limitación Nativa de SQLite
SQLite **no posee un tipo de dato DATE nativo**. Todas las fechas se almacenan como strings en formato ISO 8601, lo que requiere un manejo consistente a nivel de aplicación para evitar discrepancias operativas.

### Standard Obligatorio para Aethelgard
1. **Normalización UTC Centralizada**: Todas las timestamps en la base de datos deben estar en **UTC** y almacenadas como strings en formato **`YYYY-MM-DD HH:MM:SS.SSS`** (ej. `2026-03-02 15:45:32.567`).

2. **Funciones de Utilidad (utils/time_utils.py)**:
   - **`to_utc(datetime_obj, source_tz=None) -> str`**: Convierte un objeto `datetime` Python a string UTC normalizado.
     - Si `datetime_obj` es naive (sin timezone), se interpreta como timezone local a menos que `source_tz` sea especificado.
     - Retorna: `'YYYY-MM-DD HH:MM:SS.SSS'` en UTC.
   - **`to_utc_datetime(datetime_obj_or_string, source_tz=None) -> datetime`**: Convierte a objeto `datetime` con timezone UTC aware.
     - Retorna: `datetime` object con `tzinfo=timezone.utc`.

3. **Regla de Oro - Nunca Usar `.isoformat()`**: 
   - ❌ **PROHIBIDO**: `datetime.now(timezone.utc).isoformat()`
   - ✅ **OBLIGATORIO**: `to_utc(datetime.now(timezone.utc))`
   - `.isoformat()` produce strings en formato completo ISO 8601 (ej. `2026-03-02T15:45:32.567000+00:00`) que **no coinciden** con el formato de SQLite y causa fallos en comparaciones de timestamps.

4. **Inserción en Base de Datos**:
   - El esquema de SQLite usa `DEFAULT CURRENT_TIMESTAMP` en columnas de fecha para capturar automáticamente la timestamp al insertar registros.
   - Para insertions explícitas: usar siempre `to_utc(datetime.now(timezone.utc))`.

5. **Comparaciones y Filtros**:
   - Al comparar timestamps en queries SQL: usar strings UTC normalizados, no objetos datetime.
   - Ejemplo correcto:
     ```python
     time_threshold = to_utc(datetime.now(timezone.utc) - timedelta(minutes=window_minutes))
     cursor.execute("SELECT * FROM logs WHERE timestamp >= ?", [time_threshold])
     ```

6. **Auditoría y Debugging**:
   - Verificar formato de timestamps en logs: debe verse como `2026-03-02 15:45:32.567`, no `2026-03-02T15:45:32.567000+00:00`.
   - Si hay discrepancias en filtros de ventanas de tiempo, verificar primero que se usó `to_utc()` y no `.isoformat()` al generar umbrales.

### Cobertura en el Codebase
Este estándar se aplica a:
- ✅ `core_brain/services/coherence_service.py` - Timestamps de eventos de coherencia
- ✅ `data_vault/execution_db.py` - Comparaciones de ventanas temporales en shadow logs
- ✅ `tests/test_coherence_service.py` - Fixtures de test con timestamps
- ✅ Todo nuevo módulo que maneje timestamps después de esta versión

---

## VI. Capa de Filtrado de Eficiencia por Score de Activo (EXEC-EFFICIENCY-SCORE-001)

Aethelgard implementa un sistema de **Score de Eficiencia de Activos** que valida la performance histórica antes de ejecución de cada estrategia.

### Principio Fundamental: SSOT en Performance Logs

La **fuente única de verdad (SSOT)** para los affinity scores son los logs de performance perseguidos en la tabla `strategy_performance_logs`:

```
strategy_performance_logs (id, strategy_id, asset, pnl, trades_count, win_rate, profit_factor, timestamp, trace_id)
    ↓ (Agregación dinámica)
strategies.affinity_scores (JSON: {"EUR/USD": 0.92, "GBP/USD": 0.85, ...})
    ↓ (Carga en memoria)
StrategyGatekeeper.asset_scores (Dict en-memory, ultra-fast lookup)
```

**Garantía**: Ningún score se hardcodea o se persiste en archivos JSON. El sistema aprende únicamente de datos reales en DB.

### Arquitectura de Dos Componentes

#### 1. **strategies_db.py (Persistencia SSOT)**

Métodos clave en StrategiesMixin:

- `create_strategy(class_id, mnemonic, version, affinity_scores, market_whitelist)`
  - Define una nueva estrategia con scores iniciales y lista de mercados permitidos
  
- `update_strategy_affinity_scores(class_id, affinity_scores)`
  - Actualiza scores después de agregar logs de performance (sistema de aprendizaje)
  
- `calculate_asset_affinity_score(strategy_id, asset, lookback_trades=50)`
  - Calcula score para un activo basándose en últimas N operaciones
  - Fórmula: `(avg_win_rate * 0.5) + (pf_score * 0.3) + (momentum * 0.2)`
    - **avg_win_rate**: Tasa de ganancia ponderada
    - **pf_score**: Profit Factor normalizado (capped at 2.0 → 1.0)
    - **momentum**: Tendencia reciente vs histórica
  
- `save_strategy_performance_log(strategy_id, asset, pnl, trades_count, win_rate, profit_factor, trace_id)`
  - Registra cada trade/batch para alimentar el cálculo de scores
  - Auditable con trace_id para trazabilidad completa

#### 2. **StrategyGatekeeper (In-Memory Guard)**

Componente ultra-rápido que valida tickets **antes** de procesar la lógica de estrategia:

```python
# Dentro de UniversalStrategyExecutor.generate_signals()
can_execute = gatekeeper.can_execute_on_tick(
    asset='EUR/USD',
    min_threshold=0.80,  # Script decide este umbral
    strategy_id='BRK_OPEN_0001'
)
if not can_execute:
    logger.debug(f"[VETO] Abort execution for {asset}: score below threshold")
    return []  # No signal generated
```

**Requisitos de Rendimiento**:
- ✅ Latencia < 1ms por validación (100% en-memory)
- ✅ Sin accesos a DB durante ejecución de tick
- ✅ Refresh periódico de cache desde DB (entre sesiones)

**Métodos Públicos**:

- `can_execute_on_tick(asset, min_threshold, strategy_id) → bool`
  - Validación rápida: whitelist check + score comparison
  - Returns True si OK, False si veto
  
- `set_market_whitelist(strategy_id, whitelist: List[str])`
  - Define activos permitidos para una estrategia (ej: solo Forex, no crypto)
  
- `log_asset_performance(...pnl, trades_count, win_rate, profit_factor...)`
  - Registra resultado de operaciones desde executor
  - Persiste en DB vía StorageManager
  
- `refresh_affinity_scores()`
  - Recarga cache desde DB (entre sesiones)
  - Idempotent y thread-safe (en contexto de asyncio)

### Flujo Completo: Operación + Aprendizaje

```
1. [OPERACIÓN]
   Tick llega → UniversalStrategyExecutor.generate_signals()
   ↓
   StrategyGatekeeper.can_execute_on_tick()
   - ¿EUR/USD en whitelist? ✅
   - ¿Score (0.92) >= min_threshold (0.80)? ✅
   → ALLOW → Generar señal
   
2. [TRADE EXECUTION]
   Señal ejecutada → Trade cierra con P&L
   ↓
   ExecutionManager.close_trade() registra resultado
   
3. [LEARNING]
   End-of-day script agrega logs:
   StrategyGatekeeper.log_asset_performance(
       strategy_id='BRK_OPEN_0001',
       asset='EUR/USD',
       pnl=250.00,
       trades_count=5,
       win_rate=0.80,
       profit_factor=1.5
   )
   
4. [SCORE UPDATE]
   Sistema de Tuning (ThresholdOptimizer) calcula nuevo score:
   new_score = calculate_asset_affinity_score('BRK_OPEN_0001', 'EUR/USD', lookback=50)
   → 0.92 + momentum adjustment = 0.94
   
   Actualiza en DB:
   StorageManager.update_strategy_affinity_scores('BRK_OPEN_0001', {'EUR/USD': 0.94, ...})
   
5. [CACHE REFRESH]
   Next session: StrategyGatekeeper.refresh_affinity_scores()
   → Carga nuevos scores en memoria
   → Operaciones de siguiente sesión ya benefician del aprendizaje
```

### Gobernanza y Seguridad

**Regla 8: Immutabilidad de Umbrales en Producción**
- min_threshold es especificado por el strategy JSON schema (inmutable)
- NO puede ser relelajado por el sistema (Safety Governor veto)
- Si un asset tiene score 0.70 y threshold es 0.80 → BLOCK SIEMPRE

**Regla 15: SSOT Único en DB**
- No hay archivos JSON con scores hardcodeados
- No hay caching en Redis o memcached sin DB sync
- Affinity_scores en JSON dentro de `strategies` table es caché legible, source de verdad es `strategy_performance_logs`

**Regla 9: Documentación Completa**
- Este apartado es documentación única oficial
- Cambios siempre se documentan AQUÍ, no en READMEs separados
- Trace_ID: EXEC-EFFICIENCY-SCORE-001 linked desde ROADMAP

### Integración Sistémica

El Gatekeeper se integra en:

| Componente | Integración | Responsable |
|-----------|-------------|-------------|
| **UniversalStrategyExecutor** | Llamada a `gatekeeper.can_execute_on_tick()` antes de `generate_signals()` | MainOrchestrator (inyecta gatekeeper) |
| **ExecutionManager** | Llama `gatekeeper.log_asset_performance()` cuando trade cierra | RiskManager/Executor |
| **MainOrchestrator** | Crea StrategyGatekeeper, lo inyecta en executor | Constructor StrategyGatekeeper(storage) |
| **StorageManager** | Proveedor de affinity_scores (StrategiesMixin) | StorageManager.get_strategy_affinity_scores() |
| **ThresholdOptimizer / Tuner** | Calcula scores nuevos, actualiza DB (llamado off-session) | sys_edge_tuner.py |

---
> [!TIP]
> Los detalles técnicos, diagramas de arquitectura y manuales de dominio se encuentran en la carpeta `docs/`. El historial cronológico de cambios técnicos reside en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md).
