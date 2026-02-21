# AETHELGARD: SEMANTIC VERSIONING

## 📌 Protocolo de Versionado
Aethelgard sigue el estándar de **Semantic Versioning 2.0.0** (SemVer) para garantizar la trazabilidad y la estabilidad de las integraciones.

---

### 📝 Estructura: `MAJOR.MINOR.PATCH`

1.  **MAJOR**: Cambios profundos en la arquitectura que rompen la compatibilidad (e.g., cambio total en el esquema de base de datos o en el protocolo WebSocket).
2.  **MINOR**: Nuevas funcionalidades o mejoras significativas sin romper la compatibilidad (e.g., una nueva estrategia, un nuevo conector, o el motor de confluencia).
3.  **PATCH**: Correcciones de bugs menores, optimizaciones de rendimiento y ajustes de documentación.

---

### 🏷️ Ciclo de Vida del Software
- **Alpha**: Versiones en desarrollo activo, altamente volátiles.
- **Beta**: Versiones con features completas en fase de prueba de estabilidad.
- **Stable / Production Ready**: Versiones validadas con `validate_all.py` y auditadas.

---

### 📅 Control de Documentación
Cada cambio en el código debe acompañarse de una actualización en el **[SYSTEM_LEDGER.md](SYSTEM_LEDGER.md)** vinculando la versión técnica con los cambios realizados.
