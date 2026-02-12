# AETHELGARD: SYSTEM RULES & ARCHITECTURE

## 🎯 Misión
Sistema autónomo, proactivo y agnóstico de trading multihilo. Capacidad de auto-calibración y enfoque comercial (SaaS).

## 🧠 Reglas de Oro para la IA
1. **Revisar Antes de Actuar**: SIEMPRE revisar si algo ya existe antes de agregar o modificar. Si existe, evaluar si es mejor modificar lo existente o crear algo nuevo. Aplica a: reglas, funciones, documentación, configuración, tests.
2. **Autonomía Proactiva**: El sistema no espera datos, los busca (ScannerEngine).
3. **Independencia de Código (Arquitectura Agnóstica)**:
   - ✅ **Permitido** importar librerías de brokers (MT5/Rithmic) en:
     - `connectors/` (integración con brokers)
   - ❌ **PROHIBIDO** importar en:
     - `core_brain/` (lógica de negocio agnóstica)
     - `data_vault/` (persistencia agnóstica)
     - `models/` (modelos de datos agnósticos)
     - `scripts/` (utilitarios deben usar connectors)
     - `tests/` (tests deben usar connectors)
4. **Gestión de Recursos**: Todo proceso pesado debe respetar el `cpu_limit_pct` para no bloquear la máquina del usuario.
5. **Escalabilidad Comercial**: Las señales y funciones deben filtrarse por niveles de membresía (Basic/Premium) definidos en `config/modules.json`.
6. **Auto-Calibración**: El sistema debe priorizar el aprendizaje de los datos en `data_vault` para ajustar `dynamic_params.json`.
7. **Seguridad Primero**: Validar todas las entradas externas (datos de mercado, configuraciones de usuario) antes de procesarlas.
8. **Documentación Única**: TODO debe documentarse EXCLUSIVAMENTE en AETHELGARD_MANIFESTO.md. NUNCA crear documentos adicionales (README separados, guías, tutoriales). Un solo archivo de verdad.
9. **Auto-Provisioning**: El sistema debe crear cuentas demo automáticamente en brokers que lo permitan (sin intervención humana). Clasificar brokers: automático vs manual.
10. **Modo DEMO Autónomo**: Si el usuario elige modo DEMO y no existe cuenta, el sistema debe crearla automáticamente. Solo pedir credenciales en brokers que requieren registro manual.
11. **Codigo en el chat**: no agregar codigo completo directamente en la conversación, solo fragmentos relevantes y explicaciones.
12. **Informes Ejecutivos en Chat**: NUNCA crear archivos markdown para reportes, resúmenes o informes de tareas completadas. Entregar SOLO resumen ejecutivo directo en el chat. Los archivos .md son EXCLUSIVAMENTE para documentación técnica permanente (MANIFESTO, ROADMAP).
13. **ROADMAP Obligatorio**: SIEMPRE actualizar ROADMAP.md al inicio de cada tarea mayor con el plan de trabajo. Marcar tareas completadas (✅) conforme se finalizan. El ROADMAP debe reflejar en tiempo real qué se hizo y qué falta.
14. **Single Source of Truth (DB)**: Configuración, credenciales y datos del sistema deben residir en la BASE DE DATOS. NO crear archivos JSON/ENV redundantes. La DB es la única fuente de verdad.
15. **Scripts Mínimos y Útiles**: NO crear scripts de validación/debugging redundantes. Mantener solo los scripts que agregan valor real al usuario final (setup, diagnóstico end-to-end, tests de flujo completo).
16. **Validaciones Completas Obligatorias**: Después de TODA implementación, tests y validación, comprobar que el sistema funciona sin errores (ejecutar validate_all.py + start.py) antes de dar por terminada la tarea
14. **Scripts Mínimos y Útiles**: NO crear scripts de validación/debugging redundantes. Mantener solo los scripts que agregan valor real al usuario final (setup, diagnóstico end-to-end, tests de flujo completo).

## � Reglas de Desarrollo de Código (Resumen - Ver MANIFESTO Completo)

**Nota**: Estas reglas están detalladas en AETHELGARD_MANIFESTO.md (Sección 7: Reglas de Desarrollo de Código). Este es un resumen para referencia rápida de IAs.

1. **Inyección de Dependencias Obligatoria**:
   - Ninguna clase de lógica (RiskManager, Tuner, Executor, Monitor) puede instanciar StorageManager o configuraciones en `__init__`.
   - Todas las dependencias deben pasarse (inyectarse) desde MainOrchestrator o tests.
   - Prohibido: `self.storage = StorageManager()`
   - Obligatorio: `def __init__(self, storage, config): self.storage = storage`

2. **Inmutabilidad de los Tests**:
   - Si un test de lógica de negocio falla, está prohibido modificar el test para "hacerlo pasar".
   - El fallo se corrige en el código de producción.
   - Si crees que el test tiene un bug, pedir permiso explícito explicando la falla lógica.

3. **Single Source of Truth (SSOT)**:
   - Valores críticos (como max_consecutive_losses) no pueden estar hardcodeados.
   - Deben leerse de un archivo de configuración único o de la base de datos compartida por todos los componentes.

4. **Limpieza de Deuda Técnica (DRY)**:
   - Antes de crear una función, buscar si ya existe una similar.
   - Si existe, refactorizar la original para que sea reutilizable.
   - Prohibido crear métodos "gemelos" (ej. `_load_frrom_db` vs `_load_from_db`).

5. **Aislamiento de Tests**:
   - Los tests deben usar bases de datos en memoria (`:memory:`) o temporales.
   - No se permite que un test dependa del estado dejado por un test anterior.

## �🛠️ Stack Tecnológico
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
1. **Actualizar ROADMAP.md** con el plan de tareas.
2. Definir requerimientos técnicos.
3. Crear archivo de test en `tests/`.
4. Ejecutar test (debe fallar).
5. Implementar código mínimo en `core_brain/`.
6. Ejecutar test (debe pasar).
**6.5. ✅ EJECUTAR `validate_all.py`** (OBLIGATORIO antes de documentar)
   - Valida arquitectura (duplicados, imports prohibidos)
   - Valida calidad de código (sintaxis, tipos, complejidad)
   - Ejecuta tests críticos (deduplicación + risk manager)
   - **Si falla** → CORREGIR antes de continuar (NO cambiar tests para que pasen)
   - **Comando**: `python scripts/validate_all.py`
7. **Actualizar ROADMAP.md** marcando tarea como completada (✅).
8. Actualizar `AETHELGARD_MANIFESTO.md`.
**9. 🧹 LIMPIEZA WORKSPACE** (OBLIGATORIO después de completar implementación)
   - Eliminar archivos temporales de debugging (test_*.py, check_*.py en raíz)
   - Mover scripts de diagnóstico a `scripts/utilities/` (QA Guard permite MT5 imports ahí)
   - Verificar que `validate_all.py` pasa 100% (6/6 validaciones OK)
   - Confirmar sistema funcional: `python start.py` sin errores
   - **Comando verificación**: `python scripts/validate_all.py && python -c "print('✅ Sistema limpio y funcional')"`