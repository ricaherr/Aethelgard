# SPRINT 1: SAAS GENESIS

**Inicio**: 25 de Febrero, 2026  
**Objetivo**: Establecer los cimientos de la arquitectura multi-tenant con autenticación y aislamiento de datos.  
**Versión Target**: v3.5.0

---

## 📋 Tareas del Sprint

- [x] **Implementación de JWT Middleware para FastAPI**
  - Crear middleware de validación de tokens JWT en cada request.
  - Definir esquema de claims (user_id, tenant_id, role, exp).
  - Integrar con el pipeline de routers existente.

- [x] **Creación de tabla `users` y `UserRepo`**
  - Diseñar esquema: `users(id, email, password_hash, tenant_id, role, created_at)`.
  - Implementar `UserRepo` con métodos CRUD + autenticación.
  - Endpoints: `POST /api/auth/register`, `POST /api/auth/login`.

- [x] **Desarrollo de la `TenantDBFactory` para aislamiento de bases de datos**
  - Factory que resuelve la conexión SQLite por `tenant_id`.
  - Patrón: `data_vault/{tenant_id}/aethelgard.db`.
  - Migración automática de esquema en primer acceso.

- [x] **Fragmentación de data_vault/storage.py para cumplimiento de Regla de Masa (<30KB)**
  - Identificar dominios en `StorageManager`.
  - Extraer métodos a repositorios especializados.
  - Inyectar repositorios en `StorageManager` (Fachada).

---

## 📸 Snapshot de Contexto

| Métrica | Valor |
|---|---|
| **Estado de Persistencia** | Aislada y blindada en Multi-Tenant via TenantDBFactory |
| **Seguridad de Acceso** | Seguridad JWT + Aislamiento por Middleware |
| **Masa de server.py** | <30KB |
| **Integridad** | 17/17 tests PASSED |
| **Versión Global** | v3.5.0 |
