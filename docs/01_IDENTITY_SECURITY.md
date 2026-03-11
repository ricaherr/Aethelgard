# Dominio 01: IDENTITY_SECURITY (SaaS, Auth, Isolation)

## 🎯 Propósito
Garantizar la integridad, privacidad y seguridad del ecosistema Aethelgard mediante protocolos de autenticación de nivel bancario y un aislamiento total de datos (Multitenancy). Este dominio protege el capital y la privacidad de cada cliente mediante criptografía, aislamiento de bases de datos y validación exhaustiva de tokens.

## 🚀 Componentes Críticos

### Auth Gateway
Middleware centralizado con protección JWT que valida cada solicitud antes de acceder a recursos. Implementa:
- Validación de firma JWT con secretos rotados
- Extracción de `tenant_id` desde el payload del token
- Inyección de `TokenPayload` en rutas protegidas
- Excepciones explícitas para tokens inválidos, expirados o comprometidos

### Tenant Isolation Protocol
Factoría de bases de datos que garantiza que el `user_id` sea inyectado en cada consulta y que cada cliente tenga su propia base de datos aislada.

#### Arquitectura Multi-Tenant
- **Por-User Database Isolation**: Cada usuario obtiene su base de datos exclusiva en `data_vault/tenants/{user_id}/aethelgard.db`
- **User Provisioning**: Nueva BD se crea automáticamente clonando `data_vault/templates/usr_template.db` (blueprint generado vía `bootstrap_tenant_template()`). La plantilla contiene las 12 tablas `usr_*` del esquema del usuario con estructura estándar. Ver detalles técnicos en [Dominio 08: DATA_SOVEREIGNTY - Tenant Provisioning](08_DATA_SOVEREIGNTY.md#-tenant-provisioning-bootstrap_tenant_template---creación-idempotente-de-capas-1).
- **TenantDBFactory Pattern**: Factory singleton que crea y cachea `StorageManager` instances por usuario
  ```python
  # Patrón correcto:
  storage = TenantDBFactory.get_storage(token.sub)  # BD aislada del usuario (clonada de template)
  
  # Patrón PROHIBIDO:
  storage = _get_storage()  # BD genérica compartida entre todos
  ```
- **Schema Consistency**: Cada BD de usuario usa el mismo schema (`data_vault/schema.py`) pero datos completamente aislados. Template garantiza que todas las Capas 1 sean idénticas estructuralmente.
- **Zero Cross-Tenant Data Leakage**: Imposible acceder a datos de otro usuario incluso si alguien contornea autenticación

#### Reglas Obligatorias de Implementación

**RULE T1**: Si endpoint tiene `token: TokenPayload` en firma → **DEBE** usar `TenantDBFactory.get_storage(token.sub)`
```python
# ❌ INCORRECTO:
@router.get("/signals")
async def get_signals(token: TokenPayload = Depends(get_current_active_user)):
    storage = _get_storage()  # ¡ERROR! BD compartida
    return storage.get_signals()  # Datos filtrados por user_id post-facto

# ✅ CORRECTO:
@router.get("/signals")
async def get_signals(token: TokenPayload = Depends(get_current_active_user)):
    storage = TenantDBFactory.get_storage(token.sub)  # BD aislada por usuario
    return storage.get_signals()  # Solo datos del usuario en BD
```

**RULE T2**: Si endpoint retorna datos del usuario → **DEBE** estar en BD aislada (no filtro post-facto)
```python
# ❌ PROBLEMATIC (aunque funcione):
tuning_history = storage.get_all_tuning_history()
filtered = [h for h in tuning_history if h['user_id'] == token.sub]  # Filtro manual

# ✅ SEGURO:
tuning_history = storage.get_tuning_history()  # BD ya es del usuario
# (retorna solo datos de ese usuario, no hay filtro necesario)
```

**RULE T3**: Si endpoint modifica datos → **DEBE** validar que `owner_id == token.sub`
```python
@router.post("/update_strategy")
async def update_strategy(req: StrategyUpdate, token: TokenPayload = Depends(...)):
    storage = TenantDBFactory.get_storage(token.sub)
    strategy = storage.get_strategy(req.strategy_id)
    
    if strategy['owner_id'] != token.sub:  # Validación explícita de propiedad
        raise HTTPException(403, "Not owner of this strategy")
    
    storage.update_strategy(req)  # Ahora seguro actualizar
```

**RULE T4**: Todo endpoint público → **DEBE** tener `@Depends(get_current_active_user)`
```python
# ❌ CRÍTICO:
@router.get("/public_signal")  # SIN AUTH
async def get_public_signal():
    # ...es punto de entrada de CUALQUIERA

# ✅ OBLIGATORIO (incluso si endpoint es "público" conceptualmente):
@router.get("/public_signal")
async def get_public_signal(token: TokenPayload = Depends(get_current_active_user)):
    # Ahora token.tid filtra qué señal ve (versiones por suscripción, etc.)
```

#### Validación Continua

**Tenant Isolation Scanner** (`scripts/tenant_isolation_audit.py`):
- Ejecuta automáticamente en cada validación (parte de `validate_all.py`)
- Escanea todos los archivos en `core_brain/api/routers/`
- Detecta endpoints con `token` parameter que NO usan `TenantDBFactory`
- Genera reporte: `[OK]` o `[FAIL]` para cada uno de los 47 endpoints
- **Cumplimiento Actual**: ✅ 47/47 endpoints (100% compliant)

**Security Test Suite** (`tests/test_tenant_isolation_edge_history.py`):
- 5 tests comprensivos de aislamiento multi-tenant
- Test `test_tenant_isolation_edge_history_alice_vs_bob`: Verifica que Alice y Bob usan BDs separadas
- Test `test_endpoint_uses_tenantdbfactory_not_generic_storage`: Valida que usa TenantDBFactory, no genérico
- Tests de estructura de respuesta e integridad de datos
- **Estado**: ✅ 5/5 PASSED

---

## 🔄 Tenant Lifecycle Management: Provisioning → Deprovisioning

### Clasificación de Tenants (Ciclo de Vida)

#### **TIPO A: Tenants de Producción (Permanentes)**
Usuarios activos con suscripciones pagas o trials activos. Están protegidos y respaldados regularmente.

| Estado | Acción | Backup | Retención |
|--------|--------|--------|-----------|
| **ACTIVE** | Operativos, datos en uso real | Diario | Indefinida |
| **SUSPENDED** | Suspensión temporal (pago vencido, violación ToS) | Diario | Indefinida |
| **ARCHIVED** | Usuario solicitó cierre de cuenta (datos legales) | Semanal | 7 años |

#### **TIPO B: Tenants de Prueba/Testing (Temporales - ❌ PARA ELIMINAR)**
Creados para desarrollo, QA o demos. No contienen datos operativos reales.

| UUID | Uso | Status | Acción | Deadline |
|------|-----|--------|--------|----------|
| `alice_uuid` | Demo trader inicial | OBSOLETO | Eliminar carpeta + backup | 2026-03-15 |
| `bob_uuid` | Testing de aislamiento | OBSOLETO | Eliminar carpeta + backup | 2026-03-15 |
| `tenant_test_123` | Automatización QA | OBSOLETO | Eliminar carpeta + backup | 2026-03-15 |
| `test_tenant` | Sandbox general | OBSOLETO | Eliminar carpeta + backup | 2026-03-15 |

### Provisioning: Crear Nuevo Tenant

**Trigger**: Usuario se registra en UI o via API

**Flujo**:
```
1. Auth Gateway: Validar email + contraseña
2. sys_auth: Insertar nuevo usuario (Capa 0 global)
3. sys_memberships: Asignar tier (Basic/Premium, fecha expiración)
4. TenantDBFactory: Crear folder /tenants/{user_id}/
5. bootstrap_tenant_template(): Clonar usr_template.db → {user_id}/aethelgard.db
6. sys_audit_logs: Registrar "Tenant {uuid} created" con TRACE_ID
7. Response: JWT token para new user
```

**Validaciones Pre-Provisioning**:
- ✅ Email único (no duplicado)
- ✅ Password cumple política (8+ chars, uppercase, number)
- ✅ No existen datos previos (idempotent)

**Estado Post-Provisioning**:
- Usuario puede autenticarse
- BD aislada está lista
- Zero cross-tenant data leakage garantizado

### Deprovisioning: Eliminar Tenant Obsoleto

**Precondiciones (CRÍTICAS)**:
- ✅ No hay posiciones abiertas en broker (MT5, etc.)
- ✅ No hay suscripción activa (o ya expiró)
- ✅ Confirmación de usuario o admin
- ✅ Backup completo en `backups/` con timestamp

**Procedimiento Seguro**:
```bash
# Script: scripts/maintenance/cleanup_obsolete_tenants.py

for tenant_uuid in OBSOLETE_TENANTS:
    1. Backup: data_vault/tenants/{uuid}/ → backups/{uuid}_YYYYMMDD_hhmmss/
    2. Verify: SELECT * FROM {uuid}.usr_positions WHERE status='OPEN'
       → IF any open → ABORT (manual review required)
    3. Archive: Mover DB a backups/ para auditoría histórica
    4. Delete: rm -rf data_vault/tenants/{uuid}/
    5. Audit Log: sys_audit_logs INSERT: "Tenant {uuid} deleted"
    6. Verify: Confirm folder gone, no orphaned files
```

**Auditoría Post-Deprovisioning**:
- ✅ Backup intacto e indexado
- ✅ Carpeta eliminada
- ✅ sys_auth: usuario marcado como `inactive`
- ✅ sys_memberships: estatus `Archived`
- ✅ TRACE_ID documentado (quién, cuándo, por qué)

**Retención de Datos**:
- **ACTIVA producción**: Indefinida
- **ARCHIVADA**: 7 años (cumplimiento legal)
- **TEST/DEMO**: 30 días (post-eliminación, luego purgar backups)

### Limpiar Tenants Obsoletos: Procedimiento Operacional

**Cuando ejecutar**:
- Semanalmente (script cron)
- Post-expiración de trial (7 días después)
- Manual si se solicita cierre de cuenta

**Validación Final**:
```bash
# Verificar sincronización post-limpieza
python scripts/utilities/verify_tenant_consistency.py

# Output esperado:
# ✅ TENANT alice_uuid: DELETED (backup: backups/alice_uuid_20260315_120000/)
# ✅ TENANT bob_uuid: DELETED (backup: backups/bob_uuid_20260315_120000/)
# ✅ No orphaned files
# ✅ sys_auth consistency: OK
```

#### Lecciones Aprendidas (Trace_ID: SECURITY-TENANT-ISOLATION-2026-001)

**Problem**: Endpoint `GET /api/edge/history` no aplicaba aislamiento multi-tenant aunque autenticación y BD aislada existían.

**Root Cause**: Usar `_get_storage()` (compartido) en lugar de `TenantDBFactory.get_storage(token.tid)` (aislado). Inconsistencia arquitectónica permitida por:
1. No validar automáticamente el patrón (falta de audit scanner)
2. No tener tests de endpoint data isolation
3. No incluir validación HTTP en suite de tests

**Why Not Detected Earlier?**
- `validate_all.py` NO ejecutaba tests de integridad HTTP/API
- NO hay validación de "contratos" que validen autenticación + aislamiento en endpoints
- Tests existentes eran de lógica pura, no de endpoints

**Solution**:
1. Crear `TenantDBFactory.get_storage(token.tid)` en todos los endpoints afectados
2. Automatizar validación con `tenant_isolation_audit.py` (parte de validate_all.py)
3. Crear security test suite para aislamiento multi-tenant
4. Documentar patrones obligatorios en DEVELOPMENT_GUIDELINES.md

**Prevention for Future**:
- Endpoint Audit Scanner valida TenantDBFactory usage en cada commit
- Security tests previenen regresiones (parte de CI/CD)
- Rules T1-T4 documentadas como "Aislamiento (Multitenancy)" en DEVELOPMENT_GUIDELINES.md
- Validación inteligente: Si hay token en signature, MUST use TenantDBFactory

### Membership Engine
Control de acceso granular basado en niveles (Basic, Pro, Institutional). Las características y señales están filtradas por nivel de suscripción, permitiendo monetización SaaS sin duplicación de lógica.

### User Management CRUD (Fase X.2 - IMPLEMENTADA)

**Propósito**: Admin dashboard para crear, leer, actualizar y eliminar usuarios con seguridad, trazabilidad y soft delete policy.

#### Implementación

**Arquitectura de Capas** (Clean Architecture + DI Obligatoria):
```
Router (HTTP)
    ↓ Depends()
AdminService (Business Logic)
    ↓ Inyección
AuthRepository (Persistencia)
    ↓ SQL
sys_users + sys_audit_logs (BD Global)
```

**Backend (API REST)**:
- **5 Endpoints CRUD** en `/api/admin/users` (`core_brain/api/routers/admin.py`):
  - `GET /api/admin/users` → List all users
  - `GET /api/admin/users/{user_id}` → Get user details
  - `POST /api/admin/users` → Create new user (email, password, role, tier)
  - `PUT /api/admin/users/{user_id}` → Update user (role/status/tier)
  - `DELETE /api/admin/users/{user_id}` → Soft delete user

**AdminService** (`core_brain/services/admin_service.py`) - Capa de Orquestación:
- Recibe `AuthRepository` inyectado en `__init__`
- Métodos tipados:
  - `list_all_users(include_deleted: bool) -> List[Dict[str, Any]]`
  - `get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]`
  - `create_user(email, password_hash, role, tier, ...) -> str` (retorna user_id)
  - `update_user_role/status/tier(user_id, new_value, updated_by) -> bool`
  - `soft_delete_user(user_id, updated_by) -> bool`
- Validaciones de negocio: Lock-out prevention, self-deletion check, soft delete enforcement
- **Patrón obligatorio**: NO instancia AuthRepository; la recibe inyectada

**AuthRepository** (`data_vault/auth_repo.py`) - Capa de Persistencia:
- 15 typed methods: get_user_by_id, list_all_users, create_user, update_user_*, soft_delete_user, log_audit
- SSOT compliance: All data in `global/aethelgard.db` (sys_users + sys_audit_logs tables)
- Soft delete policy: Status field (active|suspended|deleted), never hard delete

**Frontend (React + TypeScript)**:
- **UserManagement.tsx component** (480+ lines):
  - CRUD UI: Create form, List table, Edit inline, Delete with confirmation
  - Security: No self-modification, no self-deletion
  - Styling: GlassPanel, Lucide icons, Tailwind (consistent with app)
- **ConfigHub integration**: New "User Management" tab (admin-only visible)

**RBAC Decorators** (`core_brain/api/dependencies/rbac.py`):
- `@require_admin` - Validate ADMIN role
- `@require_trader` - Validate TRADER role
- `@require_role()` - Factory for arbitrary role validation
- Logging: All unauthorized attempts logged
- HTTP 403 (Forbidden) for access denied

#### Seguridad Implementada
- **Role-based access control**: Only ADMIN can access /api/admin/* endpoints
- **Lock-out prevention**: Admin cannot change own role
- **Self-deletion prevention**: Admin cannot delete own account
- **Soft delete policy**: Records never deleted (compliance/audit trail)
- **Audit logging**: Every change logged in sys_audit_logs with trace_id
- **Type hints 100%**: All methods, parameters, returns fully typed

#### Testing
- **21 tests** (100% pass rate):
  - Create: trader/admin users ✅
  - Read: by ID, by email, list all, list by role/status ✅
  - Update: role, status, tier ✅
  - Delete: soft delete preserves records ✅
  - Audit: log create/update/delete ✅
  - Edge cases: duplicates, nonexistent, idempotence ✅
- **System validation**: validate_all.py passses 100% (24/24 modules)

#### Campos de Usuario
- `id` (UUID)
- `email` (text, unique)
- `password_hash` (bcrypt)
- `role` (admin|trader)
- `status` (active|suspended|deleted)
- `tier` (BASIC|PREMIUM|INSTITUTIONAL)
- `created_at`, `updated_at`, `deleted_at` (ISO timestamps)
- `created_by`, `updated_by` (admin_id who made change)

#### Gobernanza
- ✅ SSOT: Single database source of truth (sys_users in global/aethelgard.db)
- ✅ `sys_*` prefix: Convention for global tables
- ✅ Soft delete: Compliance with data retention regulations
- ✅ Audit trail: Trace every change with admin_id + trace_id

### Broker Account Management (Fase X.3 - Arquitectura SaaS Multi-Broker)

**Propósito**: Permitir que cada trader gestione múltiples cuentas broker (MT5, NT8, etc.) con segregación clara entre:
- **Capa 0 (Global)**: `sys_broker_accounts` - Cuentas DEMO del sistema para data feeds
- **Capa 1 (Per-Tenant)**: `usr_broker_accounts` - Cuentas personales del trader para ejecución

#### Arquitectura de 2 Capas

**Capa 0: Sistema Global** (`data_vault/global/aethelgard.db`):
```sql
CREATE TABLE sys_broker_accounts (
    id TEXT PRIMARY KEY,                    -- UUID
    broker_name TEXT NOT NULL,              -- 'MT5', 'NT8', 'BINANCE'
    account_type TEXT DEFAULT 'DEMO',       -- DEMO only (no REAL)
    connector_class TEXT,                   -- Python connector class
    is_enabled BOOLEAN DEFAULT TRUE,        -- ¿está activo?
    
    -- Credenciales del sistema (encriptadas)
    credentials_encrypted TEXT,             -- JSON: {login, password, server}
    
    -- Metadata
    balance DECIMAL(15,2),                  -- Saldo actual (cached)
    last_sync_utc TIMESTAMP,                -- Última sincronización
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Uso**: 
- Sistema obtiene datos (precios, calendarios económicos, feeds)
- NO se ejecutan trades en estas cuentas (DEMO only)
- Admin gestiona para asegurar data availability

**Capa 1: Por Trader** (`data_vault/tenants/{user_id}/aethelgard.db`):
```sql
CREATE TABLE usr_broker_accounts (
    id TEXT PRIMARY KEY,                    -- UUID
    user_id TEXT NOT NULL,                  -- Foreign key → users
    broker_name TEXT NOT NULL,              -- 'MT5', 'NT8', 'BINANCE'
    broker_account_id TEXT NOT NULL,        -- ID en el broker (MT5 account number)
    
    -- Configuración
    account_type TEXT DEFAULT 'DEMO',       -- 'REAL' | 'DEMO' (usuario elige)
    account_status TEXT DEFAULT 'ACTIVE',   -- 'ACTIVE' | 'SUSPENDED' | 'CLOSED'
    
    -- Credenciales (encriptadas con Fernet)
    credentials_encrypted TEXT,             -- JSON: {login, password, server}
    
    -- Limits & Risk per trading account
    daily_loss_limit DECIMAL(10,2),         -- Máxima pérdida diaria (USD)
    max_position_size DECIMAL(10,4),        -- Máximo volumen por trade
    max_open_positions INTEGER DEFAULT 3,   -- Máximo # posiciones simultaneas
    
    -- Metadata
    balance DECIMAL(15,2),                  -- Saldo actual (cached)
    equity DECIMAL(15,2),                   -- Equity actual (cached)
    last_sync_utc TIMESTAMP,                -- Última sincronización
    
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, broker_name, broker_account_id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);
```

**Uso**:
- Trader gestiona SUS cuentas (1 o varias)
- Ejecución de trades ocurre en estas cuentas (REAL o DEMO del trader)
- Cada trader ve/controla solo sus cuentas (aislamiento + seguridad)

#### Segregación de Responsabilidades

| Aspecto | `sys_broker_accounts` | `usr_broker_accounts` |
|--------|----------------------|-----------------------|
| **Sistema** | Capa 0 (global) | Capa 1 (per-tenant) |
| **Propósito** | Data feeds | Trading execution |
| **Tipo Cuenta** | DEMO only | REAL o DEMO (trader elige) |
| **Quién Accede** | Sistema + Admin | Trader + Admin |
| **Operaciones** | Lectura de datos | Ejecución de trades |
| **Aislamiento** | N/A (compartida) | Por user_id (completamente aislada) |
| **Credenciales** | Encriptadas (admin) | Encriptadas (user owns) |

#### Flujo de Trading Seguro

```
1. Trader inicia sesión (JWT token con user_id)
   ↓
2. TradeClosureListener recibe evento de broker
   - Extrae user_id del JWT/token
   - Consulta usr_broker_accounts[user_id] para obtener account_type (REAL|DEMO)
   - Si no existe → Default DEMO (fail-safe)
   ↓
3. Executor valida:
   - ¿Token.user_id == signal.user_id? (ownership)
   - ¿usr_broker_accounts existe para user_id + broker? (account active)
   - ¿account_status == 'ACTIVE'? (allowed)
   ↓
4. Si todo OK → Ejecuta trade
   - Registra con account_type correcta (REAL del usuario, no sistema)
   - Auditar en sys_audit_logs (quién, cuándo, cuenta)
   ↓
5. RiskManager monitorea:
   - daily_loss_limit por cuenta
   - max_position_size per trade
   - max_open_positions en paralelo
```

#### Encriptación de Credenciales

```python
from cryptography.fernet import Fernet

class CredentialVault:
    def __init__(self, encryption_key: str):
        self.cipher = Fernet(encryption_key)
    
    def encrypt_credentials(self, creds: Dict) -> str:
        """Encrypt {login, password, server} to single encrypted string"""
        json_creds = json.dumps(creds)
        encrypted = self.cipher.encrypt(json_creds.encode())
        return encrypted.decode()
    
    def decrypt_credentials(self, encrypted: str) -> Dict:
        """Decrypt back to {login, password, server}"""
        decrypted = self.cipher.decrypt(encrypted.encode())
        return json.loads(decrypted.decode())
```

**Key Management**:
- Encryption key en `config/` o environment variable (NEVER in code)
- Key rotation strategy (plan: quarterly)
- Credentials NEVER logged (risk exposure)

#### Multi-Tenant Security

**Trader A NUNCA puede acceder cuentas de Trader B:**

```python
# ✅ CORRECTO (broker_account_service.py):
async def get_active_account(user_id: str, broker_name: str) -> Dict:
    return storage.fetch_one("""
        SELECT * FROM usr_broker_accounts 
        WHERE user_id = ? AND broker_name = ? AND account_status = 'ACTIVE'
    """, (user_id, broker_name))
    # user_id garantiza aislamiento técnico (storage es per-tenant)

# ❌ NUNCA (falla de seguridad):
async def get_account(account_id: str) -> Dict:
    return storage.fetch_one(
        "SELECT * FROM usr_broker_accounts WHERE id = ?", (account_id,)
    )
    # Sin user_id filter, podría retornar cuenta de otro usuario
```

**Validación per request:**

```python
@router.post("/accounts/{account_id}/activate")
async def activate_account(
    account_id: str, 
    token: TokenPayload = Depends(get_current_active_user)
):
    storage = TenantDBFactory.get_storage(token.sub)
    
    # Verificar propiedad antes de modificar
    account = storage.fetch_one(
        "SELECT * FROM usr_broker_accounts WHERE id = ? AND user_id = ?",
        (account_id, token.sub)  # user_id validation obligatoria
    )
    
    if not account:
        raise HTTPException(403, "Not owner of this account")
    
    # Safe to update
    storage.execute(
        "UPDATE usr_broker_accounts SET account_status='ACTIVE' WHERE id=?",
        (account_id,)
    )
```

#### Rate Limiting por Cuenta

```python
async def check_daily_loss_limit(
    user_id: str, 
    account_id: str, 
    trade_loss: Decimal
) -> bool:
    """Enforce daily loss limit configured per account"""
    
    account = storage.fetch_one(
        "SELECT daily_loss_limit FROM usr_broker_accounts WHERE id=? AND user_id=?",
        (account_id, user_id)
    )
    
    if not account:
        return False  # Account not found, fail-secure
    
    today_loss = storage.fetch_one("""
        SELECT SUM(ABS(profit)) as total_loss FROM usr_trades
        WHERE user_id=? AND broker_account_id=? 
        AND DATE(close_time)=DATE('now')
        AND profit < 0
    """, (user_id, account_id))
    
    total_so_far = today_loss['total_loss'] or Decimal(0)
    
    if total_so_far + trade_loss > account['daily_loss_limit']:
        logger.warning(f"LOSS LIMIT: User {user_id} exceeded on account {account_id}")
        return False
    
    return True
```

#### Gobernanza

- ✅ **SSOT**: sys_broker_accounts global, usr_broker_accounts per-tenant
- ✅ **Encriptación**: Fernet obligatoria para credenciales
- ✅ **Aislamiento**: user_id en TODAS las queries de usr_broker_accounts
- ✅ **Audit Trail**: INSERT/UPDATE/DELETE en sys_audit_logs
- ✅ **Type Hints**: 100% en BrokerAccountService
- ✅ **Error Handling**: Fail-secure (default DEMO si no existe account)

## 🖥️ UI/UX REPRESENTATION
*   **Auth Terminal**: Interfaz de acceso "Premium Dark" con visualización de handshake técnico.
*   **Tenant Badge**: Indicador persistente en el header con el `tenant_id` activo y estado de cifrado de la sesión.
*   **Membership Shield**: Menú de perfil que muestra las capacidades desbloqueadas según el rango del usuario.
*   **Admin Users Panel**: Settings → User Management tab para CRUD de usuarios (admin-only)
*   **Audit Monitor**: Time-real visualization de validación de aislamiento multi-tenant (Tenant Isolation Scanner, Tenant Security tests)
*   **Security Status Badge**: Indicator en dashboard mostrando estado de compliance multi-tenant (8 validation vectors incluyendo "Multi-Tenant" y "Auth Isolation"), RBAC y User Management

## 📈 Roadmap del Dominio
- [x] Implementación de JWT y rotación de secretos.
- [x] Despliegue de esquemas SQLite aislados.
- [x] Aislamiento de endpoints HTTP con TenantDBFactory (47/47 compliant).
- [x] Audit Scanner para validación continua de Tenant Isolation.
- [x] Security Test Suite para aislamiento multi-tenant.
- [x] Documentación de Reglas T1-T4 en DEVELOPMENT_GUIDELINES.md.
- [ ] HTTP Contract Tests (autenticación + autorización flujos end-to-end).
- [ ] OWASP Top 10 Security Validation en CI/CD.
- [ ] Lógica de filtrado de módulos por suscripción (Membership Engine).

