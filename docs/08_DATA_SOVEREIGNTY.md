# Dominio 08: DATA_SOVEREIGNTY (SSOT, Persistence)

## 🎯 Propósito
Garantizar que la información sea el activo más fiable y protegido del sistema, eliminando redundancias y asegurando la persistencia inmutable bajo el dogma de Single Source of Truth (SSOT).

## 🔷 REGLA DE ORO: Convención Obligatoria de Nombres de Tablas (ARCH-SSOT-2026-006)

✅ **Todo activo financiero se denomina `asset` (NUNCA `symbol`, `instrument`, o variaciones).**  
✅ **Tablas de sistema usan prefijo `sys_*` (Capa 0: Global).**  
✅ **Tablas de usuario usan prefijo `usr_*` (Capa 1: Tenant-isolated).**  
✅ **Datos en `sys_*` NUNCA se duplican en `usr_*`; tenants filtran en runtime.**  
✅ **Tenant ID se infiere de la ruta del archivo DB (`data_vault/tenants/{id}/...`), NO se almacena en columnas `usr_*`.**

Esta convención es **vinculante** y será validada en `validate_all.py` → `audit_table_naming.py`.

---

## 🔄 PROTOCOLO DE SINCRONIZACIÓN: Global Intelligence + Local Execution

### Capa 0: Global Intelligence (`data_vault/global/aethelgard.db`)

**Tablas del Sistema** (admin-managed, read-only para tenants):
- `sys_config`: Configuración maestra (trading params, risk limits, system defaults)
- `sys_market_pulse`: ⭐ Market snapshot ÚNICO, escaneo global centralizado
- `sys_calendar`: Eventos económicos globales (NewsSanitizer → DB)
- `sys_auth`: Credenciales y autenticación (Fernet-encrypted)
- `sys_memberships`: Tiers de usuario y acceso

**Garantía**: Un solo `sys_market_pulse` para todos los traders. Global Scanner escribe UNA SOLA VEZ; todos leen.

### Capa 1: Local Execution (`data_vault/tenants/{tenant_id}/aethelgard.db`)

**Tablas del Usuario** (tenant-owned, full CRUD access):
- `usr_assets_cfg`: Tus activos (filtras `sys_market_pulse` contra esto)
- `usr_strategies`: Tus estrategias (parámetros personalizados)
- `usr_signals`: Tus señales generadas
- `usr_trades`: Tus ejecuciones (Soberanía Total del Tenant)
- `usr_performance`: Tu ranking de estrategias (basado en TU equity)

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

| Tabla | Propósito | Campos | Gobernanza |
|-------|-----------|--------|-----------|
| **sys_auth** | Identidad y autenticación de usuarios | `user_id (PK)`, `email`, `password_hash`, `role (ENUM: Admin/Trader)`, `mfa_secret`, `created_at` | ✅ SSOT única; encriptación Fernet obligatoria |
| **sys_memberships** | Niveles de acceso y suscripciones | `id (PK)`, `user_id (FK)`, `tier (ENUM: Basic/Premium/Institutional)`, `status (ENUM: Active/Suspended/Expired)`, `expiration (DATETIME)`, `created_at` | ✅ Determina qué estrategias/funciones puede usar el Trader |
| **sys_audit_logs** | Registro inmutable de decisiones administrativas y eventos del sistema | `id (PK)`, `user_id`, `action (TEXT)`, `resource (TEXT)`, `severity (ENUM: INFO/WARNING/ERROR)`, `timestamp (DATETIME)`, `trace_id` | ✅ Append-only; auditoría nivel Capa 0 |
| **sys_state** | Configuración global crítica (hard-stops, límites de riesgo servidor, cierre de mercados) | `key (PK)`, `value (JSON)`, `updated_by (user_id)`, `updated_at`, `_version` | ✅ SSOT para parámetros globales |
| **sys_economic_calendar** | Eventos económicos globales (NFP, BCE, etc.) — **Sólo lectura para tenants** | `event_id (PK)`, `country`, `event_name`, `impact_score (ENUM: HIGH/MEDIUM/LOW)`, `event_time_utc`, `created_at` | ✅ NewsSanitizer inserta; tenants solo leen |
| **sys_strategies** | Registro global de estrategias disponibles | `strategy_id (PK)`, `name`, `version`, `readiness (ENUM: READY_FOR_ENGINE/LOGIC_PENDING)`, `affinity_scores (JSON)` | ✅ UniversalEngine consulta para instanciar |

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
| **usr_assets_cfg** | Símbolos habilitados, activos, affinity scores personalizados del trader | ✅ SSOT única por tenant; cambios via UI o API. **Filtrada contra `sys_strategies`** | Trader RW, System R |
| **usr_trades** | Historial completo de operaciones del trader | ✅ Inmutable post-cierre; trazabilidad 100% con TRACE_ID | Trader RW, Admin audit R |
| **usr_signals** | Señales generadas (aprobadas, rechazadas, ejecutadas) para trader | ✅ Registro de decisiones; auditoría de validaciones (4 Pilares) | Trader RW, System W (new signals) |
| **usr_strategy_params** | Parámetros dinámicos de estrategias **personalizados por trader** | ✅ Evolucionan con el tiempo (auto-calibración). **No sobrescriben `sys_` valores globales** | Trader RW |
| **usr_credentials** | API keys del broker, encriptadas | ✅ Encriptación Fernet en reposo; nunca se loguean valores. **Admin NO tiene acceso** | Trader RW (own only) |
| **usr_positions** | Posiciones abiertas y cerradas del trader | ✅ Sincronía con broker via connectors | Trader RW, System W (sync) |

**Regla de Aislamiento y Delegación**:
- 🟢 **Trader**: Acceso **total** a su carpeta `/tenants/{uuid}/` (todas tablas `usr_*`)
- 🔴 **Trader B**: NO puede ver, leer ni modificar datos del Trader A (aislamiento por UUID)
- 🔒 **Admin**: Puede leer datos de auditoria (`usr_trades`); NO puede modificar datos de traders
- 🟢 **System**: Lectura/escritura limitada (ej: `usr_signals.insert()` para nuevas señales, `usr_positions.sync()` post-ejecución)
- 📍 **Delegación de Responsabilidad**: UniversalEngine consulta `sys_strategies` (global) Y filtra contra `usr_assets_cfg` (personal trader) antes de generar `usr_signals`

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

**Tablas del Sistema** (actualizado 2026-03-07):

| Tabla | Responsable de Escritura | Trader Lee | Trader Escribe |
|-------|--------------------------|------------|---------------:|
| `sys_auth` | Admin (CLI/API Auth) | ❌ NO | ❌ NO |
| `sys_memberships` | Admin (Billing/Suscripción) | ✅ SÍ (propia) | ❌ NO |
| `sys_audit_logs` | System + Admin | ✅ SÍ (propios) | ❌ NO |
| `sys_state` | Admin (servidor) | ✅ SÍ (lectura) | ❌ NO |
| `sys_economic_calendar` | NewsSanitizer/External Providers | ✅ SÍ (lectura) | ❌ NO |
| `sys_strategies` | DevOps/Strategy Team | ✅ SÍ (lectura) | ❌ NO |

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

**Tablas del Usuario** (actualizado 2026-03-07):

| Tabla | Trader RW | System Read | System Write | Admin Read |
|-------|-----------|-------------|--------------|------------|
| `usr_assets_cfg` | ✅ Sí | ✅ Sí | ❌ NO | ✅ Audit |
| `usr_trades` | ✅ Sí | ✅ Sí | ✅ Sí (close/PnL) | ✅ Audit |
| `usr_signals` | ✅ Sí (histórico) | ✅ Sí | ✅ Sí (new signals) | ✅ Audit |
| `usr_strategy_params` | ✅ Sí | ✅ Sí | ❌ NO | ✅ Audit |
| `usr_credentials` | ✅ Sí (own only) | ❌ NO | ❌ NO | ❌ NO** |
| `usr_positions` | ✅ Sí | ✅ Sí | ✅ Sí (sync) | ✅ Audit |

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

**Resultado**: `validate_all.py` rechaza schemas que violen la convención.

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
