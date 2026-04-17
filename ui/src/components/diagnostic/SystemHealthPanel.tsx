import { motion } from 'framer-motion';
import {
  Activity, AlertTriangle, CheckCircle2, Clock, Cpu, Database,
  GitBranch, Radio, RefreshCw, Search, ShieldCheck, Signal, TrendingUp, Zap,
} from 'lucide-react';
import { GlassPanel } from '../common/GlassPanel';
import { cn } from '../../utils/cn';
import { useOemHealth, CheckStatus, OverallStatus } from '../../hooks/useOemHealth';

// ── Metadata estática de cada check ─────────────────────────────────────────

interface CheckMeta {
  label: string;
  connects_to: string;
  icon: React.ReactNode;
  color: string;
  tooltip?: string;
}

const CHECK_META: Record<string, CheckMeta> = {
  orchestrator_heartbeat: {
    label: 'Loop Heartbeat',
    connects_to: 'MainOrchestrator',
    icon: <Activity size={13} />,
    color: 'text-aethelgard-blue',
    tooltip: 'Verifica que el ciclo principal del orquestador esté activo. Detecta el estado del modo DEMO (ON/OFF) y la salud del loop de ejecución.',
  },
  signal_flow: {
    label: 'Signal Flow',
    connects_to: 'SignalFactory',
    icon: <Radio size={13} />,
    color: 'text-purple-400',
    tooltip: 'Monitorea el flujo de señales generadas y rechazadas. Incluye conteo de señales exploratorias (EXPLORATION_ON) activas en el ciclo EDGE DEMO.',
  },
  shadow_sync: {
    label: 'Shadow Sync',
    connects_to: 'ShadowManager',
    icon: <GitBranch size={13} />,
    color: 'text-aethelgard-gold',
    tooltip: 'Estado de sincronización de instancias SHADOW. Muestra el mejor profit factor, la cantidad de instancias activas y el impacto de señales exploratorias.',
  },
  backtest_quality: {
    label: 'Backtest Quality',
    connects_to: 'BacktestOrchestrator',
    icon: <TrendingUp size={13} />,
    color: 'text-aethelgard-blue',
    tooltip: 'Calidad del motor de backtesting. Evalúa la consistencia de resultados históricos y la validez estadística de las estrategias activas.',
  },
  connector_exec: {
    label: 'Connector Exec',
    connects_to: 'ConnectivityOrchestrator',
    icon: <Signal size={13} />,
    color: 'text-aethelgard-green',
    tooltip: 'Estado del conector de ejecución hacia MT5. Detecta latencia, errores de conexión y disponibilidad del broker.',
  },
  adx_sanity: {
    label: 'ADX Sanity',
    connects_to: 'ScannerEngine',
    icon: <Zap size={13} />,
    color: 'text-orange-400',
    tooltip: 'Valida que el indicador ADX produzca lecturas coherentes. Un ADX=0 constante indica un problema en el cálculo o en la carga de datos OHLC.',
  },
  lifecycle_coherence: {
    label: 'Lifecycle Coherence',
    connects_to: 'StrategyRanker',
    icon: <ShieldCheck size={13} />,
    color: 'text-purple-400',
    tooltip: 'Coherencia del ciclo de vida de estrategias: incubación, shadow, promoción y cuarentena. Detecta transiciones inválidas o estados inconsistentes.',
  },
  rejection_rate: {
    label: 'Rejection Rate',
    connects_to: 'OrderExecutor',
    icon: <AlertTriangle size={13} />,
    color: 'text-aethelgard-gold',
    tooltip: 'Tasa de rechazo de señales. Desglosa motivos: affinity (correlación), whitelist (activos permitidos), budget (riesgo), freeze (exploración congelada), rollback (reversión EDGE DEMO).',
  },
  score_stale: {
    label: 'Score Freshness',
    connects_to: 'StrategyRanker',
    icon: <Database size={13} />,
    color: 'text-aethelgard-blue',
    tooltip: 'Frescura de los scores de estrategia. Detecta si el ranking no se ha actualizado en el tiempo esperado, lo que podría indicar un fallo en el ranker.',
  },
};

// ── Helpers de estilos ───────────────────────────────────────────────────────

const STATUS_BADGE: Record<CheckStatus, string> = {
  OK:   'bg-aethelgard-green/10 text-aethelgard-green border border-aethelgard-green/20',
  WARN: 'bg-orange-400/10 text-orange-400 border border-orange-400/20',
  FAIL: 'bg-red-500/10 text-red-500 border border-red-500/30 shadow-[0_0_8px_rgba(239,68,68,0.15)]',
};

const STATUS_CARD: Record<CheckStatus, string> = {
  OK:   'bg-white/[0.02] border-white/5 hover:border-white/10',
  WARN: 'bg-orange-400/5 border-orange-400/15',
  FAIL: 'bg-red-500/8 border-red-500/25',
};

const OVERALL_BORDER: Record<OverallStatus, string> = {
  OK:          'border-aethelgard-green/20',
  DEGRADED:    'border-orange-400/20',
  CRITICAL:    'border-red-500/30',
  UNAVAILABLE: 'border-white/10',
};

const OVERALL_PILL: Record<OverallStatus, string> = {
  OK:          'bg-aethelgard-green/10 text-aethelgard-green border border-aethelgard-green/20',
  DEGRADED:    'bg-orange-400/10 text-orange-400 border border-orange-400/20',
  CRITICAL:    'bg-red-500/10 text-red-500 border border-red-500/30 animate-pulse',
  UNAVAILABLE: 'bg-white/5 text-white/30 border border-white/10',
};

// ── Orden de renderizado ─────────────────────────────────────────────────────

const CHECK_ORDER = [
  'orchestrator_heartbeat',
  'signal_flow',
  'shadow_sync',
  'backtest_quality',
  'connector_exec',
  'adx_sanity',
  'lifecycle_coherence',
  'rejection_rate',
  'score_stale',
];

// ── Sub-componente: metadata enriquecida por check ───────────────────────────

function CheckMetadata({ checkKey, metadata }: { checkKey: string; metadata?: Record<string, any> }) {
  if (!metadata) return null;

  if (checkKey === 'signal_flow') {
    return (
      <div className="flex flex-wrap gap-2 mt-1">
        {metadata.signals_generated !== undefined && (
          <span className="text-[8px] font-mono text-aethelgard-green/70">↑{metadata.signals_generated} gen</span>
        )}
        {metadata.signals_rejected !== undefined && (
          <span className="text-[8px] font-mono text-red-400/70">↓{metadata.signals_rejected} rej</span>
        )}
        {!!metadata.exploration_on_count && (
          <span className="text-[8px] font-mono text-aethelgard-gold/80 border border-aethelgard-gold/20 px-1 rounded">
            EXPLORE×{metadata.exploration_on_count}
          </span>
        )}
        {metadata.exploratory_active === true && (
          <span className="text-[7px] font-bold uppercase text-aethelgard-gold/70 bg-aethelgard-gold/5 px-1 rounded">active</span>
        )}
      </div>
    );
  }

  if (checkKey === 'rejection_rate') {
    const reasons = ['affinity', 'whitelist', 'budget', 'freeze', 'rollback'];
    const hasAny = reasons.some(r => !!metadata[r]);
    if (!hasAny) return null;
    return (
      <div className="flex flex-wrap gap-1.5 mt-1">
        {reasons.map(r => metadata[r] ? (
          <span key={r} className="text-[7px] font-mono text-orange-400/70 bg-orange-400/5 px-1 py-0.5 rounded border border-orange-400/10">
            {r}:{metadata[r]}
          </span>
        ) : null)}
      </div>
    );
  }

  if (checkKey === 'orchestrator_heartbeat' && metadata.demo_mode !== undefined) {
    return (
      <span className={cn(
        'text-[8px] font-bold uppercase px-1.5 py-0.5 rounded mt-1 inline-block',
        metadata.demo_mode
          ? 'bg-aethelgard-gold/10 text-aethelgard-gold border border-aethelgard-gold/20'
          : 'bg-white/5 text-white/30 border border-white/10',
      )}>
        DEMO: {metadata.demo_mode ? 'ON' : 'OFF'}
      </span>
    );
  }

  if (checkKey === 'shadow_sync') {
    return (
      <div className="flex flex-wrap gap-2 mt-1">
        {metadata.instances_count !== undefined && (
          <span className="text-[8px] font-mono text-aethelgard-gold/70">{metadata.instances_count} inst</span>
        )}
        {metadata.best_pf !== undefined && (
          <span className="text-[8px] font-mono text-aethelgard-green/70">PF:{Number(metadata.best_pf).toFixed(2)}</span>
        )}
        {!!metadata.exploratory_signals && (
          <span className="text-[8px] font-mono text-purple-400/80 border border-purple-400/20 px-1 rounded">
            +{metadata.exploratory_signals} expl
          </span>
        )}
      </div>
    );
  }

  return null;
}

// ── Componente principal ─────────────────────────────────────────────────────

/**
 * SystemHealthPanel
 *
 * Muestra el estado de los checks del OperationalEdgeMonitor en tiempo real.
 * Incluye modo DEMO, estado de exploración EDGE y motivos de rechazo desglosados.
 * Se actualiza por polling HTTP cada 15 s via useOemHealth.
 */
export const SystemHealthPanel = () => {
  const { health, loading, error } = useOemHealth();

  const overallStatus: OverallStatus = health?.status ?? 'UNAVAILABLE';
  const lastChecked = health?.last_checked_at
    ? new Date(health.last_checked_at).toLocaleTimeString()
    : null;

  return (
    <GlassPanel className={cn('p-6 flex flex-col gap-5', OVERALL_BORDER[overallStatus])}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Cpu size={18} className="text-aethelgard-blue" />
          <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white/60">
            EDGE Self-Audit
          </h3>
          {health?.demo_mode && (
            <span className="text-[9px] font-black uppercase px-2 py-0.5 rounded-md bg-aethelgard-gold/10 text-aethelgard-gold border border-aethelgard-gold/20 tracking-widest">
              DEMO
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {lastChecked && (
            <div className="flex items-center gap-1.5 text-white/30">
              <Clock size={10} />
              <span className="text-[9px] font-mono">{lastChecked}</span>
            </div>
          )}
          {loading && !health && (
            <RefreshCw size={11} className="text-white/30 animate-spin" />
          )}
          <span className={cn('text-[9px] font-black uppercase px-2 py-0.5 rounded-md tracking-widest', OVERALL_PILL[overallStatus])}>
            {overallStatus}
          </span>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="text-[10px] text-orange-400/70 font-mono px-3 py-2 rounded-lg bg-orange-400/5 border border-orange-400/10">
          {error}
        </div>
      )}

      {/* Unavailable message */}
      {health?.status === 'UNAVAILABLE' && health.message && (
        <p className="text-[10px] text-white/30 italic">{health.message}</p>
      )}

      {/* Checks grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {CHECK_ORDER.map((checkKey, i) => {
          const result = health?.checks[checkKey];
          const meta = CHECK_META[checkKey];
          if (!meta) return null;

          const status: CheckStatus = result?.status ?? 'OK';
          const detail = result?.detail ?? '—';

          return (
            <motion.div
              key={checkKey}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              title={meta.tooltip}
              className={cn(
                'flex flex-col gap-2 p-3 rounded-xl border transition-all duration-300 cursor-help',
                result ? STATUS_CARD[status] : 'bg-white/[0.02] border-white/5',
              )}
            >
              {/* Check header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={cn('opacity-80', result ? (status === 'OK' ? 'text-aethelgard-green' : status === 'FAIL' ? 'text-red-400' : 'text-orange-400') : meta.color)}>
                    {meta.icon}
                  </span>
                  <span className="text-[10px] font-bold text-white/80 uppercase tracking-wider">
                    {meta.label}
                  </span>
                </div>

                {result ? (
                  <span className={cn('text-[8px] font-black uppercase px-1.5 py-0.5 rounded-md', STATUS_BADGE[status])}>
                    {status}
                  </span>
                ) : (
                  <span className="text-[8px] text-white/20 uppercase">—</span>
                )}
              </div>

              {/* Connects to */}
              <div className="flex items-center gap-1.5">
                <div className="h-px flex-1 bg-white/5" />
                <span className="text-[8px] font-mono text-white/25 uppercase tracking-widest">
                  {meta.connects_to}
                </span>
                <div className="h-px flex-1 bg-white/5" />
              </div>

              {/* Detail */}
              <p className="text-[9px] font-mono text-white/40 leading-relaxed line-clamp-2">
                {detail}
              </p>

              {/* Check-specific enriched metadata */}
              <CheckMetadata checkKey={checkKey} metadata={result?.metadata} />

              {/* Status bar */}
              <div className="w-full h-0.5 bg-white/5 rounded-full overflow-hidden mt-auto">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: result ? '100%' : '0%' }}
                  transition={{ duration: 0.4, delay: i * 0.04 }}
                  className={cn(
                    'h-full rounded-full',
                    !result ? 'bg-white/10'
                      : status === 'OK' ? 'bg-aethelgard-green'
                      : status === 'WARN' ? 'bg-orange-400'
                      : 'bg-red-500',
                  )}
                />
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Summary footer */}
      {health && health.status !== 'UNAVAILABLE' && (
        <div className="flex items-center gap-4 pt-2 border-t border-white/5">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 size={10} className="text-aethelgard-green" />
            <span className="text-[9px] text-white/40">
              {Object.keys(health.checks).length - health.failing.length - health.warnings.length} OK
            </span>
          </div>
          {health.warnings.length > 0 && (
            <div className="flex items-center gap-1.5">
              <AlertTriangle size={10} className="text-orange-400" />
              <span className="text-[9px] text-white/40">{health.warnings.length} WARN</span>
            </div>
          )}
          {health.failing.length > 0 && (
            <div className="flex items-center gap-1.5">
              <AlertTriangle size={10} className="text-red-400" />
              <span className="text-[9px] text-red-400 font-bold">{health.failing.length} FAIL</span>
            </div>
          )}
          <div className="ml-auto text-[8px] text-white/20 font-mono">
            OEM · 11 checks · 5 min interval
          </div>
        </div>
      )}

      {/* EDGE Exploration summary (visible cuando exploration está activa) */}
      {health?.exploration?.active && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="flex flex-col gap-2 pt-3 border-t border-aethelgard-gold/10"
        >
          <div className="flex items-center gap-2">
            <Search size={10} className="text-aethelgard-gold" />
            <span className="text-[9px] font-black uppercase tracking-widest text-aethelgard-gold">
              EDGE Exploration Active
            </span>
            <span className="text-[8px] font-mono text-white/40">
              {health.exploration.assets_in_exploration.length} activos
            </span>
          </div>
          <div className="flex flex-wrap gap-3">
            <span className="text-[8px] font-mono text-white/40">
              Budget: {health.exploration.budget_remaining?.toFixed(0)}%
            </span>
            {health.exploration.frozen_assets.length > 0 && (
              <span className="text-[8px] font-mono text-blue-400/70">
                Frozen: {health.exploration.frozen_assets.length}
              </span>
            )}
            {health.exploration.rollback_count > 0 && (
              <span className="text-[8px] font-mono text-orange-400/70">
                Rollbacks: {health.exploration.rollback_count}
              </span>
            )}
            {health.exploration.exploratory_pf > 0 && (
              <span className="text-[8px] font-mono text-aethelgard-green/70">
                Expl.PF: {health.exploration.exploratory_pf?.toFixed(2)}
              </span>
            )}
            {health.exploration.exploration_on_count > 0 && (
              <span className="text-[8px] font-mono text-purple-400/70">
                EXPLORATION_ON: {health.exploration.exploration_on_count}
              </span>
            )}
          </div>
          {health.exploration.assets_in_exploration.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {health.exploration.assets_in_exploration.slice(0, 8).map(asset => (
                <span key={asset} className="text-[7px] font-mono text-aethelgard-gold/60 bg-aethelgard-gold/5 border border-aethelgard-gold/15 px-1.5 py-0.5 rounded">
                  {asset}
                </span>
              ))}
              {health.exploration.assets_in_exploration.length > 8 && (
                <span className="text-[7px] font-mono text-white/30">+{health.exploration.assets_in_exploration.length - 8}</span>
              )}
            </div>
          )}
        </motion.div>
      )}
    </GlassPanel>
  );
};
