import { motion, AnimatePresence } from 'framer-motion';
import {
    BrainCircuit,
    Zap,
    Target,
    RefreshCcw,
    BarChart3,
    Search,
    Snowflake,
    RotateCcw,
    TrendingUp,
    ChevronDown,
    ChevronUp,
    AlertTriangle,
    AlertCircle,
    CheckCircle2,
    Info,
} from 'lucide-react';
import { GlassPanel } from '../common/GlassPanel';
import { cn } from '../../utils/cn';
import {
    MarketRegime,
    EdgeMetrics,
    TuningLog,
    ExplorationState,
    CerebroThought,
} from '../../types/aethelgard';
import { useAethelgard } from '../../hooks/useAethelgard';
import { useOemHealth } from '../../hooks/useOemHealth';
import { useEffect, useState } from 'react';
import { NeuralHistoryPanel } from './NeuralHistoryPanel';
import { RegimeBadge } from './RegimeBadge';
import { WeightedMetricsVisualizer } from './WeightedMetricsVisualizer';

// ── Mapeo módulo → nombre legible ─────────────────────────────────────────────

const AGENT_MODULES: { key: string; name: string }[] = [
    { key: 'scanner',          name: 'Scanner Engine'     },
    { key: 'risk_manager',     name: 'Risk Sentry'        },
    { key: 'executor',         name: 'Order Orchestrator' },
    { key: 'position_manager', name: 'Position Manager'   },
    { key: 'monitor',          name: 'Closing Monitor'    },
];

// ── Props ─────────────────────────────────────────────────────────────────────

interface EdgeHubProps {
    metrics: EdgeMetrics;
    regime: MarketRegime;
    /** Puede pasarse desde el padre; si no, se lee del OEM health (polling 15 s). */
    explorationState?: ExplorationState;
}

// ── Componente principal ──────────────────────────────────────────────────────

export function EdgeHub({ metrics, regime, explorationState: explorationProp }: EdgeHubProps) {
    const { getTuningLogs, modulesStatus, status, thoughts } = useAethelgard();
    const { health } = useOemHealth();

    const [isLogsOpen, setIsLogsOpen]             = useState(false);
    const [tuningLogs, setTuningLogs]             = useState<TuningLog[]>([]);
    const [logsLoading, setLogsLoading]           = useState(true);
    const [isExplorationExpanded, setIsExpanded]  = useState(true);

    // Carga los tuning logs al montar (no sólo al abrir el panel)
    useEffect(() => {
        let cancelled = false;
        getTuningLogs(10).then(logs => {
            if (!cancelled) {
                setTuningLogs(logs ?? []);
                setLogsLoading(false);
            }
        }).catch(() => {
            if (!cancelled) setLogsLoading(false);
        });
        return () => { cancelled = true; };
    }, [getTuningLogs]);

    const handleOpenLogs = async () => {
        const logs = await getTuningLogs(50);
        setTuningLogs(logs ?? []);
        setIsLogsOpen(true);
    };

    // Fuente de verdad: prop del padre > OEM health > undefined
    const explorationState: ExplorationState | undefined =
        explorationProp ?? health?.exploration ?? undefined;
    const explorationActive = explorationState?.active ?? false;

    // Self-Learning: activo si el WebSocket está conectado
    const selfLearningOn = status?.connected ?? false;

    // Módulos activos desde la API
    const modules: Record<string, boolean> = modulesStatus?.modules ?? {};

    // Thoughts del Cerebro: excluir debug, tomar los últimos 4
    const insightThoughts: CerebroThought[] = (thoughts ?? [])
        .filter(t => t.level !== 'debug')
        .slice(-4)
        .reverse();

    return (
        <div className="flex flex-col gap-8 animate-in fade-in duration-500">
            {/* ── Header ─────────────────────────────────────────────────── */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h2 className="text-2xl font-outfit font-bold text-white/95 flex items-center gap-3">
                        <BrainCircuit className="text-aethelgard-green" size={28} />
                        EDGE Intelligence Hub
                    </h2>
                    <p className="text-white/60 text-sm mt-1">
                        Autonomous monitoring and self-calibration engine active (Darwinismo Algorítmico).
                    </p>
                </div>

                <div className="flex items-center gap-3 flex-col sm:flex-row">
                    <RegimeBadge regime={regime} size="large" showLabel animated />

                    <StatusBadge
                        active={selfLearningOn}
                        labelOn="Self-Learning: ON"
                        labelOff="Self-Learning: OFF"
                        colorOn="green"
                        tooltip={selfLearningOn
                            ? 'Motor EDGE activo: ajuste autónomo de parámetros en curso.'
                            : 'Sistema desconectado — el aprendizaje autónomo está en pausa.'}
                    />

                    <StatusBadge
                        active={explorationActive}
                        labelOn="Exploration: ON"
                        labelOff="Exploration: OFF"
                        colorOn="gold"
                        tooltip={explorationActive
                            ? `Ciclo EDGE DEMO activo: ${explorationState?.assets_in_exploration.length ?? 0} activos en exploración evolutiva.`
                            : 'Exploración EDGE DEMO inactiva. El sistema opera en modo estándar.'}
                    />
                </div>
            </div>

            {/* ── Panel EDGE DEMO Exploration ────────────────────────────── */}
            <AnimatePresence>
                {explorationState && (
                    <motion.div
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                    >
                        <GlassPanel className={cn(
                            'border transition-colors',
                            explorationActive
                                ? 'border-aethelgard-gold/20 bg-aethelgard-gold/[0.03]'
                                : 'border-white/5',
                        )}>
                            <button
                                onClick={() => setIsExpanded(v => !v)}
                                className="w-full flex items-center justify-between p-4 hover:bg-white/[0.02] transition-colors rounded-xl"
                            >
                                <div className="flex items-center gap-3">
                                    <Search size={14} className={explorationActive ? 'text-aethelgard-gold' : 'text-white/30'} />
                                    <span className="text-[11px] font-black uppercase tracking-[0.15em] text-white/80">
                                        EDGE DEMO · Ciclo Evolutivo de Exploración
                                    </span>
                                    {explorationActive && (
                                        <span className="text-[8px] font-bold uppercase px-2 py-0.5 rounded-full bg-aethelgard-gold/15 text-aethelgard-gold border border-aethelgard-gold/25 animate-pulse">
                                            ACTIVE
                                        </span>
                                    )}
                                </div>
                                <div className="flex items-center gap-3">
                                    <span className="text-[9px] font-mono text-white/30">
                                        {explorationState.assets_in_exploration.length} activos
                                    </span>
                                    {isExplorationExpanded
                                        ? <ChevronUp size={12} className="text-white/30" />
                                        : <ChevronDown size={12} className="text-white/30" />}
                                </div>
                            </button>

                            <AnimatePresence>
                                {isExplorationExpanded && (
                                    <motion.div
                                        initial={{ opacity: 0, height: 0 }}
                                        animate={{ opacity: 1, height: 'auto' }}
                                        exit={{ opacity: 0, height: 0 }}
                                        className="overflow-hidden"
                                    >
                                        <div className="px-4 pb-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                                            <ExplorationStat icon={<TrendingUp size={13} />} label="Budget"
                                                value={`${explorationState.budget_remaining?.toFixed(0) ?? 0}%`}
                                                color="text-aethelgard-green"
                                                tooltip="Presupuesto de exploración restante para el ciclo actual." />
                                            <ExplorationStat icon={<BarChart3 size={13} />} label="Expl. PF"
                                                value={explorationState.exploratory_pf > 0 ? explorationState.exploratory_pf.toFixed(2) : '—'}
                                                color="text-aethelgard-blue"
                                                tooltip="Profit factor acumulado de señales EXPLORATION_ON." />
                                            <ExplorationStat icon={<Snowflake size={13} />} label="Frozen"
                                                value={String(explorationState.frozen_assets.length)}
                                                color="text-blue-400"
                                                tooltip="Activos en estado freeze (sin nuevas entradas exploratorias)." />
                                            <ExplorationStat icon={<RotateCcw size={13} />} label="Rollbacks"
                                                value={String(explorationState.rollback_count)}
                                                color={explorationState.rollback_count > 0 ? 'text-orange-400' : 'text-white/30'}
                                                tooltip="Reversiones aplicadas ante resultados negativos." />
                                        </div>

                                        <div className="px-4 pb-4 flex flex-col gap-3">
                                            {explorationState.exploration_on_count > 0 && (
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[8px] font-black uppercase tracking-widest text-purple-400">EXPLORATION_ON</span>
                                                    <span className="text-[9px] font-mono text-white/60">
                                                        {explorationState.exploration_on_count} señales activas
                                                    </span>
                                                </div>
                                            )}
                                            {explorationState.assets_in_exploration.length > 0 && (
                                                <div className="flex flex-col gap-1.5">
                                                    <span className="text-[8px] text-white/30 uppercase tracking-widest">Activos en exploración</span>
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {explorationState.assets_in_exploration.map(asset => {
                                                            const isFrozen = explorationState.frozen_assets.includes(asset);
                                                            return (
                                                                <span key={asset}
                                                                    title={isFrozen ? `${asset}: FROZEN` : `${asset}: explorando`}
                                                                    className={cn(
                                                                        'text-[8px] font-mono px-2 py-0.5 rounded border',
                                                                        isFrozen
                                                                            ? 'text-blue-400/70 bg-blue-400/5 border-blue-400/20'
                                                                            : 'text-aethelgard-gold/80 bg-aethelgard-gold/5 border-aethelgard-gold/20',
                                                                    )}>
                                                                    {isFrozen && '❄ '}{asset}
                                                                </span>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            )}
                                            {explorationState.handshake_logs && explorationState.handshake_logs.length > 0 && (
                                                <div className="flex flex-col gap-1.5">
                                                    <span className="text-[8px] text-white/30 uppercase tracking-widest">Handshake Log</span>
                                                    <div className="flex flex-col gap-1 max-h-24 overflow-y-auto scrollbar-hide">
                                                        {explorationState.handshake_logs.slice(-4).map((log, idx) => (
                                                            <p key={idx} className="text-[8px] font-mono text-white/40 leading-relaxed">{log}</p>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                            {explorationState.last_handshake && (
                                                <span className="text-[7px] font-mono text-white/20">
                                                    Last handshake: {new Date(explorationState.last_handshake).toLocaleTimeString()}
                                                </span>
                                            )}
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </GlassPanel>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── Main Grid ──────────────────────────────────────────────── */}
            <div className="grid grid-cols-12 gap-6">
                {/* Left column */}
                <div className="col-span-12 lg:col-span-8 grid grid-cols-1 md:grid-cols-2 gap-6">

                    {/* Confidence Radar — datos reales de metrics */}
                    <GlassPanel className="p-6 flex flex-col gap-6" premium>
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-white/90 uppercase tracking-widest flex items-center gap-2">
                                <Target size={16} className="text-aethelgard-green" />
                                Confidence Radar
                            </h3>
                            <span className="text-[10px] font-mono text-white/40">Real-time</span>
                        </div>

                        <div className="flex flex-col items-center justify-center py-4 relative">
                            <div className="w-48 h-48 rounded-full border-4 border-white/5 flex items-center justify-center relative">
                                <div className="absolute inset-0 rounded-full border border-aethelgard-green/20 animate-ping" />
                                <div className="flex flex-col items-center">
                                    <span className="text-5xl font-outfit font-black text-white">{metrics.confidence}%</span>
                                    <span className="text-[10px] font-bold text-aethelgard-green uppercase tracking-widest">Calculated Edge</span>
                                </div>
                            </div>
                            <div className="grid grid-cols-2 w-full mt-8 gap-4">
                                <StatRow label="Global Bias"   value={metrics.global_bias} />
                                <StatRow label="ADX Strength"  value={metrics.adx_strength.toFixed(2)} />
                                <StatRow label="Volatility"    value={metrics.volatility} />
                                <StatRow label="Optimization"  value={`${metrics.optimization_rate}%`} />
                            </div>
                        </div>
                    </GlassPanel>

                    <div className="flex flex-col gap-6">
                        {/* Autonomous Agents — estado real de modulesStatus */}
                        <GlassPanel className="p-5 flex-1 border-white/5">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-[10px] font-bold text-white/50 uppercase tracking-[0.2em]">
                                    Autonomous Agents
                                </h3>
                                {!modulesStatus && (
                                    <span className="text-[8px] text-white/20 font-mono">loading…</span>
                                )}
                            </div>
                            <div className="flex flex-col gap-3">
                                {AGENT_MODULES.map(({ key, name }) => (
                                    <AgentItem
                                        key={key}
                                        name={name}
                                        active={!!modules[key]}
                                        available={key in modules}
                                    />
                                ))}
                            </div>
                        </GlassPanel>

                        {/* Tuner Activity — últimos eventos reales de getTuningLogs */}
                        <GlassPanel className="p-5 flex-1 border-white/5 bg-gradient-to-br from-white/[0.02] to-transparent">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-[10px] font-bold text-white/50 uppercase tracking-[0.2em]">Tuner Activity</h3>
                                <RefreshCcw size={12} className={cn('text-white/20', logsLoading && 'animate-spin')} />
                            </div>
                            <div className="space-y-2">
                                {logsLoading ? (
                                    <p className="text-[9px] text-white/25 italic">Cargando actividad…</p>
                                ) : tuningLogs.length === 0 ? (
                                    <p className="text-[9px] text-white/25 italic">Sin ajustes registrados aún.</p>
                                ) : (
                                    tuningLogs.slice(0, 3).map(log => (
                                        <TunerEntry key={log.id} log={log} />
                                    ))
                                )}
                            </div>
                        </GlassPanel>
                    </div>
                </div>

                {/* Right column — Cerebro Insights: thoughts reales del WebSocket */}
                <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
                    <GlassPanel className="p-6 border-aethelgard-green/10 flex flex-col gap-6 bg-gradient-to-b from-aethelgard-green/[0.03] to-transparent">
                        <div>
                            <h3 className="text-sm font-bold text-white/90 uppercase tracking-widest mb-1">Cerebro Insights</h3>
                            <p className="text-[11px] text-white/60">Análisis en tiempo real del motor Cerebro.</p>
                        </div>

                        <div className="flex flex-col gap-3 flex-1 overflow-y-auto scrollbar-hide max-h-72">
                            {insightThoughts.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-8 gap-2 opacity-30">
                                    <BrainCircuit size={24} />
                                    <p className="text-[10px] uppercase tracking-widest">Sin análisis disponible</p>
                                </div>
                            ) : (
                                insightThoughts.map(thought => (
                                    <ThoughtInsightCard key={thought.id} thought={thought} />
                                ))
                            )}
                            {explorationActive && explorationState && (
                                <ExplorationInsightCard explorationState={explorationState} />
                            )}
                        </div>

                        <button
                            onClick={handleOpenLogs}
                            className="w-full py-3 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-white/60 hover:bg-white/10 hover:text-white transition-all active:scale-[0.98] mt-auto"
                        >
                            Ver logs detallados
                        </button>
                    </GlassPanel>
                </div>

                {/* WeightedMetricsVisualizer — Full Width */}
                <div className="col-span-12">
                    <WeightedMetricsVisualizer currentRegime={regime} height={350} />
                </div>
            </div>

            <NeuralHistoryPanel
                isOpen={isLogsOpen}
                onClose={() => setIsLogsOpen(false)}
                logs={tuningLogs}
            />
        </div>
    );
}

// ── StatusBadge ── patrón visual unificado ────────────────────────────────────

interface StatusBadgeProps {
    active: boolean;
    labelOn: string;
    labelOff: string;
    colorOn: 'green' | 'gold' | 'blue';
    tooltip?: string;
}

function StatusBadge({ active, labelOn, labelOff, colorOn, tooltip }: StatusBadgeProps) {
    const colorMap = {
        green: { bg: 'bg-aethelgard-green/10', border: 'border-aethelgard-green/30', dot: 'bg-aethelgard-green', text: 'text-aethelgard-green' },
        gold:  { bg: 'bg-aethelgard-gold/10',  border: 'border-aethelgard-gold/30',  dot: 'bg-aethelgard-gold',  text: 'text-aethelgard-gold'  },
        blue:  { bg: 'bg-aethelgard-blue/10',  border: 'border-aethelgard-blue/30',  dot: 'bg-aethelgard-blue',  text: 'text-aethelgard-blue'  },
    };
    const c = colorMap[colorOn];
    return (
        <div title={tooltip} className={cn(
            'flex items-center gap-2.5 px-4 py-2 rounded-2xl border transition-all duration-300 cursor-default',
            active ? `${c.bg} ${c.border}` : 'bg-white/5 border-white/10',
        )}>
            {active ? (
                <motion.div animate={{ scale: [1, 1.35, 1], opacity: [1, 0.7, 1] }}
                    transition={{ duration: 2, repeat: Infinity }}
                    className={cn('w-2 h-2 rounded-full flex-shrink-0', c.dot)} />
            ) : (
                <div className="w-2 h-2 rounded-full flex-shrink-0 bg-white/20" />
            )}
            <span className={cn('text-xs font-bold tracking-widest uppercase', active ? c.text : 'text-white/40')}>
                {active ? labelOn : labelOff}
            </span>
        </div>
    );
}

// ── AgentItem — estado real de módulo ─────────────────────────────────────────

function AgentItem({ name, active, available }: { name: string; active: boolean; available: boolean }) {
    return (
        <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
                <div className={cn(
                    'w-1.5 h-1.5 rounded-full flex-shrink-0',
                    !available ? 'bg-white/10'
                        : active ? 'bg-aethelgard-green shadow-[0_0_6px_rgba(0,255,136,0.5)]'
                        : 'bg-red-500/60',
                )} />
                <span className="text-[11px] font-bold text-white/90">{name}</span>
            </div>
            <span className={cn(
                'text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded',
                !available ? 'text-white/20 bg-white/5'
                    : active ? 'text-aethelgard-green bg-aethelgard-green/10'
                    : 'text-red-400/80 bg-red-500/10',
            )}>
                {!available ? '—' : active ? 'ON' : 'OFF'}
            </span>
        </div>
    );
}

// ── TunerEntry — entrada real de tuning log ───────────────────────────────────

function TunerEntry({ log }: { log: TuningLog }) {
    const timeAgo = (() => {
        const diff = Date.now() - new Date(log.timestamp).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1)  return 'ahora';
        if (mins < 60) return `hace ${mins}m`;
        return `hace ${Math.floor(mins / 60)}h`;
    })();

    const summary = log.action_taken ?? log.details ?? log.trigger ?? log.type;

    const paramChange = log.old_params && log.new_params
        ? Object.entries(log.new_params)
            .filter(([k, v]) => log.old_params![k] !== undefined && log.old_params![k] !== v)
            .map(([k, v]) => `${k}: ${log.old_params![k]} → ${v}`)
            .join(', ')
        : null;

    return (
        <div className="p-3 rounded-lg bg-white/5 border border-white/5">
            {paramChange ? (
                <p className="text-[10px] text-white/80 leading-relaxed font-medium">
                    {paramChange}
                </p>
            ) : (
                <p className="text-[10px] text-white/80 leading-relaxed font-medium line-clamp-2">
                    {summary}
                </p>
            )}
            <div className="flex items-center justify-between mt-1.5">
                <span className="text-[8px] font-mono text-purple-400/60 uppercase">{log.type}</span>
                <span className="text-[8px] text-white/25 font-mono">{timeAgo}</span>
            </div>
        </div>
    );
}

// ── ThoughtInsightCard — thought real del Cerebro ────────────────────────────

const THOUGHT_ICON: Record<CerebroThought['level'], React.ReactNode> = {
    info:    <Info size={14} />,
    success: <CheckCircle2 size={14} />,
    warning: <AlertTriangle size={14} />,
    error:   <AlertCircle size={14} />,
    debug:   <Info size={14} />,
};

const THOUGHT_COLOR: Record<CerebroThought['level'], string> = {
    info:    'text-aethelgard-blue',
    success: 'text-aethelgard-green',
    warning: 'text-aethelgard-gold',
    error:   'text-red-400',
    debug:   'text-white/30',
};

function ThoughtInsightCard({ thought }: { thought: CerebroThought }) {
    const timeAgo = (() => {
        const diff = Date.now() - new Date(thought.timestamp).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1)  return 'ahora';
        if (mins < 60) return `hace ${mins}m`;
        return `hace ${Math.floor(mins / 60)}h`;
    })();

    return (
        <div className="flex gap-3 p-3 rounded-xl bg-white/5 border border-white/5 hover:border-white/10 transition-colors group">
            <div className={cn('mt-0.5 flex-shrink-0 opacity-70 group-hover:opacity-100 transition-opacity', THOUGHT_COLOR[thought.level])}>
                {THOUGHT_ICON[thought.level]}
            </div>
            <div className="flex flex-col gap-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                    <span className="text-[9px] font-black uppercase tracking-widest text-white/40">{thought.module}</span>
                    <span className="text-[8px] font-mono text-white/20 flex-shrink-0">{timeAgo}</span>
                </div>
                <p className="text-[10px] leading-relaxed text-white/70 line-clamp-2">{thought.message}</p>
            </div>
        </div>
    );
}

// ── ExplorationInsightCard — insight de exploración activa ───────────────────

function ExplorationInsightCard({ explorationState }: { explorationState: ExplorationState }) {
    return (
        <div className="flex gap-3 p-3 rounded-xl bg-aethelgard-gold/5 border border-aethelgard-gold/15 hover:border-aethelgard-gold/25 transition-colors group">
            <div className="mt-0.5 flex-shrink-0 text-aethelgard-gold opacity-70 group-hover:opacity-100">
                <Search size={14} />
            </div>
            <div className="flex flex-col gap-1 min-w-0">
                <span className="text-[9px] font-black uppercase tracking-widest text-aethelgard-gold/60">EDGE DEMO</span>
                <p className="text-[10px] leading-relaxed text-white/70 line-clamp-2">
                    {explorationState.assets_in_exploration.length} activos en exploración.
                    PF exploratorio: {explorationState.exploratory_pf > 0 ? explorationState.exploratory_pf.toFixed(2) : '—'}.
                    Rollbacks: {explorationState.rollback_count}.
                </p>
            </div>
        </div>
    );
}

// ── Sub-componentes utilitarios ───────────────────────────────────────────────

function StatRow({ label, value }: { label: string; value: string | number }) {
    return (
        <div className="flex justify-between items-center py-2 border-b border-white/5">
            <span className="text-[10px] text-white/50 font-medium uppercase tracking-wider">{label}</span>
            <span className="text-[11px] text-white/90 font-bold font-mono">{value}</span>
        </div>
    );
}

function ExplorationStat({ icon, label, value, color, tooltip }: {
    icon: React.ReactNode; label: string; value: string; color: string; tooltip?: string;
}) {
    return (
        <div title={tooltip} className="flex flex-col gap-2 p-3 rounded-xl bg-white/[0.02] border border-white/5 cursor-help">
            <div className={cn('opacity-70', color)}>{icon}</div>
            <span className="text-[8px] text-white/40 uppercase tracking-widest font-bold">{label}</span>
            <span className={cn('text-base font-outfit font-black', color)}>{value}</span>
        </div>
    );
}
