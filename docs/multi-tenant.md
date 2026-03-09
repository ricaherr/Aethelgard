# 🏗️ Arquitectura Multi-Tenant: Protocolo de Limpieza, Auditoría y Gobernanza de Datos

**Version**: 1.0  
**Status**: 🔵 GOBERNANZA ACTIVA  
**Fecha**: 2026-03-06  
**TRACE_ID**: ARCH-GOVERNANCE-SSOT-2026-003  

---

## 🎯 Propósito

Establecer un protocolo claro para la gestión, limpieza y auditoría de tenants en una arquitectura multi-tenant, eliminando ambigüedades sobre qué datos son operativos, cuáles son descartables y cuáles son protegidos.

---

## 📋 Inventario de Tenants: Clasificación y Ciclo de Vida

### I. Tenants Marcados para Eliminación Inmediata

Estos tenant UUIDs fueron creados con fines de **testing, desarrollo o prueba de concepto** y **no contienen datos operativos críticos**. **Deben ser eliminados del sistema** de manera ordenada.

| Tenant UUID | Uso Histórico | Status | Acción | Deadline |
|-------------|--------------|--------|--------|----------|
| `alice_uuid` | Demo trader Alice (prueba inicial de multi-tenant) | ❌ OBSOLETO | Eliminar folders + auditar si hay datos sensibles | 2026-03-10 |
| `bob_uuid` | Demo trader Bob (testing de aislamiento) | ❌ OBSOLETO | Eliminar folders + auditar si hay datos sensibles | 2026-03-10 |
| `tenant_test_123` | Automatización de tests (sandbox) | ❌ OBSOLETO | Eliminar folders + auditar credenciales | 2026-03-10 |
| `test_tenant` | QA general (ephemeral) | ❌ OBSOLETO | Eliminar folders + auditar si hay archivos temporales | 2026-03-10 |

**Procedimiento de Eliminación Segura**:

```bash
# Script: scripts/maintenance/cleanup_obsolete_tenants.py

for tenant_uuid in ["alice_uuid", "bob_uuid", "tenant_test_123", "test_tenant"]:
    1. Backup completo en backups/ (para auditoría histórica si es necesario)
    2. Verify no hay posiciones abiertas en MT5 (consultar via connector)
    3. Delete carpeta: data_vault/tenants/{tenant_uuid}/
    4. Log en system_audit_logs: "Tenant {uuid} deleted by system"
    5. Verify en aethelgard_core.db que usuario asociado está marcado inactive
```

**Validaciones Pre-Limpieza**:
- ✅ No hay trades abiertos (consultar posiciones en MT5)
- ✅ No hay suscripción activa
- ✅ No hay datos de clientes reales
- ✅ Backup completo en carpeta `backups/` con timestamp

---

### II. Tenants de Infraestructura (Protegidos)

Estos tenants **NUNCA deben ser eliminados** porque sirven funciones críticas de sistema.

#### **Tenant: `AETHEL-INTERNAL`**

**Propósito**: Testing de QA, validación de nuevas estrategias antes de producción

**Datos Contenidos**:
- Cuentas de demostración en MT5 (credenciales públicas, no sensibles)
- Estrategias en fase LOGIC_PENDING o READY_FOR_ENGINE (pre-lanzamiento)
- Métricas de performance en ambiente sandbox (no afecta operativas)

**Reglas de Acceso**:
- 🔴 **Traders**: NO tienen acceso (sistema interno solamente)
- 🟢 **Dev Team**: Lectura/escritura para testing
- 🟢 **QA Team**: Ejecución de scripts de validación

**Ciclo de Vida**:
- ✅ Permanente en el sistema
- ✅ Se auto-limpia cada 24h (eliminación de trades antiguos >30 días)
- ✅ Se realimenta con datos de prueba (seed data) cada deployment

---

#### **Tenant: `monitor-tenant`**

**Propósito**: Monitoreo de salud del sistema (health checks, métricas de uptime)

**Datos Contenidos**:
- Señales de diagnosticación (no operativas)
- Logs de latencia de API
- Métricas de performance del núcleo (CPU, memoria)
- Status de conectores (MT5, CCXT, data providers)

**Reglas de Acceso**:
- 🔴 **Traders**: NO tienen acceso
- 🟢 **Admin/DevOps**: Lectura de health metrics
- 🟢 **Monitoring System**: Escritura de telemetría

**Ciclo de Vida**:
- ✅ Permanente en el sistema
- ✅ Rotación de logs cada 7 días (retención máxima: 90 días)
- ✅ Datos nunca se eliminan (auditoría de uptime histórico)

---

### III. Tenants Operacionales (Activos)

Todos los demás tenants que pertenecen a **traders reales o cuentas institucionales** en producción.

**Protección Maximal**:
- 🔒 Backup diario automático
- 🔒 Cifrado en reposo (Fernet)
- 🔒 Aislamiento de datos entre tenants
- 🔒 Acceso de auditoría con TRACE_ID obligatorio

---

## 🗄️ Consolidación de Bases de Datos: Eliminación de Redundancia Auth

### Problema Histórico: El "Cisma de la Base de Datos"

**Antes (v1.x - ❌ DEPRECATED)**:
- `auth.db`: Contiene usuarios, passwords, roles
- `aethelgard.db` (raíz): Contiene otra copia de algunos datos
- **Redundancia**: Confusión sobre cuál es fuente de verdad

**Impacto Negativo**:
- ❓ Sistema no sabía dónde leer credenciales (¿ de auth.db o aethelgard.db ?)
- ❌ Sincronización manual entre BDs (propenso a errores)
- ❌ Auditoría confusa (dos fuentes de verdad)

### Solución Nueva (v2.x - ✅ SSOT):

**Unificación en `aethelgard_core.db`**:

Toda la información de autenticación, autorización y gobernanza reside en una **única base de datos centralizada**:

```
data_vault/global/aethelgard_core.db
├─ auth            ← Usuarios, contraseñas, roles
├─ memberships     ← Suscripciones
├─ system_audit_logs ← Auditoría
└─ system_state    ← Configuración global
```

---

### Mapping de Migración: auth.db → aethelgard_core.db

**Script de Migración Histórica** (ejecución única):

```sql
-- Migration: 003_consolidate_auth_v1_to_v2.sql
-- Descripción: Unifica auth.db a aethelgard_core.db (ONE-TIME)

INSERT INTO aethelgard_core.auth (user_id, email, password_hash, role, created_at)
SELECT 
    user_id,
    email,
    password_hash,
    role,
    created_at
FROM old_auth.users
WHERE user_id NOT IN (SELECT user_id FROM aethelgard_core.auth);

INSERT INTO aethelgard_core.memberships (user_id, tier, status, created_at)
SELECT 
    user_id,
    tier,
    status,
    created_at
FROM old_auth.memberships
WHERE user_id NOT IN (SELECT user_id FROM aethelgard_core.memberships);

-- Marcar auth.db como deprecated
-- (No se elimina fisicamente por auditoría histórica, pero no se accede en runtime)
```

**Mapping de Campos**:

| Campo auth.db (v1) | Campo aethelgard_core.db (v2) | Tipo | Notas |
|--------------------|------------------------------|------|-------|
| `users.user_id` | `auth.user_id` | UUID | PK |
| `users.email` | `auth.email` | VARCHAR | Unique |
| `users.password_hash` | `auth.password_hash` | VARCHAR | Fernet encrypted |
| `users.role` | `auth.role` | ENUM | {Admin, Trader} |
| `users.created_at` | `auth.created_at` | DATETIME | Inmutable |
| `users.updated_at` | `auth.updated_at` | DATETIME | Modificable |
| `memberships.tier` | `memberships.tier` | ENUM | {Basic, Premium, Institutional} |
| `memberships.status` | `memberships.status` | ENUM | {Active, Suspended, Expired} |

**Validación Post-Migración**:
- ✅ Todos los usuarios de auth.db importados a aethelgard_core.db
- ✅ Integridad referencial: cada user_id en auth existe
- ✅ No hay duplicados (constraint UNIQUE en email)
- ✅ Passwords validados (hash intacto, no corrupción)

**Deprecación de auth.db**:
- 📋 Archivo se mantiene como **backup histórico** (no se elimina)
- ❌ Runtime NUNCA accede a auth.db (completamente desacoplado)
- 🔒 Si se necesita auditar usuario histórico → consultar aethelgard_core.db.system_audit_logs

---

## 🧹 Protocolo de Auditoría de Residuos

### Definición: "Residuo de Datos"

Información **huérfana o inconsistente** que no debería existir en producción:

| Tipo | Ejemplo | Acción |
|------|---------|--------|
| **Archivos temporales** | `_debug_*.json`, `check_*.py` en raíz | ❌ Eliminar; nunca commitear |
| **Bases de datos obsoletas** | `auth.db` (deprecated) | ✅ Guardar en backups/, no usar en runtime |
| **Credenciales hardcodeadas** | API keys en `.env` o código | ❌ CRÍTICO: Eliminar inmediatamente, rotar claves |
| **Datos huérfanos en BD** | Trades sin tenant_id válido | ⚠️ Quarantine en tabla separate, auditar |
| **Posiciones fantasma** | Posición abierta en BD pero NO en MT5 | 🧹 Auto-limpieza por SignalDeduplicator |

### Scan Automático

**Script**: `scripts/utilities/audit_data_residue.py`

```python
def scan_residue():
    # Detecta archivos temporales en raíz
    temp_files = glob.glob("check_*.py") + glob.glob("_debug_*.json")
    
    # Detecta credenciales en .env (debería estar vacío o no existir)
    env_content = read_file(".env")
    api_keys = re.findall(r'API_KEY|PASSWORD|SECRET', env_content)
    
    # Detecta trades sin tenant_id en BD
    orphaned = db.query("SELECT * FROM trades WHERE tenant_id IS NULL")
    
    # Log todo en system_audit_logs
    if len(temp_files) > 0 or len(api_keys) > 0 or len(orphaned) > 0:
        logger.warning(f"DATA RESIDUE DETECTED: {temp_files}, {api_keys}, {orphaned}")
```

**Ejecución**:
- ✅ Pre-deployment: `audit_data_residue.py` debe retornar "CLEAN"
- ✅ Programada diaria: 02:00 UTC (durante mantenimiento)
- ✅ Alertas en Telegram si detecta residuos críticos

---

## 🔐 Aislamiento Garantizado: Multi-Tenant Security Model

### Principio: Zero Trust Inter-Tenant

Un trader **NUNCA debe poder acceder a datos de otro trader**, incluso si tiene acceso a la misma máquina.

**Implementación**:

```python
# En MainOrchestrator, antes de cualquier lectura de BD:

def get_trader_data(user_id: str, requested_field: str) -> Any:
    """
    Fetch datos del trader con validación de tenant_id.
    """
    # 1. Verificar user_id tiene membership activa
    membership = storage.get_membership(user_id)
    if membership.status != "Active":
        raise PermissionDenied(f"User {user_id} subscription expired")
    
    # 2. Obtener tenant_uuid del usuario
    tenant_uuid = storage.get_user_tenant_uuid(user_id)
    
    # 3. Abrir SOLO BD del tenant específico
    db_path = f"data_vault/tenants/{tenant_uuid}/aethelgard.db"
    with sqlite3.connect(db_path) as conn:
        # ← NO hay acceso a otras carpetas
        cursor = conn.cursor()
        # Lectura segura dentro de tenant_uuid
    
    return result
```

**Validaciones**:
- ✅ Cada llamada a BD lleva `tenant_uuid` verificado
- ✅ No se usan rutas glob `tenants/*/` (acceso específico)
- ✅ Todas las queries logueadas con `user_id` para auditoría
- ✅ Error si se intenta acceder a tenant distinto → `PermissionDenied`

---

## 📊 Métricas de Salud Multi-Tenant

**Dashboard**: `monitor-tenant` registry (interno)

| Métrica | Threshold | Acción |
|---------|-----------|--------|
| Tenants Activos | N/A | Informativo |
| Espacio BD promedio por tenant | >500 MB | Alert: posible data leak |
| Credenciales vencidas | >0 | Alert: fuerza re-auth |
| Datos huérfanos detectados | >0 | Warning: audit_residue.py debe correr |
| Sincronización BD schema | Lag > 5 min | Critical: detener sistema |

---

## 🎯 Pasos Ejecutables (Próximos 30 días)

- [ ] **Semana 1**: Ejecutar `cleanup_obsolete_tenants.py` (eliminar alice, bob, test_*)
- [ ] **Semana 1**: Validar `AETHEL-INTERNAL` y `monitor-tenant` están protegidos
- [ ] **Semana 2**: Ejecutar migración `003_consolidate_auth_v1_to_v2.sql`
- [ ] **Semana 2**: Desactivar lectura de auth.db en código (100%)
- [ ] **Semana 3**: Ejecutar `audit_data_residue.py` en modo strict
- [ ] **Semana 4**: Documentar en SYSTEM_LEDGER.md con TRACE_ID

---

**Estatus**: 🔵 En Fase de Documentación de Diseño  
**Próxima Revisión**: 2026-03-20

