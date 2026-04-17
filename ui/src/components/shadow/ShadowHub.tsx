import React, { useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Snowflake, RotateCcw, TrendingUp } from 'lucide-react';
import { useShadow } from '../../contexts/ShadowContext';
import { ShadowInstance, WebSocketShadowEvent, ExplorationState } from '../../types/aethelgard';
import CompetitionDashboard from './CompetitionDashboard';
import JustifiedActionsLog from './JustifiedActionsLog';
import styles from '../../styles/shadow.module.css';
import { getWsUrl } from '../../utils/wsUrl';
import { cn } from '../../utils/cn';

const ShadowHub: React.FC = () => {
    const { instances, setInstances, updateInstance, bestPerformer, setBesPerformer } = useShadow();
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectAttemptsRef = useRef<number>(0);
    const instancesRef = useRef(instances);
    const bestPerformerRef = useRef(bestPerformer);
    const updateInstanceRef = useRef(updateInstance);
    const setBesPerformerRef = useRef(setBesPerformer);
    const [wsConnected, setWsConnected] = React.useState(false);
    const [explorationState, setExplorationState] = React.useState<ExplorationState | null>(null);

    // Keep refs in sync with state
    useEffect(() => { instancesRef.current = instances; }, [instances]);
    useEffect(() => { bestPerformerRef.current = bestPerformer; }, [bestPerformer]);
    useEffect(() => { updateInstanceRef.current = updateInstance; }, [updateInstance]);
    useEffect(() => { setBesPerformerRef.current = setBesPerformer; }, [setBesPerformer]);

    // Fetch initial SHADOW instances
    useEffect(() => {
        const fetchInstances = async () => {
            try {
                const response = await fetch('/api/shadow/instances');
                if (!response.ok) throw new Error('Failed to fetch instances');
                const data: ShadowInstance[] = await response.json();
                setInstances(data);

                const healthy = data.filter((i) => i.health_status === 'HEALTHY');
                if (healthy.length > 0) {
                    const best = healthy.reduce((prev, curr) =>
                        curr.metrics.profit_factor > prev.metrics.profit_factor ? curr : prev
                    );
                    setBesPerformer(best);
                }
            } catch (error) {
                console.error('[ShadowHub] Failed to fetch instances:', error);
            }
        };

        fetchInstances();
    }, [setInstances, setBesPerformer]);

    // WebSocket connection - STABLE with refs
    useEffect(() => {
        const wsUrl = getWsUrl('/ws/shadow');
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        let keepaliveIntervalId: ReturnType<typeof setInterval> | null = null;

        ws.onopen = () => {
            console.log('[ShadowHub] ✓ Connected');
            setWsConnected(true);
            reconnectAttemptsRef.current = 0;

            keepaliveIntervalId = setInterval(() => {
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'KEEPALIVE' }));
                    console.debug('[ShadowHub] ℹ Sent keepalive ping');
                }
            }, 25000);
        };

        ws.onmessage = (event: MessageEvent) => {
            try {
                const message = JSON.parse(event.data) as WebSocketShadowEvent;

                if (message.event_type === 'SHADOW_STATUS_UPDATE' && message.instance_id && message.metrics) {
                    const updatedInstance = instancesRef.current.find((i) => i.instance_id === message.instance_id);

                    if (updatedInstance) {
                        const updated: ShadowInstance = {
                            ...updatedInstance,
                            health_status: message.health_status || 'MONITOR',
                            pilar1_status: message.pilar1_status || 'UNKNOWN',
                            pilar2_status: message.pilar2_status || 'UNKNOWN',
                            pilar3_status: message.pilar3_status || 'UNKNOWN',
                            metrics: {
                                ...updatedInstance.metrics,
                                profit_factor: message.metrics.profit_factor,
                                win_rate: message.metrics.win_rate,
                                max_drawdown_pct: message.metrics.max_drawdown_pct,
                                consecutive_losses_max: message.metrics.consecutive_losses_max,
                                total_trades_executed: message.metrics.total_trades_executed,
                            },
                            last_evaluation: message.timestamp || new Date().toISOString(),
                            has_exploratory_signals: message.has_exploratory_signals ?? updatedInstance.has_exploratory_signals,
                            edge_demo_frozen: message.edge_demo_frozen ?? updatedInstance.edge_demo_frozen,
                        };

                        updateInstanceRef.current(updated);

                        if (bestPerformerRef.current === null || message.metrics.profit_factor > bestPerformerRef.current.metrics.profit_factor) {
                            setBesPerformerRef.current(updated);
                        }
                    }
                }

                if (message.event_type === 'EDGE_EXPLORATION_UPDATE' && message.exploration_state) {
                    setExplorationState(message.exploration_state);
                }
            } catch (error) {
                console.error('[ShadowHub] Parse error:', error);
            }
        };

        ws.onerror = () => {
            console.error('[ShadowHub] WebSocket error');
            setWsConnected(false);
        };

        ws.onclose = () => {
            console.log('[ShadowHub] Disconnected');
            setWsConnected(false);

            if (keepaliveIntervalId) clearInterval(keepaliveIntervalId);

            reconnectAttemptsRef.current++;
            if (reconnectAttemptsRef.current <= 5) {
                const delayMs = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current - 1), 30000);
                console.log(`[ShadowHub] Reconnecting in ${delayMs}ms...`);
                setTimeout(() => {
                    if (wsRef.current?.readyState === WebSocket.CLOSED) {
                        const newWs = new WebSocket(getWsUrl('/ws/shadow'));
                        wsRef.current = newWs;

                        newWs.onopen = () => {
                            setWsConnected(true);
                            reconnectAttemptsRef.current = 0;
                            keepaliveIntervalId = setInterval(() => {
                                if (newWs.readyState === WebSocket.OPEN) {
                                    newWs.send(JSON.stringify({ type: 'KEEPALIVE' }));
                                }
                            }, 25000);
                        };
                        newWs.onmessage = ws.onmessage;
                        newWs.onerror = ws.onerror;
                        newWs.onclose = ws.onclose;
                    }
                }, delayMs);
            }
        };

        return () => {
            if (keepaliveIntervalId) clearInterval(keepaliveIntervalId);
            if (ws && ws.readyState !== WebSocket.CLOSED) ws.close();
        };
    }, []);

    const instancesWithExploration = instances.filter(i => i.has_exploratory_signals);
    const frozenInstances = instances.filter(i => i.edge_demo_frozen);

    return (
        <div data-testid="shadow-hub" className="w-full h-full space-y-6 p-6">
            {/* Competition Dashboard: 3x2 grid of SHADOW instances */}
            <CompetitionDashboard />

            {/* EDGE DEMO Exploration Impact Panel */}
            <AnimatePresence>
                {(explorationState?.active || instancesWithExploration.length > 0) && (
                    <motion.div
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 8 }}
                        className="rounded-2xl border border-aethelgard-gold/20 bg-aethelgard-gold/[0.03] p-4 space-y-3"
                    >
                        {/* Header */}
                        <div className="flex items-center gap-2">
                            <Search size={13} className="text-aethelgard-gold" />
                            <span className="text-[10px] font-black uppercase tracking-[0.15em] text-aethelgard-gold">
                                EDGE DEMO · Impacto de Exploración en SHADOW
                            </span>
                            {explorationState?.active && (
                                <span className="text-[7px] font-bold uppercase px-2 py-0.5 rounded-full bg-aethelgard-gold/15 text-aethelgard-gold border border-aethelgard-gold/25 animate-pulse ml-auto">
                                    ACTIVE
                                </span>
                            )}
                        </div>

                        {/* Metrics row */}
                        {explorationState && (
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                <ExplorationMetric
                                    icon={<Search size={11} />}
                                    label="Activos Expl."
                                    value={String(explorationState.assets_in_exploration.length)}
                                    color="text-aethelgard-gold"
                                    tooltip="Número de activos actualmente en el ciclo evolutivo EDGE DEMO."
                                />
                                <ExplorationMetric
                                    icon={<TrendingUp size={11} />}
                                    label="Expl. PF"
                                    value={explorationState.exploratory_pf > 0 ? explorationState.exploratory_pf.toFixed(2) : '—'}
                                    color="text-aethelgard-green"
                                    tooltip="Profit factor acumulado de señales exploratorias (EXPLORATION_ON) impactando instancias SHADOW."
                                />
                                <ExplorationMetric
                                    icon={<Snowflake size={11} />}
                                    label="Frozen"
                                    value={String(explorationState.frozen_assets.length)}
                                    color="text-blue-400"
                                    tooltip="Activos en estado freeze: sin nuevas entradas exploratorias hasta próxima evaluación."
                                />
                                <ExplorationMetric
                                    icon={<RotateCcw size={11} />}
                                    label="Rollbacks"
                                    value={String(explorationState.rollback_count)}
                                    color={explorationState.rollback_count > 0 ? 'text-orange-400' : 'text-white/30'}
                                    tooltip="Reversiones aplicadas por EDGE DEMO ante resultados negativos en instancias SHADOW."
                                />
                            </div>
                        )}

                        {/* Instances receiving exploratory signals */}
                        {instancesWithExploration.length > 0 && (
                            <div className="flex flex-col gap-1.5">
                                <span className="text-[8px] text-white/30 uppercase tracking-widest">
                                    Instancias SHADOW con señales exploratorias
                                </span>
                                <div className="flex flex-wrap gap-2">
                                    {instancesWithExploration.map(inst => (
                                        <div
                                            key={inst.instance_id}
                                            title={`${inst.instance_id}: recibiendo señales EXPLORATION_ON. PF exploratorio: ${inst.exploratory_pf?.toFixed(2) ?? '—'}`}
                                            className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-aethelgard-gold/5 border border-aethelgard-gold/20 cursor-help"
                                        >
                                            <Search size={8} className="text-aethelgard-gold/70" />
                                            <span className="text-[8px] font-mono text-white/70">{inst.instance_id}</span>
                                            {inst.exploratory_pf !== undefined && (
                                                <span className="text-[7px] font-mono text-aethelgard-green/70">
                                                    PF:{inst.exploratory_pf.toFixed(2)}
                                                </span>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Frozen instances */}
                        {frozenInstances.length > 0 && (
                            <div className="flex flex-col gap-1.5">
                                <span className="text-[8px] text-blue-400/60 uppercase tracking-widest">
                                    Instancias con freeze aplicado por EDGE DEMO
                                </span>
                                <div className="flex flex-wrap gap-2">
                                    {frozenInstances.map(inst => (
                                        <div
                                            key={inst.instance_id}
                                            title={`${inst.instance_id}: FREEZE activo — nuevas entradas exploratorias bloqueadas`}
                                            className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-blue-400/5 border border-blue-400/20 cursor-help"
                                        >
                                            <Snowflake size={8} className="text-blue-400/70" />
                                            <span className="text-[8px] font-mono text-white/60">{inst.instance_id}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Justified Actions Log: Real-time event stream */}
            <JustifiedActionsLog />

            {/* Status footer */}
            {instances.length > 0 && (
                <div className="text-xs font-mono space-y-1">
                    <div className="text-blue-400">
                        Active Instances: {instances.length} | Best Performer:{' '}
                        {bestPerformer?.instance_id || 'None'} (PF: {bestPerformer?.metrics.profit_factor.toFixed(2) || 'N/A'})
                        {instancesWithExploration.length > 0 && (
                            <span className="text-aethelgard-gold ml-2">
                                | EXPLORATION_ON: {instancesWithExploration.length} inst
                            </span>
                        )}
                    </div>
                    <div className={wsConnected ? 'text-aethelgard-green' : 'text-orange-400'}>
                        WebSocket: {wsConnected ? '✓ Connected' : '✗ Waiting for connection...'}
                    </div>
                </div>
            )}
        </div>
    );
};

function ExplorationMetric({
    icon, label, value, color, tooltip,
}: {
    icon: React.ReactNode;
    label: string;
    value: string;
    color: string;
    tooltip?: string;
}) {
    return (
        <div
            title={tooltip}
            className="flex flex-col gap-1.5 p-2.5 rounded-xl bg-white/[0.02] border border-white/5 cursor-help"
        >
            <div className={cn('opacity-70', color)}>{icon}</div>
            <span className="text-[7px] text-white/35 uppercase tracking-widest font-bold">{label}</span>
            <span className={cn('text-sm font-outfit font-black', color)}>{value}</span>
        </div>
    );
}

export default ShadowHub;
