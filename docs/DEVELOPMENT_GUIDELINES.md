# 📖 AETHELGARD: DEVELOPMENT GUIDELINES (BIBLIA DE INGENIERÍA)

## 🛡️ Propósito
Establecer los estándares innegociables para el desarrollo del ecosistema Aethelgard, garantizando la escalabilidad SaaS, la integridad financiera y una experiencia de usuario de nivel institucional.

## 1. Backend Rules: La Fortaleza Asíncrona
*   **Aislamiento (Multitenancy)**: El `tenant_id` es el átomo central. Ninguna función de base de datos o lógica de negocio puede ejecutarse sin la validación del contexto del usuario.
*   **Agnosticismo de Datos**: El Core Brain no debe conocer detalles del broker (MT5/FIX). Debe trabajar solo con Unidades R y estructuras normalizadas. All connectors must translate broker-specific data to Aethelgard canonical forms.
*   **Rigor de Tipado**:
    *   Uso estricto de **Pydantic** para todos los esquemas de datos y validaciones de entrada/salida.
    *   Uso obligatorio de `Decimal` para todos los cálculos financieros. **PROHIBIDO** el uso de `float` en lógica de dinero para evitar errores de redondeo IEEE 754.
*   **1.4. Protocolo "Explorar antes de Crear"**: Antes de implementar cualquier nueva función o clase, el Ejecutor DEBE realizar una búsqueda semántica en el repositorio actual para verificar si ya existe una lógica similar. Se prohíbe la duplicación de código; en su lugar, se debe refactorizar la función existente para que sea reutilizable.
*   **1.5. Higiene de Masa (Regla <30KB)**: Ningún archivo puede superar los 30KB o las 500 líneas. Si un componente crece por encima de este límite, su fragmentación en submódulos es obligatoria e inmediata.
*   **1.6. Patrones Obligatorios**: Se exige el uso estricto de Repository Pattern para datos y Service Layer para lógica. Los Routers de FastAPI solo orquestan.

## 2. Frontend Rules: La Terminal de Inteligencia
*   **Estética Terminal**: Prohibido el uso de componentes de librerías comunes sin personalización. Estética **Bloomberg-Dark** (#050505, acentos cian/neón).
*   **Densidad de Datos**: Diseñar para el experto. Mostrar datos de alta fidelidad sin saturar, utilizando transparencias y capas (Glassmorphism).
*   **Micro-interacciones**: Los cambios de estado deben "pulsar" o "deslizarse". La UI debe sentirse como un organismo vivo y reactivo.
*   **Estado Centralizado**: El frontend es una capa de visualización. La lógica de trading y gestión reside exclusivamente en el Backend.

## 3. Protocolo de Higiene y Limpieza
*   **3.1. Gestión de Temporales**: Todo script de prueba, archivo .tmp, o código de depuración debe ser eliminado INMEDIATAMENTE después de cumplir su función. No se permite la persistencia de "basura técnica" en el repositorio principal.
*   **3.2. Comentarios de Producción**: Se prohíbe dejar bloques de código comentados ("muertos"). Si el código no es funcional, se elimina. La trazabilidad reside en el Git, no en los comentarios.

## 4. Gestión de Excepciones y Veto
*   **4.1. Fail-Safe**: Todo proceso financiero debe incluir un bloque try-except específico con rollback de base de datos en caso de fallo.
*   **4.2. Veto Técnico**: La autonomía delegada se detiene si los signos vitales (latencia > 500ms o pérdida de WS) se degradan.

## 🏷️ Protocolo de Versionado (SemVer)
Aethelgard sigue el estándar **Semantic Versioning 2.0.0**:
*   **MAJOR**: Cambios arquitectónicos que rompen compatibilidad.
*   **MINOR**: Nuevas funcionalidades (estrategias, conectores) sin rotura.
*   **PATCH**: Bugfixes, optimizaciones y documentación.

Toda versión debe validarse con `validate_all.py` antes de su desplieue y registrarse en el `SYSTEM_LEDGER.md`.

## ⚖️ Governance (Proceso de Validación)
Cada nueva funcionalidad o Historia de Usuario (HU) debe cumplir con:
1.  **Representación en UI**: Ninguna lógica de backend está "terminada" hasta que tenga su widget o visualización correspondiente en la Terminal.
2.  **Validación de Aislamiento**: Pruebas explícitas de que los datos no se filtran entre `tenant_id`s.
3.  **Agnosticismo**: Verificación de que el Core Brain sigue funcionando si se cambia el conector de datos.
4.  **Trazabilidad**: Toda tarea debe estar registrada en el [Central Backlog](../governance/BACKLOG.md) siguiendo la jerarquía de los 10 Dominios.

---
*Este documento es dinámico y representa el estándar de excelencia técnica de Aethelgard.*
