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
Factoría de bases de datos que garantiza que el `tenant_id` sea inyectado en cada consulta y que cada cliente tenga su propia base de datos aislada.

#### Arquitectura Multi-Tenant
- **Por-Tenant Database Isolation**: Cada tenant obtiene su base de datos exclusiva en `data_vault/tenants/{tenant_id}/aethelgard.db`
- **TenantDBFactory Pattern**: Factory singleton que crea y cachea `StorageManager` instances por tenant
  ```python
  # Patrón correcto:
  storage = TenantDBFactory.get_storage(token.tid)  # BD aislada del tenant
  
  # Patrón PROHIBIDO:
  storage = _get_storage()  # BD genérica compartida entre todos
  ```
- **Schema Consistency**: Cada BD de tenant usa el mismo schema (`data_vault/schema.py`) pero datos completamente aislados
- **Zero Cross-Tenant Data Leakage**: Imposible acceder a datos de otro tenant incluso si alguien contornea autenticación

#### Reglas Obligatorias de Implementación

**RULE T1**: Si endpoint tiene `token: TokenPayload` en firma → **DEBE** usar `TenantDBFactory.get_storage(token.tid)`
```python
# ❌ INCORRECTO:
@router.get("/signals")
async def get_signals(token: TokenPayload = Depends(get_current_active_user)):
    storage = _get_storage()  # ¡ERROR! BD compartida
    return storage.get_signals()  # Datos filtrados por tenant_id post-facto

# ✅ CORRECTO:
@router.get("/signals")
async def get_signals(token: TokenPayload = Depends(get_current_active_user)):
    storage = TenantDBFactory.get_storage(token.tid)  # BD aislada por tenant
    return storage.get_signals()  # Solo datos del tenant en BD
```

**RULE T2**: Si endpoint retorna datos del usuario → **DEBE** estar en BD aislada (no filtro post-facto)
```python
# ❌ PROBLEMATIC (aunque funcione):
tuning_history = storage.get_all_tuning_history()
filtered = [h for h in tuning_history if h['tenant_id'] == token.tid]  # Filtro manual

# ✅ SEGURO:
tuning_history = storage.get_tuning_history()  # BD ya es del tenant
# (retorna solo datos de ese tenant, no hay filtro necesario)
```

**RULE T3**: Si endpoint modifica datos → **DEBE** validar que `owner_id == token.tid`
```python
@router.post("/update_strategy")
async def update_strategy(req: StrategyUpdate, token: TokenPayload = Depends(...)):
    storage = TenantDBFactory.get_storage(token.tid)
    strategy = storage.get_strategy(req.strategy_id)
    
    if strategy['owner_id'] != token.tid:  # Validación explícita de propiedad
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

## 🖥️ UI/UX REPRESENTATION
*   **Auth Terminal**: Interfaz de acceso "Premium Dark" con visualización de handshake técnico.
*   **Tenant Badge**: Indicador persistente en el header con el `tenant_id` activo y estado de cifrado de la sesión.
*   **Membership Shield**: Menú de perfil que muestra las capacidades desbloqueadas según el rango del usuario.
*   **Audit Monitor**: Time-real visualization de validación de aislamiento multi-tenant (Tenant Isolation Scanner, Tenant Security tests)
*   **Security Status Badge**: Indicator en dashboard mostrando estado de compliance multi-tenant (8 validation vectors incluyendo "Multi-Tenant" y "Auth Isolation")

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
