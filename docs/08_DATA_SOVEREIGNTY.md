# Dominio 08: DATA_SOVEREIGNTY (SSOT, Persistence)

## 🎯 Propósito
Garantizar que la información sea el activo más fiable y protegido del sistema, eliminando redundancias y asegurando la persistencia inmutable bajo el dogma de Single Source of Truth (SSOT).

## 🔷 REGLA DE ORO: Convención Obligatoria de Nombres de Tablas (ARCH-SSOT-2026-006)

✅ **Todo activo financiero se denomina `asset` (NUNCA `symbol`, `instrument`, o variaciones).**
✅ **Tablas de sistema usan prefijo `sys_*` (Capa 0: Global).**
✅ **Tablas de usuario usan prefijo `usr_*` (Capa 1: Tenant-isolated).**
✅ **Datos en `sys_*` NUNCA se duplican en `usr_*`; tenants filtran en runtime.**
✅ **Tenant ID se infiere de la ruta del archivo DB (`data_vault/tenants/{id}/...`), NO se almacena en columnas `usr_*`.**
✅ **`sys_trades` es el SSOT de trades del sistema (SHADOW + BACKTEST). `usr_trades` es el SSOT de trades del trader (LIVE únicamente). Esta separación es ABSOLUTA e irreversible — ver ARCH-SSOT-2026-007.**

Esta convención es **vinculante** y será validada en `validate_all.py` → `audit_table_naming.py`.

---

## 🔷 REGLA ARCH-SSOT-2026-007: Separación de Trades por Origen (Sprint 22)

### El problema que resuelve

Antes de Sprint 22, `usr_trades` almacenaba trades de todos los modos (`LIVE`, `SHADOW`, `BACKTEST`). Esto contaminaba:
- Los **KPIs del trader real** (win rate, P&L) con resultados de paper trades
- El análisis de **edge tuner** y **risk manager** con datos ficticios
- La **auditoría** (era imposible distinguir qué era real vs simulado sin filtros explícitos)

### Arquitectura post-Sprint 22

```
Ejecución LIVE  → usr_trades   (Capa 1, tenant)   — trades reales del usuario
Ejecución SHADOW → sys_trades  (Capa 0, global)   — paper trades en cuenta DEMO del broker
Ejecución BACKTEST → sys_trades (Capa 0, global)  — simulaciones históricas
```

### Mecanismos de enforcement (doble capa de seguridad)

1. **Aplicación** (`data_vault/trades_db.py`):
   - `save_trade_result(execution_mode='LIVE')` → `usr_trades`
   - `save_trade_result(execution_mode='SHADOW')` → rutea automáticamente a `save_sys_trade()`
   - `save_sys_trade(execution_mode='LIVE')` → lanza `ValueError` en la capa de aplicación

2. **Base de datos** (SQLite TRIGGER):
   - `TRIGGER trg_usr_trades_live_only` en `usr_trades`: cualquier INSERT con `execution_mode != 'LIVE'` → `RAISE(ABORT)` — rechazado a nivel de motor
   - `CHECK(execution_mode IN ('SHADOW','BACKTEST'))` en `sys_trades`: impide físicamente insertar `LIVE`

### Flujo del motor Darwiniano con sys_trades

```
Signal SHADOW generada
       ↓
Executor → cuenta DEMO real (ic_markets_demo_10001)
       ↓
Orden ejecutada en MT5 DEMO → resultado real
       ↓
save_sys_trade(instance_id, account_id, execution_mode='SHADOW')
       ↓
sys_trades ← ShadowDB.calculate_instance_metrics_from_sys_trades(instance_id)
       ↓
ShadowMetrics (win_rate, profit_factor, equity_cv, consecutive_losses)
       ↓
evaluate_health() → 3 Pilares → INCUBATING | HEALTHY | DEAD | QUARANTINED
       ↓
Lunes 00:00 UTC → promote_to_real() si HEALTHY
```

---

## 🔄 PROTOCOLO DE SINCRONIZACIÓN: Global Intelligence + Local Execution

### Capa 0: Global Intelligence (`data_vault/global/aethelgard.db`)

**Tablas del Sistema** (admin-managed, read-only para tenants):
- `sys_config`: Configuración maestra (trading params, risk limits, system defaults)
- `sys_market_pulse`: ⭐ Market snapshot ÚNICO, escaneo global centralizado
- `sys_economic_calendar`: Eventos económicos globales (NewsSanitizer → DB)
- `sys_users`: Identidad y autenticación de usuarios
- `sys_strategies`: Estrategias disponibles y su ciclo de vida
- `sys_signal_ranking`: Ranking global de estrategias (reemplaza `usr_performance` deprecated)

**Garantía**: Un solo `sys_market_pulse` para todos los traders. Global Scanner escribe UNA SOLA VEZ; todos leen.

### Capa 1: Local Execution (`data_vault/tenants/{tenant_id}/aethelgard.db`)

**Tablas del Usuario** (tenant-owned, full CRUD access):
- `usr_assets_cfg`: Tus activos (filtras `sys_market_pulse` contra esto)
- `usr_trades`: Tus ejecuciones (Soberanía Total del Tenant)
- `usr_execution_logs`: Logs de ejecución con slippage y latencia
- `usr_position_history`: Historial de modificaciones a posiciones
- `usr_preferences`: Tu configuración personal de trading y UI

**Garantía**: Cada tenant controla su propia ejecución. Las escrituras en `usr_*` son exclusivas del tenant.

### Flujo de Datos: Cómo se Cruzan Ambas Capas

```plaintext
GLOBAL SCANNER         TENANT
(Capa 0)               (Capa 1)
                       
sys_market_pulse  ────→ Tenant A: SELECT FROM sys_market_pulse
      ↓                   WHERE asset IN (SELECT asset FROM usr_assets_cfg)
(EURUSD, AAPL,         
BTCUSDT, ...)          Result: Tenants operas solo los activos que configuraste
                       
sys_calendar      ────→ Tenant B: Consulta eventos macro (read-only)
      ↓                   
(NFP, BCE, etc.)       Decision: Aumentar/reducir exposición según eventos
```

---

## ⚠️ Regla de Acceso por Nivel

*   **La base de datos por tenant se crea UNA SOLA VEZ.** El archivo `data_vault/tenants/{tenant_id}/aethelgard.db` solo se crea cuando no existe (`provision_tenant_db` se invoca únicamente si `not os.path.isfile(db_path)`). No se vuelve a "crear" en cada petición ni en cada arranque.
*   **Las migraciones son solo aditivas.** `run_migrations()` añade columnas o filas faltantes (por ejemplo `ALTER TABLE ... ADD COLUMN`, `INSERT ... WHERE NOT EXISTS`). Nunca se borran datos existentes ni se reemplazan claves de `system_state` que ya tienen valor. Así se preservan operaciones, señales y configuración del usuario.
*   **Nunca sobrescribir datos existentes con defaults.** Si una clave existe en la DB (p. ej. `instruments_config`), no se debe reemplazar por un catálogo por defecto. Solo se siembra cuando la clave falta. Los defaults se usan en memoria para respuestas de API si hay error de lectura, pero no se persisten encima de datos ya guardados.

## 🚀 Componentes Críticos
*   **SSOT Orchestrator**: Garantiza que toda configuración resida exclusivamente en la DB.
*   **Multi-tenant Migrator**: Motor de evolución de esquemas que mantiene la consistencia entre bases de datos de clientes.
*   **Data Vault Architecture**: Estructura de persistencia segmentada para alta velocidad de lectura/escritura.

## 🖥️ UI/UX REPRESENTATION
*   **Sync Status Badge**: Indicador en tiempo real de la integridad y sincronización de la base de datos local vs nube orquestadora.
*   **Schema Evolution Map**: Log visual de migraciones y cambios estructurales aplicados al sistema.

## 📈 Roadmap del Dominio
- [x] Migración total de archivos JSON restantes a DB.
- [x] Implementación de protocolos de auditoría de hash para integridad de datos.
- [ ] Despliegue de redundancia geográfica para el modo SaaS.

---

## 🗄️ Estructura de Persistencia: Jerarquía de Verdad Global

### Arquitectura de Dos Capas (Capa 0 Global + Capa 1 Tenant)

El sistema establece una **jerarquía clara de persistencia** basada en el principio de **Single Source of Truth (SSOT)**:

#### **Capa 0: Núcleo Global** (`data_vault/global/aethelgard.db`)

**El Único Punto de Verdad Global del Sistema**

Esta **base de datos centralizada** contiene **SOLO tablas con prefijo `sys_*`**:

| Tabla | Propósito | Campos clave | Gobernanza |
|-------|-----------|--------|-----------|
| **sys_users** | Identidad y autenticación de usuarios | `id (PK)`, `email`, `password_hash`, `role (admin/trader)`, `tier`, `status` | ✅ SSOT única de usuarios; reemplaza `sys_auth` de v1.x |
| **sys_config** | Configuración global crítica (parámetros de trading, riesgo, system defaults) | `key (PK)`, `value (JSON/TEXT)`, `updated_at` | ✅ SSOT para parámetros globales; reemplaza `sys_state` de v1.x |
| **sys_audit_logs** | Registro inmutable de decisiones administrativas y eventos del sistema | `id (PK)`, `user_id`, `action`, `resource`, `status`, `timestamp`, `trace_id` | ✅ Append-only; auditoría nivel Capa 0 |
| **sys_economic_calendar** | Eventos económicos globales (NFP, BCE, etc.) — Sólo lectura para tenants | `event_id (PK)`, `country`, `event_name`, `currency`, `impact_score`, `event_time_utc` | ✅ NewsSanitizer inserta; tenants solo leen |
| **sys_strategies** | Registro global de estrategias disponibles — lifecycle BACKTEST→SHADOW→LIVE | `class_id (PK)`, `mode`, `score`, `required_regime`, `required_timeframes`, `last_backtest_at` | ✅ Sistema consulta para instanciar y evaluar |
| **sys_signal_ranking** | Ranking global de rendimiento de estrategias | `strategy_id (PK)`, `profit_factor`, `win_rate`, `execution_mode` | ✅ Reemplaza `usr_performance` (deprecated v3.x) |
| **sys_trades** | Trades del sistema: ejecuciones SHADOW (cuenta DEMO real) y BACKTEST — **NUNCA LIVE** | `id (PK)`, `instance_id` → `sys_shadow_instances`, `account_id` → `sys_broker_accounts`, `execution_mode CHECK('SHADOW','BACKTEST')`, `strategy_id`, `profit`, `open_time`, `close_time` | ✅ SSOT de paper trades; alimenta 3 Pilares del motor Darwiniano; blindado con TRIGGER contra `execution_mode='LIVE'` |

**Regla de Acceso**:
- 🔴 **Admin/DevOps**: Único rol autorizado para escribir en `sys_*`
- 🟢 **Trader**: Acceso de lectura solamente (ej: verificar su `tier`, consultar calendario económico)
- 🟢 **System**: Lectura/escritura de tablas específicas (ej: NewsSanitizer escribe en `sys_economic_calendar`)
- ❌ **PROHIBIDO**: Acceso directo a credenciales de brokers (están encriptadas en Capa 1)

#### **Capa 1: Soberanía del Trader** (`data_vault/tenants/{tenant_uuid}/aethelgard.db`)

**La Fortaleza de Datos del Trader**

Cada tenant tiene su **propia base de datos aislada** que contiene **SOLO tablas con prefijo `usr_*`**:

| Tabla | Propósito | Gobernanza | Acceso |
|-------|-----------|-----------|--------|
| **usr_assets_cfg** | Activos habilitados con tick_size, lot_step, contract_size | ✅ SSOT de instrumentos operables; filtrada contra `sys_strategies` | Trader RW, System R |
| **usr_trades** | Trades **LIVE únicamente** — historial real del trader (NUNCA SHADOW ni BACKTEST) | ✅ Blindado con TRIGGER `trg_usr_trades_live_only`: rechaza cualquier INSERT con `execution_mode != 'LIVE'` | Trader RW, Admin audit R |
| **usr_execution_logs** | Logs de ejecución con slippage y latencia real vs teórica | ✅ Evidencia de calidad de ejecución por broker | Trader R, System W |
| **usr_position_history** | Log de modificaciones a SL/TP de posiciones (EdgeTuner events) | ✅ Auditoría de ajustes automáticos | Trader R, System W |
| **usr_preferences** | Configuración personal de UI y parámetros de trading | ✅ Soberanía total del usuario | Trader RW |
| **usr_broker_accounts** | Cuentas de broker con límites de riesgo configurados | ✅ Gestión personal de cuentas | Trader RW |

**Regla de Aislamiento y Delegación**:
- 🟢 **Trader**: Acceso **total** a su carpeta `/tenants/{uuid}/` (todas tablas `usr_*`)
- 🔴 **Trader B**: NO puede ver, leer ni modificar datos del Trader A (aislamiento por UUID)
- 🔒 **Admin**: Puede leer datos de auditoria (`usr_trades`); NO puede modificar datos de traders
- 🟢 **System**: Lectura/escritura limitada (ej: `usr_signals.insert()` para nuevas señales, `usr_positions.sync()` post-ejecución)
- 📍 **Delegación de Responsabilidad**: UniversalEngine consulta `sys_strategies` (global) Y filtra contra `usr_assets_cfg` (personal trader) antes de generar `usr_signals`

---

## 🔧 Tenant Provisioning: bootstrap_tenant_template() - Creación Idempotente de Capas 1

**Función**: `data_vault/schema.py::bootstrap_tenant_template()`

**Propósito**: Crear plantilla de base de datos (`data_vault/templates/usr_template.db`) que actúa como blueprint para nuevos tenants. Copia las 12 tablas `usr_*` desde la Capa 0 global, permitiendo provisioning automático de nuevas Capas 1.

**Ubicación Física**:
```
data_vault/
├── global/
│   └── aethelgard.db                    (Capa 0: sys_* tables)
├── templates/
│   └── usr_template.db                  (Blueprint para nuevos tenants)
└── tenants/
    └── {tenant_uuid}/
        └── aethelgard.db                (Capa 1: Clone del template)
```

---

## 🗄️ Consolidación de Bases de Datos: SSOT Unificado (auth.db → aethelgard.db)

### Problema Histórico: Redundancia de Autenticación (v1.x)

**Síntoma**:
- ❌ Dos archivos DB separados: `auth.db` (auth/memberships) + `aethelgard.db` (operativo)
- ❌ Confusión sobre SSOT: ¿dónde leer credenciales?
- ❌ Sincronización manual entre BDs (propenso a errores)
- ❌ Auditoría dispersa (dos fuentes de verdad)

### Solución: Unificación en `aethelgard.db` (v2.x+)

**Arquitectura Unificada**:
```
data_vault/global/aethelgard.db
├── sys_auth           ← Usuarios, contraseñas, roles (Capa 0)
├── sys_memberships    ← Suscripciones, niveles (Capa 0)
├── sys_audit_logs     ← Registro de acciones administrativas
├── sys_state          ← Configuración global
├── sys_economic_calendar ← Eventos macro
└── sys_strategies     ← Estrategias disponibles
```

**REGLA**: `auth.db` es **DEPRECATED** (mantenido como backup histórico, no accesado en runtime).

### Mapping de Migración: auth.db → aethelgard.db

**Script de Migración Única** (ejecutar una sola vez):

```sql
-- Migration: 003_consolidate_auth_into_aethelgard.sql
-- Descripción: Unifica auth.db a aethelgard.db (ONE-TIME, IDEMPOTENT)

-- Insertar usuarios de auth.db sin sobrescribir existentes
INSERT OR IGNORE INTO sys_auth (user_id, email, password_hash, role, created_at)
SELECT 
    user_id,
    email,
    password_hash,
    role,
    created_at
FROM old_auth.users;

-- Insertar memberships sin sobrescribir
INSERT OR IGNORE INTO sys_memberships (user_id, tier, status, created_at)
SELECT 
    user_id,
    tier,
    status,
    created_at
FROM old_auth.memberships;
```

**Fields Mapping**:

| auth.db (v1) | aethelgard.db (v2) | Tipo | Notas |
|---|---|---|---|
| `users.user_id` | `sys_auth.user_id` | UUID | PK |
| `users.email` | `sys_auth.email` | VARCHAR | UNIQUE |
| `users.password_hash` | `sys_auth.password_hash` | VARCHAR | Fernet-encrypted |
| `users.role` | `sys_auth.role` | ENUM | {Admin, Trader} |
| `users.created_at` | `sys_auth.created_at` | DATETIME | Immutable |
| `memberships.tier` | `sys_memberships.tier` | ENUM | {Basic, Premium, Institutional} |
| `memberships.status` | `sys_memberships.status` | ENUM | {Active, Suspended, Expired} |

**Validación Post-Migración**:
- ✅ Todos los usuarios de auth.db importados
- ✅ Integridad referencial: cada user_id existe en sys_auth
- ✅ No duplicados (constraint UNIQUE en email)
- ✅ Passwords íntegros (hash no corrupto)

**Deprecación de auth.db**:
- 📋 Archivo mantenido como **backup histórico** (no eliminado)
- ❌ Runtime **NUNCA** accede a auth.db (completamente desacoplado)
- 🔒 Si se audita usuario histórico → consultar `sys_auth.sys_audit_logs`

### Signature y Modos de Ejecución

```python
def bootstrap_tenant_template(global_conn: sqlite3.Connection, mode: str = "manual") -> bool:
    """
    Create template DB by copying usr_* tables from global DB.
    
    Args:
        global_conn: Connection to data_vault/global/aethelgard.db
        mode: "manual" (default) or "automatic"
    
    Returns:
        True if bootstrap succeeded, False if already done (idempotent)
    """
```

**Dos Modos de Operación**:

| Modo | Ejecución | Uso Recomendado | Configuración |
|------|-----------|-----------------|---------------|
| **manual** | Solo en llamada explícita | ✅ Producción (control explícito) | Default en sys_config |
| **automatic** | Automático en startup si falta template | ✅ Desarrollo/Testing (conveniente) | Cambiar sys_config para habilitar |

**Configuración Persistente** (almacenada en `sys_config` table):

```
tenant_template_bootstrap_mode = "manual"     (default)
tenant_template_bootstrap_done = "0" → "1"    (automático post-bootstrap)
```

### Garantías Arquitectónicas

1. **Idempotencia**: 
   - Verifica si `usr_template.db` existe antes de crear
   - Comprueba flag `bootstrap_done` en sys_config
   - Múltiples llamadas = sin efectos (seguro para retry logic)

2. **SSOT Compliance**:
   - Configuración almacenada ÚNICAMENTE en DB (sys_config)
   - No hardcodeada en código ni en archivos .env
   - Cambios en runtime reflejados inmediatamente

3. **Data Isolation**:
   - Copia SOLO tablas `usr_*` (12 tablas)
   - NUNCA incluye tablas `sys_*` (esas son siempre globales)
   - Resultado: cada tenant tiene estructura idéntica, datos completamente aislados

4. **Schema Fidelity**:
   - Copia columnas, índices, constraints exactos
   - Preserva tipos de datos y valores por defecto
   - Mantiene referencial integrity (FKs)

5. **Error Handling**:
   - Try/except con rollback automático en fallos
   - Logging en cada fase (inicio, copia, validación, fin)
   - State restoration si error parcial

### Flujo Operacional Completo

```
STARTUP INICIAL
    ↓
01. Admin registra primer usuario (ADMIN)
    └─ INSERT en sys_auth (global DB)
    
02. Sistema inicializa (MainOrchestrator)
    └─ Carga configuración desde sys_config
    └─ Lee: tenant_template_bootstrap_mode = "manual"
    └─ Template NO existe aún → No hace nada
    
03. [CUANDO SE NECESITA] Admin ejecuta bootstrap manualmente
    ├─ Llamada: bootstrap_tenant_template(global_conn, mode="manual")
    ├─ Copia 12 tablas usr_* → data_vault/templates/usr_template.db
    ├─ Valida schema consistency
    ├─ Marca sys_config.bootstrap_done = "1"
    └─ Retorna: True (éxito)

04. Nuevo trader se registra
    ├─ INSERT en sys_auth → sys_memberships (global)
    ├─ StorageManager(tenant_id="new_uuid") 
    └─ ._ensure_tenant_db_exists() → Clona template a tenants/new_uuid/
    
05. Nuevo tenant completamente operativo
    ├─ Database: data_vault/tenants/new_uuid/aethelgard.db (clon del template)
    ├─ Schema: Idéntico al template (12 usr_* tables)
    ├─ Data: Vacío (listo para operaciones del trader)
    └─ Aislamiento: Garantizado (uuid en ruta = separación física)
```

### Ejemplo de Uso

```python
from data_vault.schema import bootstrap_tenant_template
from data_vault.storage import StorageManager

# Paso 1: Obtener conexión global
storage = StorageManager()  # tenant_id=None → data_vault/global/
global_conn = storage._get_conn()

# Paso 2: Ejecutar bootstrap (manual mode = default)
success = bootstrap_tenant_template(global_conn, mode="manual")

if success:
    print("[OK] Template creado en data_vault/templates/usr_template.db")
    
    # Ahora StorageManager clonará template para nuevos tenants:
    new_tenant_storage = StorageManager(tenant_id="trader_uuid_456")
    # → Automáticamente clona: templates/usr_template.db → tenants/trader_uuid_456/aethelgard.db
else:
    print("[INFO] Template ya existe (bootstrap idempotente)")

# Paso 3: [OPCIONAL] Enable automatic mode para startups futuros
storage.execute(
    "UPDATE sys_config SET value='automatic' WHERE key='tenant_template_bootstrap_mode'"
)
# A partir de ahora: bootstrap se ejecuta automáticamente si falta template
```

### Tablas Copiadas en Template (16 usr_* tables)

**Schema Real** (validado 2026-03-25 contra `data_vault/global/aethelgard.db`):
```
usuario (Capa 1): data_vault/tenants/{uuid}/aethelgard.db
├── usr_anomaly_events              (Anomalías detectadas: Z-Score, Flash Crash)
├── usr_assets_cfg                  (Activos habilitados para operar)
├── usr_broker_accounts             (Cuentas de broker del trader)
├── usr_coherence_events            (Incoherencias detectadas en señales)
├── usr_connector_settings          (Toggle manual de conectores)
├── usr_edge_learning               (Aprendizaje EDGE por detección/acción/resultado)
├── usr_execution_logs              (Logs de ejecución con slippage y latencia)
├── usr_notification_settings       (Configuración de canales de notificación)
├── usr_notifications               (Notificaciones del sistema)
├── usr_performance                 (⚠️ DEPRECATED — usar sys_signal_ranking)
├── usr_position_history            (Historial de modificaciones a posiciones)
├── usr_preferences                 (Configuración personal de UI y trading)
├── usr_signal_pipeline             (Auditoría de etapas de señales)
├── usr_strategy_logs               (Logs de rendimiento de estrategias por activo)
├── usr_trades                      (Trades ejecutados — inmutable post-cierre)
└── usr_tuning_adjustments          (Ajustes aplicados por EdgeTuner)
```

**Tablas NUNCA Copiadas** (Siempre en Capa 0 — sys_*):
```
global (Capa 0): data_vault/global/aethelgard.db
├── sys_audit_logs                  (Auditoría inmutable de sistema)
├── sys_broker_accounts             (Cuentas broker disponibles globalmente)
├── sys_brokers / sys_platforms     (Catálogo de brokers y plataformas)
├── sys_config                      (Parámetros globales — SSOT)
├── sys_consensus_events            (Consenso multi-estrategia)
├── sys_cooldown_tracker            (Cooldown de señales)
├── sys_credentials                 (Credenciales de broker — encriptadas)
├── sys_data_providers              (Proveedores de datos OHLC)
├── sys_dedup_rules / sys_dedup_events (Deduplicación de señales)
├── sys_economic_calendar           (Eventos macro globales)
├── sys_execution_feedback          (Feedback de ejecución — CircuitBreaker)
├── sys_market_pulse                (Estado del mercado — scanner global)
├── sys_regime_configs              (Pesos de métricas por régimen)
├── sys_shadow_instances            (Lifecycle SHADOW)
├── sys_shadow_performance_history  (Evaluación 3 Pilares)
├── sys_shadow_promotion_log        (Promociones SHADOW→LIVE)
├── sys_signal_quality_assessments  (Calidad de señales)
├── sys_signal_ranking              (Ranking global de estrategias)
├── sys_signals                     (Señales globales)
├── sys_strategies                  (Registro de estrategias — lifecycle)
├── sys_symbol_mappings             (Traducción de símbolos)
└── sys_users                       (Autenticación y roles)
```

**Integración con StorageManager**:

```python
class StorageManager:
    def __init__(self, tenant_id: Optional[str] = None, db_path: Optional[str] = None):
        """Constructor tenant-aware: clona template si es nuevo tenant."""
        self.tenant_id = tenant_id
        self.db_path = db_path or self._resolve_db_path(tenant_id)
        
        if not os.path.exists(self.db_path):
            self._ensure_tenant_db_exists()  # Copia template aquí
    
    def _ensure_tenant_db_exists(self):
        """Verifica template y clona si es necesario."""
        template_path = "data_vault/templates/usr_template.db"
        
        if not os.path.exists(template_path):
            raise TemplateNotFound("Ejecute bootstrap_tenant_template() primero")
        
        shutil.copy2(template_path, self.db_path)
        logger.info(f"[TENANT PROVISIONED] {self.db_path} from template")
```

### Performance: Tiempo de Creación

| Operación | Duración | Escala |
|-----------|----------|--------|
| bootstrap_tenant_template() | ~2-5 segundos | Una sola vez |
| StorageManager clonación | ~0.5-1 segundo | Por tenant |
| StorageManager inicialización | <100ms | Reutilización |

---

### Protocolo de Sincronización (Schema Evolution)

#### Principio Base: **El Código es Master**

Cuando se agrega una **nueva funcionalidad** (ej: nuevo indicador, nueva columna de auditoría), el **código dinámicamente genera y aplica parches SQL** que evolucionan el esquema **sin migración manual**.

#### Reglas Inmutables

1. **✅ Operaciones Permitidas**:
   - `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (aditivo)
   - `INSERT INTO ... WHERE NOT EXISTS` (siembra idempotente)
   - `CREATE TABLE IF NOT EXISTS` (nueva tabla)
   - `ADD INDEX IF NOT EXISTS` (optimización)

2. **❌ Operaciones PROHIBIDAS**:
   - `DROP COLUMN` (destruye datos históricos)
   - `RENAME TABLE` (rompe referencias, scripts, auditoría)
   - `DROP TABLE` (pérdida permanente de datos)
   - `TRUNCATE TABLE` (elimina historial)
   - `DELETE FROM table` (sin WHERE + auditoría via soft-delete)

#### Flujo de Sincronización

```
Inicialización del Sistema:
  ↓
1. MainOrchestrator.__init__() carga configuración
  ↓
2. StorageManager.ensure_schema() — Punto de Sincronización
  ├─ Lee changelog: migrations/pending_migrations.json
  ├─ Para cada migración pendiente:
  │   ├─ Lee script SQL (aditivo puro)
  │   ├─ Ejecuta: ALTER TABLE / INSERT / CREATE (sin destructivas)
  │   └─ Registra en system_state._schema_version
  │
3. Si el tenant es "viejo" (1 mes atrás):
  ├─ Automáticamente recibe nuevas columnas de estrategias creadas hoy
  ├— ejemplo: "Nueva estrategia SESS_EXT requiere columna `fibonacci_level`"
  │   └─ Sistema ejecuta: ALTER TABLE signals ADD COLUMN fibonacci_level
  │   └─ Tenant viejo queda sincronizado
  │
4. StrategyEngineFactory carga estrategias READY_FOR_ENGINE
  ├─ Valida: ¿Tiene tenant las columnas requeridas por estrategia?
  │ └─ Si no → Aplica migración correspondiente
  │ └─ Nuevo: Degradación graciosa si columnas faltan
  │
5. Sistema operativo con schema actualizado
```

#### Documentación de Cambios ("El Documentador")

**Regla para Dev Team**:

Cuando se agrega una nueva funcionalidad que **requiere nuevas columnas en BD**, el **Documentador debe proporcionar**:

1. **Descripción del Cambio**:
   ```markdown
   Feature: "New Session Extension Strategy (SESS_EXT_0001)"
   ```

2. **Script SQL de Migración** (aditivo puro):
   ```sql
   -- Migration: 001_add_fibonacci_support.sql
   ALTER TABLE signals ADD COLUMN fibonacci_level TEXT DEFAULT NULL;
   ALTER TABLE signals ADD COLUMN fibonacci_target REAL DEFAULT NULL;
   ALTER TABLE strategies ADD COLUMN fibonacci_enabled BOOLEAN DEFAULT FALSE;
   ```

3. **Changelog Entry**:
   ```json
   {
     "version": "2.1.5",
     "date": "2026-03-06",
     "migration": "001_add_fibonacci_support.sql",
     "description": "Soporte para Fibonacci retracements en Session Extension",
     "applied_to": ["aethelgard.db"],
     "rollback": "❌ NO SOPORTADO (aditivo puro)"
   }
   ```

4. **Validación Pre-Deploy**:
   - [ ] Script cumple **aditivo puro** (sin DROP/TRUNCATE/RENAME)
   - [ ] Type hints en nuevas columnas (TEXT/INTEGER/REAL/BOOLEAN)
   - [ ] Valores por defecto sensatos (NULL o valor mínimo)
   - [ ] Ejecución contra test DB exitosa
   - [ ] Backward compatibility validada (BD vieja después de migrar funciona igual)

#### Garantía de Consistencia

El sistema **valida automáticamente**:

- ✅ **Pre-Ejecución**: ¿Todas las columnas requeridas existen?
- ✅ **Post-Ejecución**: ¿Estrategia puede instanciar sin errores de NULL?
- ✅ **Idempotencia**: Si migración ya fue aplicada → se skippea (IF NOT EXISTS)
- ✅ **Auditoría**: Registro de quién, cuándo, qué migración en `system_audit_logs`

**Resultado**: Old tenants get new features automáticamente sin intervención manual.

---
## 📌 Convención de Nombres Obligatoria: sys_ vs usr_ (Declaración Constitucional)

### Propósito

Eliminar la ambigüedad conceptual mediante una **convención de nombres estricta y universalmente aplicable** que distingue inmediatamente entre datos globales compartidos (`sys_*`) y datos personalizados del trader (`usr_*`).

### Prefijo: `sys_*` (Global, Compartido, Configuración de Servidor)

**Ubicación**: Capa 0 (`data_vault/global/aethelgard.db`)

**Propósito**: Contienen información que es **propiedad del sistema**, no del usuario. Gestión centralizada.

**Tablas del Sistema** (actualizado 2026-03-25 — estado real DB):

| Tabla | Responsable de Escritura | Trader Lee | Trader Escribe |
|-------|--------------------------|------------|---------------:|
| `sys_users` | Admin (CLI/API Auth) | ❌ NO | ❌ NO |
| `sys_config` | Admin / System | ✅ SÍ (lectura) | ❌ NO |
| `sys_audit_logs` | System + Admin | ✅ SÍ (propios) | ❌ NO |
| `sys_economic_calendar` | NewsSanitizer/External Providers | ✅ SÍ (lectura) | ❌ NO |
| `sys_strategies` | DevOps/Strategy Team | ✅ SÍ (lectura) | ❌ NO |
| `sys_signal_ranking` | System (post-evaluación) | ✅ SÍ (lectura) | ❌ NO |
| `sys_market_pulse` | Global Scanner | ✅ SÍ (lectura) | ❌ NO |

**Regla Aislada**:
- Trader **NUNCA modifica** tablas `sys_*`
- Trader puede **consultar** tablas `sys_*` pero solo obtiene datos globales, no personalizados
- Admin es único autorizado para escribir en `sys_*`
- System puede escribir en tablas específicas (`sys_economic_calendar`, `sys_audit_logs`)

**Ejemplo**:
```python
# ✅ CORRECTO: Trader consulta calendar económico (solo lectura)
events = storage.query_sys("SELECT * FROM sys_economic_calendar WHERE event_time_utc > NOW()")

# ❌ PROHIBIDO: Trader intenta actualizar hard-stop global
storage.write_sys("UPDATE sys_state SET value=0.05 WHERE key='max_daily_risk_pct'")
# → PermissionDenied: No puede modificar sys_state
```

---

### Prefijo: `usr_*` (Usuario, Personalizado, Soberanía del Trader)

**Ubicación**: Capa 1 (`data_vault/tenants/{uuid}/aethelgard.db`)

**Propósito**: Contienen información **propiedad del usuario/trader**. Soberanía total. Sin interferencia externa.

**Tablas del Usuario** (actualizado 2026-03-25 — estado real DB):

| Tabla | Trader RW | System Read | System Write | Admin Read |
|-------|-----------|-------------|--------------|------------|
| `usr_assets_cfg` | ✅ Sí | ✅ Sí | ❌ NO | ✅ Audit |
| `usr_trades` | ✅ Sí | ✅ Sí | ✅ Sí (close/PnL) | ✅ Audit |
| `usr_execution_logs` | ✅ Sí (histórico) | ✅ Sí | ✅ Sí (ejecuciones) | ✅ Audit |
| `usr_position_history` | ✅ Sí (histórico) | ✅ Sí | ✅ Sí (EdgeTuner) | ✅ Audit |
| `usr_preferences` | ✅ Sí | ✅ Sí | ❌ NO | ✅ Audit |
| `usr_broker_accounts` | ✅ Sí | ✅ Sí | ❌ NO | ✅ Audit |
| `usr_notifications` | ✅ Sí | ✅ Sí | ✅ Sí (sistema) | ✅ Audit |
| `usr_anomaly_events` | ✅ Sí (histórico) | ✅ Sí | ✅ Sí (detector) | ✅ Audit |

**Regla Aislada**:
- Trader es **dueño absoluto** de sus datos `usr_*`
- Admin **nunca accede** a `usr_credentials` (encriptadas, privadas)
- System puede escribir en tablas específicas (`usr_signals`, `usr_trades`, `usr_positions`)
- Trader B **nunca ve** datos de Trader A (aislamiento por UUID)

**Ejemplo**:
```python
# ✅ CORRECTO: Trader configura sus activos permitidos
trader_db = TenantDBFactory.get_storage(trader_id)
trader_db.write("INSERT INTO usr_assets_cfg (symbol, enabled) VALUES ('EUR/USD', 1)")

# ✅ CORRECTO: System inserta nueva señal para trader
system_db = TenantDBFactory.get_storage(trader_id)
system_db.write("""
    INSERT INTO usr_signals (strategy_id, symbol, signal_type, trace_id)
    VALUES ('BRK_OPEN_0001', 'EUR/USD', 'BUY', '...')
""")

# ❌ PROHIBIDO: Trader A intenta leer datos de Trader B
trader_a_db = TenantDBFactory.get_storage(trader_a_id)
trader_a_db.query("SELECT * FROM tenants/{trader_b_id}/aethelgard.db.usr_trades")
# → PermissionDenied: No acceso cross-tenant
```

---

### Delegación de Responsabilidad: sys_ → usr_ Filtering

**Patrón Obligatorio en UniversalEngine**:

El motor de estrategias debe aplicar **dos consultas en cascada**:

1. **Filtro Global** (consulta `sys_strategies`): ¿Existe la estrategia globalmente? ¿Está READY_FOR_ENGINE?
2. **Filtro Personal** (consulta `usr_assets_cfg`): ¿El trader tiene habilitado este activo para su sistema?

```python
# UniversalStrategyEngine.analyze()
async def analyze(self, symbol: str, market_data: Dict, trader_id: str) -> Optional[OutputSignal]:
    """
    Genera señal solo si:
    1. Estrategia existe en sys_ (global)
    2. Trader la permite en usr_ (personal)
    """
    
    # Paso 1: Consultar sys_ (global)
    global_db = StorageManager.get_global_db()
    strategy = global_db.query_one("SELECT * FROM sys_strategies WHERE id=?", self.strategy_id)
    if not strategy or strategy.readiness != "READY_FOR_ENGINE":
        return None  # Estrategia no disponible globalmente
    
    # Paso 2: Consultar usr_ (personal del trader)
    trader_db = TenantDBFactory.get_storage(trader_id)
    user_config = trader_db.query_one("SELECT * FROM usr_assets_cfg WHERE symbol=?", symbol)
    if not user_config or not user_config.enabled:
        return None  # Trader no permite operar este símbolo
    
    # Paso 3: Generar señal (si pasó ambos filtros)
    signal = await self._generate_signal(symbol, market_data, strategy)
    return signal
```

**Beneficio**:
- ✅ Transparencia: Queda claro qué es global y qué es personal
- ✅ Escalabilidad: Agregar nueva estrategia globalmente NO afecta datos de traders
- ✅ Auditoría: Logs muestran claramente qué nivel fue filtrado
- ✅ Seguridad: Imposible cross-tenant o acceso no autorizado

---

### Prohibición de Redundancia: Sólo Lectura de sys_ en usr_

**Regla Constitucional - NUNCA HACER**:

```python
# ❌ PROHIBIDO: Duplicar datos globales en personal
trader_db.write("""
    INSERT INTO usr_instruments (symbol, market, category)
    SELECT symbol, market, category FROM sys_strategies
""")
# Razón: Duplicación de SSOT, causará inconsistencia

# ✅ CORRECTO: Trader referencia sys_ en tiempo de ejecución
trader_db.query("""
    SELECT a.symbol, s.metadata
    FROM usr_assets_cfg a
    INNER JOIN global.sys_strategies s ON a.symbol IN (s.market_whitelist)
""")
# Resultado: Sistema respeta ambos niveles sin duplicar
```

**Razón**: La data generada por el escáner central (`sys_`) es **de sólo lectura para el usuario**. El trader **solo modifica su configuración personal** (`usr_assets_cfg`), que actúa como un **filtro de aplicación** sobre lo disponible a nivel global.

---

## 🔍 Regla de Auditoría de Nombres (Validation Obligatoria)

**Script**: `scripts/utilities/audit_table_naming.py`

Ejecuta antes de cada deployment:

```python
# Pseudocódigo
def audit_db_naming(db_path):
    """Verifica que TODAS las tablas usan sys_ o usr_"""
    
    tables = db.query("SELECT name FROM sqlite_master WHERE type='table'")
    
    for table in tables:
        if not table.startswith("sys_") and not table.startswith("usr_"):
            raise NamingConventionViolation(
                f"Tabla '{table}' viola convención de nombres. "
                f"Debe usar 'sys_' (global) o 'usr_' (personal)"
            )
    
    logger.info("✅ Todas las tablas cumplen convención: sys_* y usr_*")
```

**Excepciones documentadas** — 4 tablas legacy que preexisten a la convención y están exentas del check:
- `edge_learning` — legacy de aprendizaje EDGE (pre-convención)
- `notifications` — legacy de notificaciones (pre-convención)
- `position_metadata` — NIVEL0 SSOT movido desde `trades_db.py` a `schema.py` en v2.x
- `session_tokens` — NIVEL0 SSOT de autenticación

**Resultado**: `validate_all.py` rechaza schemas que violen la convención (excepto las 4 tablas legacy listadas).

---


### Ejemplo Real: Agregar Nueva Estrategia en 3 Pasos

**Escenario**: Equipocrea **INST_FOOTPRINT_0002** (v2 mejorada del footprint institucional) que requiere:
- Nueva columna `volume_profile_bucket` en `signals`
- Nueva columna `institutional_absorption_pct` en `trades`

**Paso 1: Documentador Prepara Script**
```sql
-- Migration: 002_institutional_footprint_v2.sql
ALTER TABLE signals ADD COLUMN IF NOT EXISTS volume_profile_bucket TEXT DEFAULT 'unknown';
ALTER TABLE trades ADD COLUMN IF NOT EXISTS institutional_absorption_pct REAL DEFAULT 0.0;
```

**Paso 2: System En Runtime**
```python
# En MainOrchestrator.__init__()
storage.run_migrations()  # ← Ejecuta migrate 002 en TODAS las BD tenants

# Sistema automáticamente:
#   1. Lee 002_institutional_footprint_v2.sql
#   2. Por cada tenant en data_vault/tenants/*/aethelgard.db:
#      - Ejecuta ALTER TABLE (IF NOT EXISTS protege contra duplicados)
#   3. Registra en system_audit_logs: "Migration 002 applied by system"
```

**Paso 3: Traders Acceden Inmediatamente**
```python
# StrategyEngineFactory
strategy = StrategyEngineFactory().get_by_id("INST_FOOTPRINT_0002")
# Sistema verifica columnas requeridas existen
# Si NO existen → Aplica migración, luego instancia
# Si SÍ existen → Instancia directamente

# Trader usa la estrategia sin saber que fue actualizado
```

**Beneficio**: No hay downtime, no hay "versión de BD". Todo es progresivo y agnóstico.

