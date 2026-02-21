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

### 🏥 Salud y Mantenimiento (Protocolo EDGE Autónomo)
Aethelgard ha evolucionado de un mantenimiento manual PAS a una gestión **EDGE Autónoma** para garantizar operatividad 24/7 sin intervención humana.

#### 🤖 Autonomous Health Service
Un servicio centinela (`core_brain/health_service.py`) supervisa la integridad del sistema:
- **Auto-Auditoría**: Ejecuta validaciones de salud cada hora.
- **Vigía de Recursos**: Monitorea el tamaño de logs y uso de CPU.
- **Propuestas de Gestión**: Detecta problemas y los reporta vía "Thoughts" en la UI, preparando el camino para la auto-reparación autorizada.

#### 📂 Gestión de Logs (Linux Style)
Para evitar archivos masivos que degraden el rendimiento:
- **Base Name**: `logs/main.log`.
- **Rotación Diaria**: Se crea un nuevo archivo cada medianoche (format: `main.log.YYYY-MM-DD`).
- **Retención Estricta**: Mantiene solo los últimos 15 días de logs para optimizar el espacio en disco.
