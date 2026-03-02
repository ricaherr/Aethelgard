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
> [!TIP]
> Los detalles técnicos, diagramas de arquitectura y manuales de dominio se encuentran en la carpeta `docs/`. El historial cronológico de cambios técnicos reside en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md).
