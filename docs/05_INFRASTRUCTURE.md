# AETHELGARD: 05 INFRASTRUCTURE

## 🛠️ Núcleo Técnico y Persistencia
Capa de cimientos, servidores y Single Source of Truth (SSOT).

---

### 🗄️ Capa de Datos (Data Vault)
- **StorageManager**: Persistencia segmentada mediante Mixins.
- **SSOT Policy**: Prohibición de archivos JSON volátiles para lógica de negocio.
- **Database Self-Healing**: Reparación automática de esquemas en startup.

---

### 🌐 Servicios de Red
- **FastAPI / WebSockets**: Infraestructura asíncrona de alta concurrencia.
- **Orquestador Resiliente**: Bucle de control con reconstrucción de estado tras crashes.
- **API Unified Endpoints**: Interfaz única para UI y servicios externos.

---

### 🏥 Salud y Diagnóstico
- **System Health Monitor**: Vigía de latencia, CPU y recursos.
- **QA Guard**: Auditoría estática de calidad y aislamiento de código.
- **Manual Overrides**: Control de satélites y talle de emergencia.
