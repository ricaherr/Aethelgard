# AETHELGARD: 06 UI/UX STRATEGY (PREMIUM INTELLIGENCE TERMINAL)

**Versión**: 2.0.0 (Milestone 5.5: Darwinismo Algorítmico UI)  
**Última Actualización**: 22 de Febrero, 2026

---

## 🎨 Visión Estética: The Intelligence Terminal

Aethelgard es una **Terminal de Inteligencia Institucional Premium** (no una web app común). El enfoque es crear una interfaz que transmita:
- **Confianza**: Datos en tiempo real, sin placeholders
- **Sofisticación**: Estilo Bloomberg/Reuters Terminal con acentos neón controlados
- **Autonomía**: Visualización del "Darwinismo Algorítmico" (rankings dinámicos, execution modes, scoring)

---

## 🛡️ Principios de Interfaz No Negociables

1. **No Placeholders**: Jamás mostrar cuadros vacíos. Si hay retraso: animación "Brain Waves" o skeleton loading.
2. **Dark First**: Fondo negro puro (#050505), acentos limitados, contraste alto.
3. **Information Density Premium**: Estilo Bloomberg pero legible (font-weight controlado, espacios blancos estratégicos).
4. **Micro-interacciones Vivas**: Todos los componentes deben tener heartbeat/pulse sutil al ritmo del servidor.
5. **Agnóstico de Datos**: Los componentes son reutilizables (no hardcodean valores).

---

## 📐 Paleta de Colores (SSOT)

| Elemento | Color Hex | RGB | Uso |
|----------|-----------|-----|-----|
| **Fondo Principal** | #050505 | 5, 5, 5 | Base de toda pantalla |
| **Acentos Éxito** | #00ffc8 | 0, 255, 200 | TREND regime, compras, healthy systems |
| **Acentos Riesgo** | #ff3333 | 255, 51, 51 | VOLATILE/CRASH regimes, alerts |
| **Acentos Warning** | #ffc107 | 255, 193, 7 | RANGE regime, cautions, SHADOW mode |
| **Panel Glass** | rgba(255,255,255,0.05) | - | Fondo panels semi-transparente |
| **Border Glass** | rgba(255,255,255,0.1) | - | Bordes subtiles |
| **Text Primary** | rgba(255,255,255,0.95) | - | Headers, datos críticos |
| **Text Secondary** | rgba(255,255,255,0.6) | - | Labels, descripciones |
| **Text Tertiary** | rgba(255,255,255,0.4) | - | Timestamps, metadata |

---

## 🔤 Tipografía (Consistente)

- **Headings (h1-h3)**: `font-outfit font-bold`
  - h1: `text-2xl` → EdgeHub header
  - h2: `text-lg` → Panel titles
  - h3: `text-sm` → Section subtitles

- **Body Text**: `font-inter` o default
  - Primary: `text-xs` / `text-[10px]` (datos numéricos)
  - Secondary: `text-[11px]` (descripciones)
  - Tertiary: `text-[9px]` (metadata, timestamps)

- **Monospace**: `font-mono` para valores numéricos/precios

- **Tracking**: `tracking-widest` (UPPERCASE labels), `tracking-tighter` (compactos)

---

## 📦 Componentes Implementados (Milestone 5.5)

### 1. **RegimeBadge** ✅
**Archivo**: `ui/src/components/edge/RegimeBadge.tsx`

**Propósito**: Indicador visual animado del régimen actual (TREND/RANGE/VOLATILE/CRASH)

**Props**:
```tsx
interface RegimeBadgeProps {
    regime: MarketRegime;  // 'TREND' | 'RANGE' | 'CRASH' | 'NEUTRAL'
    size?: 'small' | 'medium' | 'large';
    showLabel?: boolean;
    animated?: boolean;
}
```

**Backend Associated**:
- **Data Source**: `useAethelgard()` hook → `regime` state (WebSocket)
- **Endpoint**: Realtime via `/ws/GENERIC/dashboard_nextgen`

**Visual Features**:
- **Heartbeat Animation**: Escala cíclica (1 → 1.3 → 1) con duración 1.5s
- **Glow Effect**: Sombra radiante dinámica (color varía por régimen)
- **Icons Adaptables**:
  - TREND → TrendingUp (verde)
  - RANGE → PauseCircle (amarillo)
  - CRASH → AlertTriangle (rojo)
  - NEUTRAL → TrendingDown (gris)

**Usage**:
```tsx
<RegimeBadge regime={regime} size="large" showLabel={true} animated={true} />
```

---

### 2. **WeightedMetricsVisualizer** ✅
**Archivo**: `ui/src/components/edge/WeightedMetricsVisualizer.tsx`

**Propósito**: Visualizar pesos dinámicos de métricas por régimen (Darwinismo Algorítmico)

**Props**:
```tsx
interface WeightedMetricsVisualizerProps {
    currentRegime?: MarketRegime;
    height?: number;  // Default 300px
}
```

**Backend Associated**:
- **Endpoint**: `GET /api/regime_configs` (nuevo)
- **Data Structure**: `{ regime_weights: { TREND: {metric: weight}, ... } }`
- **Actualización**: Fetch on mount, WebSocket-ready para futuro

**Visual Features**:
- **Stacked Bar Charts** (CSS-based, sin Recharts):
  - Una barra por régimen (TREND, RANGE, VOLATILE, CRASH)
  - Cada barra apilada muestra proporciones de métrica (profit_factor, win_rate, etc.)
  - Colores: Verde, Azul, Púrpura, Naranja (índice basado)

- **Current Regime Indicator**: Dinámico, muestra desglose detallado de pesos actuales
- **Animaciones**: Entrada fade-in + animación de ancho 0→100% escalonada

**Usage**:
```tsx
<WeightedMetricsVisualizer currentRegime={regime} height={350} />
```

---

### 3. **AlphaSignals (Refactored)** ✅
**Archivo**: `ui/src/components/trader/AlphaSignals.tsx`

**Propósito**: Stream en tiempo real de señales de trading con modo ejecución + puntuación

**Backend Associated**:
- **Data Source**: `useAethelgard()` hook → `signals` array (WebSocket)
- **Endpoint**: `/ws/GENERIC/dashboard_nextgen` → emite `type: 'SIGNAL'`

**Nuevos Campos (Milestone 5.5)**:
- `execution_mode`: 'LIVE' | 'SHADOW' | 'QUARANTINE' (del strategy_ranker)
- `ranking_score`: 0-100 (justificación numérica del modo)

**Visual Features**:
- **Execution Mode Badging**:
  - LIVE → Verde + CheckCircle2 icon
  - SHADOW → Amarillo + PauseCircle icon
  - QUARANTINE → Rojo + AlertCircle icon

- **Ranking Score Display**:
  - Animación pulsante (scale 1 → 1.05 → 1)
  - Justifica por qué la señal está en cada modo
  - Visible en small screens como "Score: XX%"

- **Responsive Layout**:
  - Row: Symbol | Side | Price | Confidence
  - Right section: Mode Badge | Ranking Score | Status | ChevronRight

**Usage**:
```tsx
<AlphaSignals signals={signals} />
// Signal object tiene: execution_mode, ranking_score (nuevos campos)
```

---

### 4. **EdgeHub (Refactored)** ✅
**Archivo**: `ui/src/components/edge/EdgeHub.tsx`

**Propósito**: Centro de inteligencia EDGE - visualizar autonomía, regímenes, pesos dinámicos

**Backend Associated**:
- **Primary**: `useAethelgard()` hook → `metrics` (EdgeMetrics), `regime`
- **Secondary**: `GET /api/regime_configs` (vía WeightedMetricsVisualizer)
- **Tertiary**: `getTuningLogs()` método para historial

**New Components Integrated**:
- **RegimeBadge**: En header, size="large"
- **WeightedMetricsVisualizer**: Nueva fila full-width (col-span-12)

**Grid Layout**:
```
┌─ Header (RegimeBadge + Self-Learning Badge)
├─ Grid 12 cols
│  ├─ Left: 8 cols (Confidence Radar + Agents + Tuner)
│  ├─ Right: 4 cols (Cerebro Insights)
│  └─ Full: 12 cols (WeightedMetricsVisualizer)
└─ Footer (NeuralHistoryPanel modal)
```

**Usage**:
```tsx
<EdgeHub metrics={metrics} regime={regime} />
```

---

### 5. **GlassPanel (Utility)** ✅
**Archivo**: `ui/src/components/common/GlassPanel.tsx`

**Propósito**: Wrapper estándar para todos los paneles (glassmorphism)

**Props**:
```tsx
interface GlassPanelProps {
    children: React.ReactNode;
    className?: string;
    premium?: boolean;  // Añade borde aethelgard-green
}
```

**Default Styling**:
```
bg-white/[0.01]
border border-white/5
rounded-xl
backdrop-blur-sm
transition-all duration-300
```

**Usage**:
```tsx
<GlassPanel premium className="p-6">
    Content here
</GlassPanel>
```

---

### 6. **CerebroConsole** ✅
**Archivo**: `ui/src/components/trader/CerebroConsole.tsx`

**Propósito**: Feed de "pensamientos" del sistema (logs, eventos, debugging)

**Backend Associated**:
- **Data Source**: WebSocket `type: 'BREIN_THOUGHT'`
- **Structure**: `{ message, module, level ('info'|'warning'|'error'|'debug'|'success'), metadata }`

**Visual Features**:
- ASCII-like monospace display
- Color-coded por level (verde=success, rojo=error, naranja=warning)
- Auto-scroll a últimos mensajes
- Máx 50 mensajes en buffer

---

### 7. **DiagnosticDrawer** ✅
**Archivo**: `ui/src/components/diagnostic/DiagnosticDrawer.tsx`

**Propósito**: Panel de diagnóstico (CPU, WebSocket, Satellites, Health)

**Backend Associated**:
- **Endpoints**:
  - `GET /api/scanner/status` → CPU load, assets, last_scan
  - `GET /api/system/status` → connections, timestamp
  - WebSocket heartbeats via `type: 'HEARTBEAT'`

**Visual Features**:
- Drawer slide-in desde derecha
- Indicadores circulares de salud
- LED-style badges (ONLINE/OFFLINE/MANUAL_DISABLED)

---

### 8. **PortfolioView** ✅
**Archivo**: `ui/src/components/portfolio/PortfolioView.tsx`

**Propósito**: Resumen de posiciones activas + riesgo

**Backend Associated**:
- **Data Source**: `GET /api/account/summary` (balance, risk)
- **Método Hook**: `useAethelgard()` → `riskSummary`

**Visual Features**:
- Cards por activo (FOREX, CRYPTO, METALS, INDEX)
- Indicador de riesgo % vs max permitido
- Posiciones activas listadas con P&L

---

## 📊 Componentes Pendientes (Roadmap)

### Pre-Milestone 6:
- [ ] **AdminConsole**: Comandos `/fix_logs`, `/clear_stale_signals`, etc.
- [ ] **SystemIntegrity Widget**: Circular gauge consolidando CPU + Latency + Connector Status
- [ ] **Repair Protocol Bridge**: Visual distinto para auto-healing en process
- [ ] **Diagnostic Interactive Matrix**: Inspeccionar errores con traceback detallado

### Milestone 6+:
- [ ] **FVG Detector Visualization**: Heat map de Fair Value Gaps
- [ ] **Volatility Arbitrage Chart**: Implied vs Realized volatility
- [ ] **Multi-Institutional Connector**: FIX API integration UI

---

## 🔗 Associación Componente → Backend → Funcionalidad

| Componente | Backend Endpoint/Hook | Funcionalidad Principal | Actualización |
|-------------|----------------------|------------------------|-----------------|
| RegimeBadge | WebSocket realtime | Mostrar régimen actual visual | Realtime |
| WeightedMetricsVisualizer | GET /api/regime_configs | Visualizar pesos dinámicos por régimen | On-mount + manual |
| AlphaSignals | WebSocket signals | Stream de señales LIVE/SHADOW/QUARANTINE | Realtime |
| EdgeHub | useAethelgard() (metrics, regime) | Centro de inteligencia autónoma | Realtime (WebSocket) |
| CerebroConsole | WebSocket BREIN_THOUGHT | Feed de pensamientos/eventos sistema | Realtime |
| DiagnosticDrawer | GET /api/scanner/status + WS heartbeat | Diagnóstico CPU, Web Socket, Health | Realtime |
| PortfolioView | GET /api/account/summary | Resumen posiciones + riesgo | On-mount + polling 30s |
| GlassPanel | N/A (utility) | Wrapper estándar para consistency | N/A |

---

## 🎯 Pautas de Diseño (Apply Always)

### a) Espaciado & Layout
- **Padding interior**: `p-4` (pequeño), `p-5` (mediano), `p-6` (grande)
- **Gap entre elementos**: `gap-3` (pequeño), `gap-4` (mediano), `gap-6` (grande)
- **Margin top/bottom**: Usar `mt-4`, `mb-2` sparingly (preferir gap en flex)
- **Responsive**: `col-span-12 lg:col-span-8` (mobile-first)

### b) Bordes & Fondos
- **Panel estándar**: `border border-white/5 bg-white/[0.01] rounded-xl`
- **Panel premium**: Agregar `border-aethelgard-green/10` + `bg-gradient-to-b from-aethelgard-green/[0.03] to-transparent`
- **Hover states**: `hover:bg-white/10 hover:border-white/10 transition-all`

### c) Tipografía
- **Headers**: `font-outfit font-bold text-white/95`
- **Labels**: `text-[10px] font-bold text-white/50 uppercase tracking-widest`
- **Data**: `font-mono text-[11px] text-white/70`
- **Error**: `text-red-400` (nunca rojo puro)
- **Success**: `text-aethelgard-green` (nunca verde puro)

### d) Animaciones
- **Entrada**: `initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}`
- **Hover**: `whileHover={{ scale: 1.005 }}`
- **Pulsante**: `animate={{ scale: [1, 1.05, 1] }} transition={{ duration: 2, repeat: Infinity }}`
- **Heartbeat**: `animate={{ scale: [1, 1.3, 1] }} transition={{ duration: 1.5, repeat: Infinity }}`

### e) Responsive Design
- **Mobile First**: Base en `col-span-12`, agregar `lg:col-span-8` para desktop
- **Breakpoints Tailwind**: sm (640px), md (768px), lg (1024px), xl (1280px)
- **Hidden Classes**: `hidden md:block` (hide en mobile), `hidden lg:flex` (show solo en desktop)

### f) Validaciones Visuales
- **Loading**: Spinner rotating + texto "Loading..." (nunca skeleton vacío)
- **Error**: `border-red-500/20 bg-red-500/5` + AlertCircle icon
- **Empty State**: Centered icon + texto descriptivo (nunca campo vacío)

### g) Accesibilidad Mínima
- **Contraste**: Mínimo AA (WCAG) - validar colores
- **Tooltips**: Usar `title` attribute para badges/íconos
- **Keyboard Navigation**: Tab order lógico (no implementado aún, pero considerar)

---

## 🔄 Flujo de Datos (WebSocket Integration)

```
┌─ Server (FastAPI)
│  ├─ /ws/GENERIC/dashboard_nextgen (WebSocket)
│  │  ├─ type: "SIGNAL" → AlphaSignals
│  │  ├─ type: "BREIN_THOUGHT" → CerebroConsole
│  │  ├─ type: "HEARTBEAT" → DiagnosticDrawer (CPU, satellites)
│  │  └─ type: "REGIME_CHANGE" → RegimeBadge, EdgeHub
│  └─ GET /api/regime_configs → WeightedMetricsVisualizer
│
└─ UI (React)
   ├─ useAethelgard() hook (conexión WebSocket)
   ├─ App.tsx (dispatcher central)
   └─ Componentes (listeners específicos)
```

**IMPORTANTE**: No romper la conexión WebSocket. Todos los fetch() adicionales deben ser desacoplados.

---

## ✅ Checklist para Nuevos Componentes

- [ ] Usar `GlassPanel` como wrapper
- [ ] Aplicar pautas de tipografía (Outfit headers, Inter body)
- [ ] Incluir animaciones (entrada + hover + pulsante si aplica)
- [ ] Responsive: mobile-first con breakpoints `lg:`
- [ ] Colores restrictos a paleta (#050505, #00ffc8, #ff3333, #ffc107)
- [ ] Props bien tipadas en interfaces TypeScript
- [ ] Backend asociado documentado (endpoint/hook)
- [ ] Testing en múltiples tamaños de pantalla
- [ ] Sin hardcoding de datos (usar props/hooks)
- [ ] Manejo de error states (loading, error, empty)

---

## 📝 Notas Finales

- **SSOT (Single Source of Truth)**: Todos los colores, fonts, spacing viven en las secciones superiores como referencia.
- **Evolución Constante**: Este documento se actualiza con cada nuevo componente (Milestone).
- **Design Tokens**: Considerar migrar a CSS variables en próxima iteración para mayor mantenibilidad.
- **Cross-Browser**: Validar en Chrome, Firefox, Safari (Tailwind cover mayoría).

