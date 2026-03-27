import { motion } from 'framer-motion';
import {
  Activity, AlertTriangle, CheckCircle2, Clock, Cpu, Database,
  GitBranch, Radio, RefreshCw, ShieldCheck, Signal, TrendingUp, Zap,
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
}

const CHECK_META: Record<string, CheckMeta> = {
  orchestrator_heartbeat: {
    label: 'Loop Heartbeat',
    connects_to: 'MainOrchestrator',
    icon: <Activity size={13} />,
    color: 'text-aethelgard-blue',
  },
  signal_flow: {
    label: 'Signal Flow',
    connects_to: 'SignalFactory',
    icon: <Radio size={13} />,
    color: 'text-purple-400',
  },
  shadow_sync: {
    label: 'Shadow Sync',
    connects_to: 'ShadowManager',
    icon: <GitBranch size={13} />,
    color: 'text-aethelgard-gold',
  },
  backtest_quality: {
    label: 'Backtest Quality',
    connects_to: 'BacktestOrchestrator',
    icon: <TrendingUp size={13} />,
    color: 'text-aethelgard-blue',
  },
  connector_exec: {
    label: 'Connector Exec',
    connects_to: 'ConnectivityOrchestrator',
    icon: <Signal size={13} />,
    color: 'text-aethelgard-green',
  },
  adx_sanity: {
    label: 'ADX Sanity',
    connects_to: 'ScannerEngine',
    icon: <Zap size={13} />,
    color: 'text-orange-400',
  },
  lifecycle_coherence: {
    label: 'Lifecycle Coherence',
    connects_to: 'StrategyRanker',
    icon: <ShieldCheck size={13} />,
    color: 'text-purple-400',
  },
  rejection_rate: {
    label: 'Rejection Rate',
    connects_to: 'OrderExecutor',
    icon: <AlertTriangle size={13} />,
    color: 'text-aethelgard-gold',
  },
  score_stale: {
    label: 'Score Freshness',
    connects_to: 'StrategyRanker',
    icon: <Database size={13} />,
    color: 'text-aethelgard-blue',
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

// ── Componente principal ─────────────────────────────────────────────────────

/**
 * SystemHealthPanel
 *
 * Muestra el estado de los 9 checks del OperationalEdgeMonitor en tiempo real.
 * Cada card indica: componente auditado, status (OK/WARN/FAIL) y detalle del check.
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
              className={cn(
                'flex flex-col gap-2 p-3 rounded-xl border transition-all duration-300',
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
            OEM · 9 checks · 5 min interval
          </div>
        </div>
      )}
    </GlassPanel>
  );
};
