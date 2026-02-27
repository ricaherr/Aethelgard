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

- [x] **Tenant Context Auto-Injection (HU 8.2)**
  - Sustituir extracción manual por `get_current_active_user`.
  - Inyectar `tenant_id` hacia `StorageManager` en los routers (Trading, Risk, Market).
  - Protección JWT consolidada.

- [x] **Intelligence Terminal UI (HU 9.1)**
  - Estandarización estética Premium Dark / Glassmorphism.
  - Implementación de AuthGuard y MainLayout.
  - Saneamiento y refactorización de `App.tsx`.

---

## 📸 Snapshot de Contexto

| Métrica | Valor |
|---|---|
| **Estado de Persistencia** | Aislada y blindada en Multi-Tenant via TenantDBFactory |
| **Seguridad de Acceso** | Seguridad JWT + Aislamiento por Middleware |
| **Masa de server.py** | <30KB |
| **Masa de UI (Build)** | <800KB (733KB) |
| **Build Stability** | ✅ Production Build SUCCESS |
| **Integridad** | 17/17 tests PASSED |
| **Versión Global** | v3.5.0 |
