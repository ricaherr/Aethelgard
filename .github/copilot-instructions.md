# AETHELGARD: SYSTEM RULES & ARCHITECTURE

## 🎯 Misión
Sistema autónomo, proactivo y agnóstico de trading multihilo. Capacidad de auto-calibración y enfoque comercial (SaaS).

## 🧠 Reglas de Oro para la IA
1. **Autonomía Proactiva**: El sistema no espera datos, los busca (ScannerEngine).
2. **Independencia de Código**: La lógica en `core_brain` debe ser agnóstica. No importar librerías de brokers (MT5/Rithmic) directamente fuera de `connectors/`.
3. **Gestión de Recursos**: Todo proceso pesado debe respetar el `cpu_limit_pct` para no bloquear la máquina del usuario.
4. **Escalabilidad Comercial**: Las señales y funciones deben filtrarse por niveles de membresía (Basic/Premium) definidos en `config/modules.json`.
5. **Auto-Calibración**: El sistema debe priorizar el aprendizaje de los datos en `data_vault` para ajustar `dynamic_params.json`.
6. **Seguridad Primero**: Validar todas las entradas externas (datos de mercado, configuraciones de usuario) antes de procesarlas.
7. **Documentación Continua**: Cada módulo nuevo debe incluir documentación clara y ejemplos de uso, en el archivo AETHELGARD_MANIFIESTO.md.
8. **Codigo en el chat**: no agregar codigo completo directamente en la conversación, solo fragmentos relevantes y explicaciones.

## 🛠️ Stack Tecnológico
- **Backend**: Python 3.12+ (Asyncio, FastAPI).
- **UI**: Streamlit (Dashboard multi-pestaña).
- **Data**: SQLite (Persistencia segmentada por mercado).
- **Conexiones**: WebSockets para tiempo real.

## Idioma
- Comunicación siempre en **Español**
- Código y comentarios en **Inglés**

## Metodología
- **TDD obligatorio**: Test primero, luego código
- **Cero Sorpresas**: Explicar antes de implementar
- Seguir estilo del proyecto existente

## Trading Rules
- Risk per trade: 1% del capital
- Régimen VOLATILE/RANGE: reducir a 0.5%
- 3 pérdidas consecutivas = Lockdown mode

## Flujo de Trabajo (Workflow)
1. Definir requerimientos técnicos.
2. Crear archivo de test en `tests/`.
3. Ejecutar test (debe fallar).
4. Implementar código mínimo en `core_brain/`.
5. Ejecutar test (debe pasar).
6. Actualizar `AETHELGARD_MANIFESTO.md`.