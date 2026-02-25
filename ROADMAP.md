# AETHELGARD: ESTRATEGIC ROADMAP

**Versión Log**: 3.2.0 (FASE 1: SaaS Foundations - ACTIVO)
**Última Actualización**: 25 de Febrero, 2026 (00:41)

<!-- REGLA DE ARCHIVADO: Cuando TODOS los items de un milestone estén [x], -->
<!-- migrar automáticamente a docs/SYSTEM_LEDGER.md con el formato existente -->
<!-- y eliminar el bloque del ROADMAP. Actualizar la Versión Log. -->

---

## 📈 ROADMAP ESTRATÉGICO (Próximos Hitos)

### 🚀 FASE 1: SAAS FOUNDATIONS (AUTH & ISOLATION) — ACTIVO
**Trace_ID**: SAAS-GENESIS-2026-001  
**Inicio**: 25 de Febrero, 2026  
**Objetivo**: Evolucionar el sistema de un solo usuario a una arquitectura multi-tenant con autenticación JWT y aislamiento de datos por tenant.

- [x] **Manifesto Transformation**: Restructuración del `AETHELGARD_MANIFESTO.md` hacia una Constitución Estratégica.
- [ ] **JWT Middleware**: Implementación de middleware de autenticación JWT para FastAPI.
- [ ] **User Management**: Creación de tabla `users` y `UserRepo` para gestión de identidad.
- [ ] **Tenant Isolation**: Desarrollo de `TenantDBFactory` para aislamiento de bases de datos por cliente.
- [ ] **Validación E2E**: Tests de integración para flujo auth completo + aislamiento de datos.

**Dependencias**: Requiere SSOT 100% SQLite (✅ completado) y server.py modular (✅ completado).

---

### 🌐 EXPANSIÓN COMERCIAL & CONECTIVIDAD
- [ ] **Capa Institutional (FIX API)**: Conexión directa vía FIX para baja latencia en brokers institucionales.

> [!NOTE]
> El historial completo de hitos completados ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).
