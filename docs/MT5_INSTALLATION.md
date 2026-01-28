# Guía Rápida: Instalación de MetaTrader 5

## Objetivo
Instalar MT5 Terminal para habilitar trading real en cuentas demo de Forex.

## Pasos de Instalación

### 1. Descargar MT5

**Opción A - Sitio Oficial:**
1. Visita: https://www.metatrader5.com/en/download
2. Haz clic en "Download MetaTrader 5"
3. Ejecuta el instalador descargado

**Opción B - Broker Directo (Recomendado):**
- **Pepperstone**: https://pepperstone.com/en/trading-platforms/metatrader-5
- **IC Markets**: https://www.icmarkets.com/global/en/trading-platforms/metatrader-5
- **XM**: https://www.xm.com/metatrader-5

> **Ventaja**: Al descargar desde el broker, MT5 viene preconfigurado con sus servidores.

### 2. Instalar MT5

1. Ejecuta el instalador `mt5setup.exe`
2. Acepta los términos y condiciones
3. Espera a que complete la instalación (2-3 minutos)
4. **IMPORTANTE**: Cierra MT5 después de la instalación

### 3. Configurar Cuenta Demo

Una vez instalado MT5, ejecuta el script de configuración de Aethelgard:

```bash
python scripts/setup_mt5_demo.py
```

El script te guiará para:
1. Seleccionar un broker
2. Ingresar credenciales de cuenta demo
3. Validar la conexión
4. Guardar la configuración

### 4. Crear Cuenta Demo (si no tienes una)

Si no tienes una cuenta demo, créala directamente desde el broker:

**Pepperstone:**
1. Visita: https://pepperstone.com/en/demo-account
2. Completa el formulario
3. Recibirás credenciales por email (inmediato)

**IC Markets:**
1. Visita: https://www.icmarkets.com/global/en/open-account/demo
2. Completa el formulario
3. Credenciales por email (inmediato)

**XM:**
1. Visita: https://www.xm.com/demo-account
2. Completa el formulario
3. Credenciales por email (inmediato)

### 5. Verificar Instalación

Ejecuta el script de prueba:

```bash
python scripts/test_mt5_system.py
```

Esto validará:
- ✅ MT5 instalado correctamente
- ✅ Configuración válida
- ✅ Conexión exitosa
- ✅ Ejecución de trade de prueba

---

## Solución de Problemas

### Error: "MT5 x64 not found"
**Causa**: MT5 no está instalado o la ruta no es estándar.
**Solución**: 
1. Reinstalar MT5 desde el sitio oficial
2. Usar la ruta de instalación por defecto

### Error: "Login failed"
**Causa**: Credenciales incorrectas o cuenta expirada.
**Solución**:
1. Verificar login/password
2. Verificar nombre del servidor (ej: "Pepperstone-Demo")
3. Crear nueva cuenta demo (expiran en 30 días)

### Error: "Could not initialize MT5"
**Causa**: MT5 está abierto o proceso bloqueado.
**Solución**:
1. Cerrar MT5 completamente
2. Verificar en Task Manager que no haya procesos `terminal64.exe`
3. Reintentar

---

## Próximos Pasos

Una vez instalado MT5 y configurada la cuenta demo:

1. **Ejecutar sistema completo:**
   ```bash
   python start.py
   ```

2. **Abrir Dashboard:**
   - URL: http://localhost:8503
   - Tab: "💰 Análisis de Activos"

3. **Abrir MT5 Terminal:**
   - Ver trades en tiempo real
   - Tab: "Toolbox" → "Trade"
   - Filtrar por Magic Number: 234000

4. **Monitorear:**
   - Logs en `logs/production.log`
   - Señales en Dashboard
   - Trades en MT5

---

## Tiempo Estimado

- Descarga: 2-3 minutos
- Instalación: 2-3 minutos
- Configuración cuenta demo: 5 minutos
- **Total: ~10 minutos**
