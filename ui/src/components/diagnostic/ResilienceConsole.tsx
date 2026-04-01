/**
 * ResilienceConsole.tsx — Immune System Control Panel (HU 10.17b)
 *
 * Displays the live SystemPosture, healing budget, and exclusion lists.
 * Operator intervention buttons (RETRY_HEALING, OVERRIDE_POSTURE, RELEASE_SCOPE)
 * POST to /api/v3/resilience/command and show in-flight spinners.
 *
 * Data source:
 *   - Narrative badge: resilience_status injected into /ws/v3/synapse heartbeat.
 *   - Full detail: polling GET /api/v3/resilience/status every 10 s.
 *
 * Design: Glassmorphism, 0.5 px borders, stagger-100ms entry animation.
 * Trace_ID: EDGE-IGNITION-PHASE-6-RESILIENCE-UI
 */

import { useCallback, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldOff,
  Unlock,
  Zap,
} from 'lucide-react';
import { GlassPanel } from '../common/GlassPanel';
import { cn } from '../../utils/cn';
import { useSynapseTelemetry, ResilienceSnapshot } from '../../hooks/useSynapseTelemetry';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ResilienceStatus {
  posture: string;
  narrative: string;
  is_healing: boolean;
  heal_budget_remaining: number;
  exclusions: {
    muted: string[];
    quarantined: string[];
    in_cooldown: string[];
  };
}

type CommandAction = 'RETRY_HEALING' | 'OVERRIDE_POSTURE' | 'RELEASE_SCOPE';

// ── Posture palette ───────────────────────────────────────────────────────────

const POSTURE_CONFIG: Record<
  string,
  { label: string; color: string; border: string; bg: string; icon: React.ReactNode }
> = {
  NORMAL: {
    label: 'NORMAL',
    color: 'text-aethelgard-green',
    border: 'border-aethelgard-green/20',
    bg: 'bg-aethelgard-green/5',
    icon: <CheckCircle2 size={14} />,
  },
  CAUTION: {
    label: 'CAUTION',
    color: 'text-aethelgard-gold',
    border: 'border-aethelgard-gold/20',
    bg: 'bg-aethelgard-gold/5',
    icon: <AlertTriangle size={14} />,
  },
  DEGRADED: {
    label: 'DEGRADED',
    color: 'text-orange-400',
    border: 'border-orange-400/20',
    bg: 'bg-orange-400/5',
    icon: <ShieldAlert size={14} />,
  },
  STRESSED: {
    label: 'STRESSED',
    color: 'text-red-500',
    border: 'border-red-500/30',
    bg: 'bg-red-500/10',
    icon: <ShieldOff size={14} />,
  },
  UNAVAILABLE: {
    label: 'UNAVAILABLE',
    color: 'text-white/30',
    border: 'border-white/5',
    bg: 'bg-white/[0.02]',
    icon: <Shield size={14} />,
  },
};

// ── API helpers ───────────────────────────────────────────────────────────────

async function fetchResilienceStatus(): Promise<ResilienceStatus | null> {
  try {
    const res = await fetch('/api/v3/resilience/status', { credentials: 'include' });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function sendCommand(
  action: CommandAction,
  extra: { scope?: string; posture?: string } = {}
): Promise<{ success: boolean; detail?: string }> {
  try {
    const res = await fetch('/api/v3/resilience/command', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, ...extra }),
    });
    const body = await res.json();
    return { success: res.ok && body.success, detail: body.detail ?? body.error };
  } catch (err: any) {
    return { success: false, detail: err?.message };
  }
}

// ── InterventionButton ────────────────────────────────────────────────────────

interface InterventionButtonProps {
  label: string;
  icon: React.ReactNode;
  actionKey: string;
  onClick: () => Promise<void>;
  busy: boolean;
  disabled?: boolean;
  variant?: 'default' | 'danger';
}

const InterventionButton = ({
  label,
  icon,
  actionKey,
  onClick,
  busy,
  disabled = false,
  variant = 'default',
}: InterventionButtonProps) => (
  <button
    key={actionKey}
    onClick={onClick}
    disabled={busy || disabled}
    className={cn(
      'flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest',
      'border transition-all duration-200',
      busy || disabled
        ? 'opacity-40 cursor-not-allowed border-white/5 bg-white/[0.02] text-white/30'
        : variant === 'danger'
        ? 'border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20 hover:border-red-500/50'
        : 'border-aethelgard-blue/30 bg-aethelgard-blue/10 text-aethelgard-blue hover:bg-aethelgard-blue/20 hover:border-aethelgard-blue/50'
    )}
  >
    {busy ? <Loader2 size={11} className="animate-spin" /> : icon}
    {label}
  </button>
);

// ── ExclusionTable ────────────────────────────────────────────────────────────

interface ExclusionTableProps {
  title: string;
  items: string[];
  emptyLabel: string;
  color: string;
  onRelease?: (scope: string) => void;
  busyScope?: string | null;
}

const ExclusionTable = ({
  title,
  items,
  emptyLabel,
  color,
  onRelease,
  busyScope,
}: ExclusionTableProps) => (
  <div className="flex flex-col gap-2">
    <span className={cn('text-[8px] font-black uppercase tracking-widest', color)}>
      {title}
    </span>
    {items.length === 0 ? (
      <span className="text-[9px] text-white/20 italic pl-1">{emptyLabel}</span>
    ) : (
      <div className="flex flex-col gap-1">
        {items.map((scope) => (
          <div
            key={scope}
            className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.07] text-[10px] font-mono text-white/70"
          >
            <span>{scope}</span>
            {onRelease && (
              <button
                onClick={() => onRelease(scope)}
                disabled={busyScope === scope}
                className="ml-3 text-[8px] font-black text-aethelgard-blue/60 hover:text-aethelgard-blue transition-colors disabled:opacity-30"
              >
                {busyScope === scope ? (
                  <Loader2 size={9} className="animate-spin" />
                ) : (
                  <Unlock size={9} />
                )}
              </button>
            )}
          </div>
        ))}
      </div>
    )}
  </div>
);

// ── Main component ────────────────────────────────────────────────────────────

export const ResilienceConsole = () => {
  const { telemetry } = useSynapseTelemetry();
  const wsSnapshot: ResilienceSnapshot | undefined = telemetry?.resilience_status;

  const [detail, setDetail] = useState<ResilienceStatus | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [busyScope, setBusyScope] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(null);

  // Poll full detail every 10 s
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const data = await fetchResilienceStatus();
      if (!cancelled) setDetail(data);
    };
    load();
    const id = setInterval(load, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const showFeedback = (ok: boolean, msg: string) => {
    setFeedback({ ok, msg });
    setTimeout(() => setFeedback(null), 4000);
  };

  const handleRetryHealing = useCallback(async () => {
    setBusyAction('RETRY_HEALING');
    const r = await sendCommand('RETRY_HEALING');
    setBusyAction(null);
    showFeedback(r.success, r.detail ?? '');
    if (r.success) {
      const data = await fetchResilienceStatus();
      setDetail(data);
    }
  }, []);

  const handleOverrideNormal = useCallback(async () => {
    setBusyAction('OVERRIDE_POSTURE');
    const r = await sendCommand('OVERRIDE_POSTURE', { posture: 'NORMAL' });
    setBusyAction(null);
    showFeedback(r.success, r.detail ?? '');
    if (r.success) {
      const data = await fetchResilienceStatus();
      setDetail(data);
    }
  }, []);

  const handleReleaseScope = useCallback(async (scope: string) => {
    setBusyScope(scope);
    const r = await sendCommand('RELEASE_SCOPE', { scope });
    setBusyScope(null);
    showFeedback(r.success, r.detail ?? '');
    if (r.success) {
      const data = await fetchResilienceStatus();
      setDetail(data);
    }
  }, []);

  // Prefer WS posture for fast badge; fall back to polled detail
  const posture = wsSnapshot?.posture ?? detail?.posture ?? 'UNAVAILABLE';
  const palette = POSTURE_CONFIG[posture] ?? POSTURE_CONFIG['UNAVAILABLE'];
  const narrative = wsSnapshot?.narrative ?? detail?.narrative ?? '';
  const isHealing = wsSnapshot?.is_healing ?? detail?.is_healing ?? false;

  const containerVariants = {
    hidden: {},
    show: { transition: { staggerChildren: 0.1 } },
  };
  const itemVariants = {
    hidden: { opacity: 0, y: 8 },
    show: { opacity: 1, y: 0, transition: { duration: 0.25 } },
  };

  return (
    <GlassPanel className={cn('p-6 flex flex-col gap-5 border-[0.5px]', palette.border)}>
      {/* Header */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="flex flex-col gap-4"
      >
        {/* Title row */}
        <motion.div variants={itemVariants} className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={cn('p-2 rounded-xl bg-white/5', palette.color)}>
              <Activity size={16} />
            </div>
            <div>
              <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white/60">
                Resilience Console
              </h3>
              <p className="text-[9px] text-white/30 mt-0.5">Immune System Control Panel</p>
            </div>
          </div>

          {/* Posture badge */}
          <div
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-xl border-[0.5px]',
              palette.bg,
              palette.border
            )}
          >
            <span className={palette.color}>{palette.icon}</span>
            <span className={cn('text-[10px] font-black uppercase tracking-widest', palette.color)}>
              {palette.label}
            </span>
            {isHealing && (
              <Loader2 size={10} className="animate-spin text-aethelgard-blue ml-1" />
            )}
          </div>
        </motion.div>

        {/* Narrative */}
        <AnimatePresence>
          {narrative && (
            <motion.div
              key="narrative"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className={cn(
                'px-4 py-3 rounded-xl border-[0.5px] text-[10px] leading-relaxed text-white/70',
                palette.bg,
                palette.border
              )}
            >
              {narrative}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Healing budget bar */}
        {detail && (
          <motion.div variants={itemVariants} className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <span className="text-[9px] text-white/30 uppercase tracking-widest">
                Healing Budget
              </span>
              <span className="text-[9px] font-mono text-white/60">
                {detail.heal_budget_remaining} retries left
              </span>
            </div>
            <div className="h-[2px] bg-white/5 rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{
                  width: `${Math.min(100, (detail.heal_budget_remaining / 3) * 100)}%`,
                }}
                transition={{ duration: 0.5 }}
                className={cn(
                  'h-full rounded-full',
                  detail.heal_budget_remaining > 1
                    ? 'bg-aethelgard-green'
                    : detail.heal_budget_remaining === 1
                    ? 'bg-aethelgard-gold'
                    : 'bg-red-500'
                )}
              />
            </div>
          </motion.div>
        )}
      </motion.div>

      {/* Intervention Buttons */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="flex flex-wrap gap-2"
      >
        <motion.div variants={itemVariants}>
          <InterventionButton
            actionKey="retry"
            label="Retry Healing"
            icon={<RefreshCw size={11} />}
            onClick={handleRetryHealing}
            busy={busyAction === 'RETRY_HEALING'}
          />
        </motion.div>
        <motion.div variants={itemVariants}>
          <InterventionButton
            actionKey="override"
            label="Override → Normal"
            icon={<Zap size={11} />}
            onClick={handleOverrideNormal}
            busy={busyAction === 'OVERRIDE_POSTURE'}
            variant="danger"
          />
        </motion.div>
      </motion.div>

      {/* Feedback toast */}
      <AnimatePresence>
        {feedback && (
          <motion.div
            key="feedback"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-xl border-[0.5px] text-[10px] font-bold',
              feedback.ok
                ? 'bg-aethelgard-green/10 border-aethelgard-green/20 text-aethelgard-green'
                : 'bg-red-500/10 border-red-500/20 text-red-400'
            )}
          >
            {feedback.ok ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}
            {feedback.msg}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Exclusion Tables */}
      {detail && (
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 border-t border-white/[0.05]"
        >
          <motion.div variants={itemVariants}>
            <ExclusionTable
              title="Muted Assets"
              items={detail.exclusions.muted}
              emptyLabel="No assets muted"
              color="text-aethelgard-gold"
              onRelease={handleReleaseScope}
              busyScope={busyScope}
            />
          </motion.div>
          <motion.div variants={itemVariants}>
            <ExclusionTable
              title="Quarantined Strategies"
              items={detail.exclusions.quarantined}
              emptyLabel="No strategies quarantined"
              color="text-orange-400"
              onRelease={handleReleaseScope}
              busyScope={busyScope}
            />
          </motion.div>
          <motion.div variants={itemVariants}>
            <ExclusionTable
              title="In Cooldown"
              items={detail.exclusions.in_cooldown}
              emptyLabel="No cooldowns active"
              color="text-white/40"
            />
          </motion.div>
        </motion.div>
      )}
    </GlassPanel>
  );
};
