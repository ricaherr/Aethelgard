# 📖 AETHELGARD: DEVELOPMENT GUIDELINES (BIBLIA DE INGENIERÍA)

## 🛡️ Propósito
Establecer los estándares innegociables para el desarrollo del ecosistema Aethelgard, garantizando la escalabilidad SaaS, la integridad financiera y una experiencia de usuario de nivel institucional.

## 1. Backend Rules: La Fortaleza Asíncrona

### 1.1 Aislamiento (Multitenancy)
El `user_id` es el átomo central. Ninguna función de base de datos o lógica de negocio puede ejecutarse sin la validación del contexto del usuario. **Documentación completa**: Ver Dominio 01_IDENTITY_SECURITY.md (Sección "Tenant Isolation Protocol").

**Patrón Obligatorio - RULE T1**:
Si endpoint tiene `token: TokenPayload` en firma → DEBE usar `TenantDBFactory.get_storage(token.sub)`
```python
# ❌ PROHIBIDO:
@router.get("/edge/history")
async def get_edge_history(token: TokenPayload = Depends(...)):
    storage = _get_storage()  # BD compartida, error de seguridad

# ✅ OBLIGATORIO:
@router.get("/edge/history")
async def get_edge_history(token: TokenPayload = Depends(...)):
    storage = TenantDBFactory.get_storage(token.sub)  # BD aislada del usuario
```

**Validación Automática**: 
- `scripts/tenant_isolation_audit.py` valida que todos los 47 endpoints cumplan RULE T1
- Ejecuta en cada invocación de `validate_all.py`
- Resultado: **47/47 endpoints (100% compliant)**

**Testing Obligatorio**:
- Suite `tests/test_tenant_isolation_edge_history.py` (5 tests) valida aislamiento real de datos
- Verifica que Alice no accede a datos de Bob (test_tenant_isolation_edge_history_alice_vs_bob)
- Verifica que TenantDBFactory se usa correctamente
- **Estado**: 5/5 PASSED

### 1.2 Agnosticismo de Datos
El Core Brain no debe conocer detalles del broker (MT5/FIX). Debe trabajar solo con Unidades R y estructuras normalizadas. All connectors must translate broker-specific data to Aethelgard canonical forms.

### 1.3 Rigor de Tipado
*   Uso estricto de **Pydantic** para todos los esquemas de datos y validaciones de entrada/salida.
*   Uso obligatorio de `Decimal` para todos los cálculos financieros. **PROHIBIDO** el uso de `float` en lógica de dinero para evitar errores de redondeo IEEE 754.
*   **Type Hints 100% (REGLA OBLIGATORIA)**: Cobertura completa de tipos en TODO el código Python.
    - ✅ **SÍ**: Parámetros de función, retornos, variables locales complejas
    - ✅ **SÍ**: Usar enums (`SignalType`, `MarketRegime`, etc.) en lugar de strings
    - ❌ **PROHIBIDO**: `signal_type="BUY"` → ✅ **USAR**: `signal_type=SignalType.BUY`
    - ❌ **PROHIBIDO**: Funciones sin tipo de retorno (`def func():`) → ✅ **USAR**: `def func() -> ReturnType:`
    - Validación: `validate_all.py` incluye Code Quality check que verifica type hints
    - Ejemplo INCORRECTO (signal_factory.py pre-corrección):
      ```python
      signal_type="BUY" if result.signal == "BUY" else "SELL"  # ❌ String literal
      ```
    - Ejemplo CORRECTO (post-corrección):
      ```python
      signal_type=SignalType.BUY if result.signal == "BUY" else SignalType.SELL  # ✅ Enum
      ```
*   **1.4. Protocolo "Explorar antes de Crear"**: Antes de implementar cualquier nueva función o clase, el Ejecutor DEBE realizar una búsqueda semántica en el repositorio actual para verificar si ya existe una lógica similar. Se prohíbe la duplicación de código; en su lugar, se debe refactorizar la función existente para que sea reutilizable.
*   **1.5. Convención Obligatoria: `sys_*` vs `usr_*`**: (NEW - 2026-03-07)
    - **`sys_*`**: Tablas globales, propiedad del sistema, configuradas por Admin
      - Ubicación: `data_vault/global/aethelgard.db`
      - Trader: Solo lectura (no escribe)
      - System: Lectura/escritura limitada (ej: NewsSanitizer escribe en `sys_economic_calendar`, SignalFactory escribe en `sys_signals`)
      - Ejemplo: `sys_auth`, `sys_strategies`, `sys_state`, `sys_economic_calendar`, `sys_signals`
    - **`usr_*`**: Tablas personalizadas, propiedad del trader, datos aislados por tenant
      - Ubicación: `data_vault/tenants/{uuid}/aethelgard.db`
      - Trader: Lectura/escritura total a sus datos
      - Admin: Lectura solo (auditoría), nunca escritura
      - System: Lectura/escritura limitada (ej: inserta nueva `usr_trades` asociada a `sys_signals`)
      - Ejemplo: `usr_assets_cfg`, `usr_trades`, `usr_credentials`
    - **VIOLACIÓN**: Cualquier tabla sin prefijo o que viole esta convención será rechazada por `audit_table_naming.py` en `validate_all.py`
    - **DI Delegación**: UniversalEngine consulta `sys_strategies` (global) Y filtra contra `usr_assets_cfg` (personal) → genera `usr_signals`
*   **1.6. Higiene de Masa (Regla <30KB)**: Ningún archivo puede superar los 30KB o las 500 líneas. Si un componente crece por encima de este límite, su fragmentación en submódulos es obligatoria e inmediata.
*   **1.7. Patrones Obligatorios**: Se exige el uso estricto de Repository Pattern para datos y Service Layer para lógica. Los Routers de FastAPI solo orquestan.

*   **1.8. API Endpoint Naming Convention (OBLIGATORIO - 2026-03-11)**: Separación inmutable entre nombres internos (Base de Datos) y nombres públicos (API REST).
    - **PRINCIPIO**: Tabla `sys_regime_configs` en BD ≠ ruta `/api/regime_configs` en API pública
    - **PROHIBIDO**: Exponer prefijos internos (`usr_`, `sys_`) en la API pública (404 Errors + deuda técnica)
    - **OBLIGATORIO**: Nombres semánticos en API, internamente uso de prefijos DB
    
    **Convención Correcta**:
    ```
    BD (Internal Naming)          →  API REST (Semantic Public Naming)
    ─────────────────────────────────────────────────────────────
    sys_regime_configs           →  /api/regime_configs
    usr_positions                →  /api/positions
    usr_strategies               →  /api/strategies  
    sys_signals                  →  /api/signals
    usr_trades                   →  /api/trades
    usr_orders                   →  /api/orders
    sys_audit_logs               →  /api/audit/logs (admin only)
    ```
    
    **Ejemplo CORRECTO** (Clean Architecture):
    ```python
    # core_brain/api/routers/market.py
    @router.get("/regime_configs")  # ✅ Semántico para público
    async def get_regime_configs(token: TokenPayload = Depends(...)):
        storage = TenantDBFactory.get_storage(token.sub)
        # Internamente accede: storage.get_all_sys_regime_configs()  (BD naming)
        return {"regime_weights": regime_weights, ...}
    ```
    
    **Ejemplo INCORRECTO** (Deuda Técnica):
    ```python
    # ❌ ANTES (Genera 404s, aliases como bandaids)
    @router.get("/sys_regime_configs")  # Prefijo interno en API pública
    @router.get("/regime_configs")          # Alias temporal = Technical Debt
    async def get_sys_regime_configs(...): ...
    ```
    
    **Validación Automática**:
    - Auditoría en `scripts/validate_all.py` chequea consistencia frontend ↔ backend
    - Detecta: Mismatches de nombres, 404s potenciales, aliases redundantes
    - Si encuentra endpoint con prefijo `usr_` o `sys_` en API pública → FAIL
    
    **Protocolo de Refactorización**:
    1. Audit de TODOS los endpoints (identificar mismatches)
    2. Renombrar de VERDAD (no aliases temporales)
    3. Actualizar cliente (frontend) una sola vez
    4. Eliminar aliases después de validar que todo funciona
    5. Documentar nuevo nombre en esta sección (SSOT)

*   **1.9. Timezone Handling - UTC Single Source of Truth (OBLIGATORIO - 2026-03-10)**:
    
    **PRINCIPIO**: Aethelgard opera EXCLUSIVAMENTE en UTC. Todos los timestamps de broker, base de datos, y procesamiento interno DEBEN ser UTC explícito con timezone info.
    
    **Garantía de Timezone**:
    1. **Entrada (Brokers)**: Todos los brokers devuelven timestamps UNIX (universalmente UTC)
       - MT5, Rithmic, OANDA, etc.: `timestamp` UNIX = segundos desde epoch UTC
    2. **Conversión explícita**: Usar `broker_timestamp_to_utc_datetime(timestamp)` de `utils/time_utils.py`
       ```python
       from utils.time_utils import broker_timestamp_to_utc_datetime
       
       # ✅ CORRECTO
       dt_utc = broker_timestamp_to_utc_datetime(mt5_deal.time)
       # Retorna: datetime(2026-03-10 10:00:00, tzinfo=timezone.utc)
       
       # ❌ PROHIBIDO - Interpreta como timezone local del servidor
       dt_wrong = datetime.fromtimestamp(mt5_deal.time)
       # Retorna: datetime(2026-03-10 11:00:00)  # NAIVE, interpreta local!
       ```
    3. **Persistencia (Base de Datos)**: SQLite adapter convierte a ISO 8601 UTC
       ```python
       # En data_vault/base_repo.py:
       sqlite3.register_adapter(datetime, 
           lambda dt: dt.astimezone(timezone.utc).isoformat())
       ```
    4. **Procesamiento (Core Logic)**: SessionStateDetector, RiskManager, etc. SIEMPRE usan UTC
       ```python
       from datetime import datetime, timezone
       
       now_utc = datetime.now(timezone.utc)  # ✅ CORRECTO
       # ❌ PROHIBIDO: now_local = datetime.now()  # Sin timezone = naive local
       ```
    5. **Salida (API/Frontend)**: ISO 8601 UTC en JSON
       ```python
       {"timestamp": "2026-03-10T10:00:00+00:00"}  # ✅ CORRECTO (UTC explícito)
       {"timestamp": "2026-03-10T10:00:00"}        # ❌ INCORRECTO (naive)
       ```
    
    **Por qué esto es crítico en Trading**:
    - SessionStateDetector compara contra horas UTC (LONDON 08:00 UTC, NY 13:00 UTC, etc.)
    - Si broker timestamp se interpreta como local (GMT+1, GMT+5, etc.) → FALSE POSITIVES en detección de sesiones
    - Ejemplo de ERROR:
      ```
      Servidor timezone: GMT+5
      MT5 devuelve: timestamp UNIX (UTC)
      datetime.fromtimestamp() → Interpreta como GMT+5 → 5 horas adelantado
      SessionStateDetector compara contra UTC → FALLA overlap detection
      →  False signals, missed opportunities, financial loss
      ```
    
    **Checklist de Validación** (verificar en `validate_all.py`):
    - ✅ No existe `datetime.fromtimestamp(x)` sin `tz=timezone.utc` en connectors/
    - ✅ Todos los broker timestamps convierten vía `broker_timestamp_to_utc_datetime()`
    - ✅ SessionStateDetector usa `datetime.now(timezone.utc)` o `datetime.now(pytz.UTC)`
    - ✅ RiskManager timestamps son UTC-aware
    - ✅ DB reads retornan datetime con tzinfo=UTC
    - ✅ API responses incluyen timezone (+00:00 o Z)
    
    **TRACE_ID**: TZUTIL-BROKER-TIMESTAMP-001

## 2. Frontend Rules: La Terminal de Inteligencia
*   **Estética Terminal**: Prohibido el uso de componentes de librerías comunes sin personalización. Estética **Bloomberg-Dark** (#050505, acentos cian/neón).
*   **Densidad de Datos**: Diseñar para el experto. Mostrar datos de alta fidelidad sin saturar, utilizando transparencias y capas (Glassmorphism).
*   **Micro-interacciones**: Los cambios de estado deben "pulsar" o "deslizarse". La UI debe sentirse como un organismo vivo y reactivo.
*   **Estado Centralizado**: El frontend es una capa de visualización. La lógica de trading y gestión reside exclusivamente en el Backend.

## 3. Protocolo de Higiene y Limpieza
*   **3.1. Gestión de Temporales**: Todo script de prueba, archivo .tmp, o código de depuración debe ser eliminado INMEDIATAMENTE después de cumplir su función. No se permite la persistencia de "basura técnica" en el repositorio principal.
*   **3.2. Comentarios de Producción**: Se prohíbe dejar bloques de código comentados ("muertos"). Si el código no es funcional, se elimina. La trazabilidad reside en el Git, no en los comentarios.

## 4. Gestión de Excepciones y Veto (OBLIGATORIO)
*   **4.1. Fail-Safe**: Todo proceso financiero debe incluir un bloque try-except específico con rollback de base de datos en caso de fallo.
*   **4.2. Veto Técnico**: La autonomía delegada se detiene si los signos vitales (latencia > 500ms o pérdida de WS) se degradan.
*   **4.3. Try/Except obligatorio**: No es aceptable dejar sin protección bloques que accedan a persistencia (DB), APIs (HTTP, WebSocket) o servicios externos. Cualquier ruta que lea/escriba en storage, llame a un endpoint o a un conector debe estar dentro de try/except con logging del error y comportamiento definido (retorno seguro, rollback o re-raise). El revisor debe rechazar código nuevo que añada estas rutas sin manejo explícito de excepciones.

## 5. Gestión de Credenciales y Seeds (OBLIGATORIO - v2.1)

### 5.1 Arquitectura de Credenciales - La Regla del Tres
**Separación inmutable de responsabilidades**:
1. **broker_accounts** (tabla): METADATOS públicos (account_id, broker_id, server, account_number)
2. **credentials** (tabla): DATOS SENSIBLES encriptados (encrypted_data = JSON encriptado con Fernet)
3. **data_providers** (tabla): PROVEEDORES DE DATOS (api_keys para terceros, configuración)

Acción prohibida: Almacenar passwords en plaintext, .env, .json o código.

### 5.2 Flujo de Encriptación Obligatorio
1. **Ingreso**: Usuario proporciona password en UI (ej: setup_mt5_demo.py) or API
2. **Validación**: StorageManager.save_broker_account() crea entrada en broker_accounts
3. **Encriptación**: Si `password` presente → StorageManager.update_credential() → encripta con `get_encryptor()` (Fernet) → INSERT en credentials.encrypted_data
4. **Lectura**: get_credentials(account_id) → desencripta → retorna Dict[str, str]

Ejemplo correcto:
```python
# ✅ CORRECTO:
storage.save_broker_account(
    account_id="ic_markets_demo_10001",
    broker_id="ic_markets",
    password="ml&4fgHDRfahe9"  # Se encriptará automáticamente
)

# ❌ PROHIBIDO:
storage.save_broker_account(
    account_id="...",
    password="hardcodeado_en_source"  # Violación de seguridad
)
```

### 5.3 Seeds - Inicialización Idempotente (Regla del Bootstrapping)

**Ubicación**: `data_vault/seed/` - SSOT para datos iniciales no sensibles

**Archivos permitidos**:
- `strategy_registry.json`: Firmas operativas del sistema
- `demo_broker_accounts.json`: Cuentas DEMO (metadatos + credenciales DEMO públicas)
- `data_providers.json`: Proveedores por defecto (Finnhub, CCXT, etc.)

**Reglas estrictas**:
- ✅ **SÍ** seedear: Broker DEMO account_name, server, credentials PÚBLICAS (demo MT5 válido)
- ❌ **NO** seedear: API keys operativas reales, tokens, passwords de usuarios reales
- ✅ Estructura: { credential_password: "value" } → se encripta al insertar
- 🔄 Idempotencia: Script `seed_demo_data.py` verifica existencia antes de INSERT
- 📊 Registro: Todos los seeds corren en `_bootstrap_from_json()` una sola vez (`_json_bootstrap_done_v1` flag)

**Ejemplo correcto** (demo_broker_accounts.json):
```json
{
  "account_id": "ic_markets_demo_10001",
  "broker_id": "ic_markets",
  "credential_password": "ml&4fgHDRfahe9"  // Demo públiquamente disponible
}
```

**Ejemplo prohibido**:
```json
{
  "account_id": "production_account",
  "password": "operativo_secreto_real"  // ❌ VIOLACIÓN: no seedear reales
}
```

### 5.4 Validación Automática (OBLIGATORIO)
Scripts de validación (`validate_all.py`) incluyen:
- ✅ Audit: Verificar que NO existe hardcodeado passwords/API keys en código
- ✅ Estructura: Seeds en formato correcto (JSON válido, campos requeridos)
- ✅ Securidad: No hay credenciales operativas en seeds o config files
- Resultado: Report "Credentials/Seeds Audit: PASSED"

---
Aethelgard sigue el estándar **Semantic Versioning 2.0.0**:
*   **MAJOR**: Cambios arquitectónicos que rompen compatibilidad.
*   **MINOR**: Nuevas funcionalidades (estrategias, conectores) sin rotura.
*   **PATCH**: Bugfixes, optimizaciones y documentación.

Toda versión debe validarse con `validate_all.py` antes de su desplieue y registrarse en el `SYSTEM_LEDGER.md`.

## ⚖️ Governance (Proceso de Validación)
Cada nueva funcionalidad o Historia de Usuario (HU) debe cumplir con:
1.  **Representación en UI**: Ninguna lógica de backend está "terminada" hasta que tenga su widget o visualización correspondiente en la Terminal.
2.  **Validación de Aislamiento**: Pruebas explícitas de que los datos no se filtran entre `tenant_id`s.
3.  **Agnosticismo**: Verificación de que el Core Brain sigue funcionando si se cambia el conector de datos.
4.  **Trazabilidad**: Toda tarea debe estar registrada en el [Central Backlog](../governance/BACKLOG.md) siguiendo la jerarquía de los 10 Dominios.

## 6. Frontend UI Rules: La Constitución Visual (Glass Cockpit Protocol) — OBLIGATORIO desde V3

### 6.1 Rule UI-1: Aesthetic Mandate — Institutional Visual Constitution

**PRINCIPIO RECTOR**: Aethelgard es un sistema financiero **técnicamente agresivo** que requiere una interfaz visual **institucional y futurista**, no superficial. La UI no es decorativa; es un instrumento de precisión que refleja la complejidad operativa del sistema.

**PROHIBICIÓN ABSOLUTA** (Penalidad: PR Rejection):
- ❌ Bordes sólidos (1px, 2px, cualquier grosor)
- ❌ Colores planos sin profundidad (sin gradientes, sin glow, sin alpha layering)
- ❌ Layouts de rejilla tradicional (grid 12-col, flex estático, tablas en Macro/Meso)
- ❌ Animaciones CSS vanilla (usar EXCLUSIVAMENTE Framer Motion)
- ❌ Tipografía por defecto (usar JetBrains Mono + serif moderno)
- ❌ Componentes de librerías sin personalización (MUI, Chakra, etc. → custom build obligatorio)

**MANDATO OBLIGATORIO** (Penalidad: PR Request Changes):
- ✅ Glassmorphism en TODOS los contenedores:
  ```css
  background: rgba(10, 15, 35, 0.4);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(0, 255, 255, 0.2);  /* Gradiente + alpha, NO sólido */
  box-shadow: 0 0 20px rgba(0, 255, 255, 0.08),
              inset 0 0 20px rgba(0, 255, 255, 0.04);
  ```
- ✅ Animaciones Framer Motion en TODO cambio de estado:
  - Entrada: `initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}`
  - Transición: `transition={{ type: "spring", damping: 30, stiffness: 100 }}`
  - Salida: Reverse animation + cleanup
- ✅ Paleta institucional ESTRICTA:
  - Fondo: `#020202` (True Black EXCLUSIVAMENTE)
  - Cyan-Electric: `#00F2FF` (salud, conexión, datos buenos)
  - Acid-Green: `#00FF41` (rentabilidad, éxito, confirmación)
  - Magenta: `#FF0066` (crítico, anomalía, error)
  - Gold: `#FFD700` (caution, zona gris)
  - Gray Neutral: `#666666` (desactivado, offline)
- ✅ Visualizaciones abstractas FUNCIONALES:
  - **Macro/Meso**: Gauges, Heatmaps, Node graphs, Particle fields, Canvas SVG nur
  - **Microonly**: Tablas permitidas (con animación de fila al actualizar)
  - **Prohibido**: Histogramas de barras, pie charts, líneas rectas
- ✅ Framer Motion + Canvas/WebGL obligatorio para:
  - Signal DNA Radar (partículas 60 FPS)
  - Neural Link Map (nodos interactivos)
  - Core Orb (gauges rotativos con needle animation)
  - Risk threshold transitions (stagger entry sequence)
- ✅ Densidad de datos EXPERTO:
  - Sin resumen simplificado → mostrar todo con transparencia + capas
  - Hover → mostra más detalles (tooltip técnico)
  - Click → zoom a siguiente nivel Fractal (Macro → Meso → Micro)

**FRACTAL DEPTH COMPLIANCE**:
- **Macro HUD** (Command Orb): Solo gauges circulares, glow effects, drop zones
  - Zero tablas, zero grillas, zero textos densos
- **Meso Managers** (Trader/Analysis/Portfolio/EDGE): Heatmaps, Node graphs, animaciones staggered
  - Tablas PROHIBIDAS (usar Canvas + tooltips en hover)
  - Grillas tradicionales → SVG asymmetric layouts
- **Micro Atomic** (Trade details, Signal reasoning):
  - Única zona donde tablas son permitidas
  - Fondos oscuro con glassmorphism ON rows
  - Columnas: timestamp | symbol | action | p&l (coloreado por valor)

**VALIDACIÓN AUTOMÁTICA** (PR Merge Gate):
```bash
python scripts/validate_all.py
# Incluye: 
#  - scan_ui_for_solid_borders()  → grep /@media|border:|\.border/ en .tsx files
#  - scan_ui_color_compliance()   → verifica palette (#020202, #00F2FF, #00FF41)
#  - scan_ui_animation_compliance() → grep /motion\.|transition|animation/ (Framer Motion)
#  - scan_ui_table_location()     → valida tablas solo en Micro level
```

**EXCEPCIONES** (Raras):
- Admin panel (settings, credentials): Puede usar tablas en Meso (logged as EXCEPTION_UI_ADMIN_001)
- Legacy components en deprecation: 6 meses de tolerancia después de deprecation notice
- A/B testing temporal: Máximo 2 semanas, debe documentarse en ticket

**TRACE_ID**: UI-CONSTITUTION-V3-001  
**Documento de Referencia Completo**: [docs/09_INSTITUTIONAL_UI.md#V3 The Glass Cockpit Protocol](docs/09_INSTITUTIONAL_UI.md#v3-the-glass-cockpit-protocol)

---
*Este documento es dinámico y representa el estándar de excelencia técnica de Aethelgard.*

