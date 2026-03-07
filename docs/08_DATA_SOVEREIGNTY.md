# Dominio 08: DATA_SOVEREIGNTY (SSOT, Persistence)

## 🎯 Propósito
Garantizar que la información sea el activo más fiable y protegido del sistema, eliminando redundancias y asegurando la persistencia inmutable bajo el dogma de Single Source of Truth (SSOT).

## ⚠️ Regla de oro: creación y evolución de la DB

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

#### **Capa 0: Núcleo Global** (`data_vault/global/aethelgard_core.db`)

**El Único Punto de Verdad Global del Sistema**

Esta **base de datos centralizada** contiene toda la información de **gobernanza, autenticación y auditoría** que persiste **independientemente del número de tenants**.

**Tablas Críticas**:

| Tabla | Propósito | Campos | Gobernanza |
|-------|-----------|--------|-----------|
| **auth** | Identidad y autenticación de usuarios | `user_id (PK)`, `email`, `password_hash`, `role (ENUM: Admin/Trader)`, `mfa_secret`, `created_at` | ✅ SSOT única; encriptación Fernet obligatoria |
| **memberships** | Niveles de acceso y suscripciones | `id (PK)`, `user_id (FK)`, `tier (ENUM: Basic/Premium/Institutional)`, `status (ENUM: Active/Suspended/Expired)`, `expiration (DATETIME)`, `created_at` | ✅ Determina qué estrategias/funciones puede usar el Trader |
| **system_audit_logs** | Registro inmutable de decisiones administrativas | `id (PK)`, `user_id`, `action (TEXT)`, `resource (TEXT)`, `severity (ENUM: INFO/WARNING/ERROR)`, `timestamp (DATETIME)`, `trace_id` | ✅ No es mutable; append-only; auditoría nivel Capa 0 |
| **system_state** | Configuración global crítica | `key (PK)`, `value (JSON)`, `updated_by (user_id)`, `updated_at`, `_version` | ✅ Hard-stops a nivel servidor (ej: `max_daily_risk_pct`), cierre de mercados |

**Regla de Acceso**:
- 🔴 **Admin/DevOps**: Único rol autorizado para modificar tablas en `aethelgard_core.db`
- 🟢 **Trader**: Acceso de lectura solamente (ej: verificar su `tier` antes de usar estrategia Premium)
- ❌ **PROHIBIDO**: Acceso directo a credenciales de brokers (no se almacenan aquí; están encriptadas en Capa 1)

#### **Capa 1: Soberanía del Trader** (`data_vault/tenants/{tenant_uuid}/aethelgard.db`)

**La Fortaleza de Datos del Trader**

Cada tenant tiene su **propia base de datos aislada** que contiene:

| Tabla | Propósito | Gobernanza |
|-------|-----------|-----------|
| **instruments_config** | Símbolos habilitados, activos, affinity scores | ✅ SSOT única por tenant; cambios via UI o API |
| **trades** | Historial completo de operaciones | ✅ Inmutable post-cierre; trazabilidad 100% con TRACE_ID |
| **signals** | Señales generadas (aprobadas, rechazadas, ejecutadas) | ✅ Registro de decisiones; auditoría de validaciones (4 Pilares) |
| **strategy_params** | Parámetros dinámicos de estrategias | ✅ Evolucionan con el tiempo (auto-calibración) |
| **credentials** | API keys del broker, encriptadas | ✅ Encriptación Fernet en reposo; nunca se loguean valores |
| **positions** | Posiciones abiertas y cerradas | ✅ Sincronía con broker via connectors |

**Regla de Aislamiento**:
- 🟢 **Trader**: Acceso total a su carpeta `/tenants/{uuid}/`
- 🔴 **Trader B**: NO puede ver, leer ni modificar datos del Trader A (aislamiento por UUID)
- 🔒 **Admin**: Puede leer (auditoría); NO puede modificar datos de traders sin autorización explícita

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
