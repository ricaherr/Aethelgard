import React, { useEffect, useRef, useCallback } from 'react';
import { useShadow } from '../../contexts/ShadowContext';
import { ShadowInstance, WebSocketShadowEvent } from '../../types/aethelgard';
import CompetitionDashboard from './CompetitionDashboard';
import JustifiedActionsLog from './JustifiedActionsLog';
import styles from '../../styles/shadow.module.css';

interface ShadowHubProps {
    wsUrl?: string;
}

const ShadowHub: React.FC<ShadowHubProps> = ({ wsUrl = 'ws://localhost:8000/ws/shadow' }) => {
    const { instances, setInstances, updateInstance, bestPerformer, setBesPerformer } = useShadow();
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectAttemptsRef = useRef<number>(0);
    const instancesRef = useRef(instances);
    const bestPerformerRef = useRef(bestPerformer);
    const updateInstanceRef = useRef(updateInstance);
    const setBesPerformerRef = useRef(setBesPerformer);
    const [wsConnected, setWsConnected] = React.useState(false);

    // Keep refs in sync with state
    useEffect(() => {
        instancesRef.current = instances;
    }, [instances]);

    useEffect(() => {
        bestPerformerRef.current = bestPerformer;
    }, [bestPerformer]);

    useEffect(() => {
        updateInstanceRef.current = updateInstance;
    }, [updateInstance]);

    useEffect(() => {
        setBesPerformerRef.current = setBesPerformer;
    }, [setBesPerformer]);

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
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        let keepaliveIntervalId: ReturnType<typeof setInterval> | null = null;

        ws.onopen = () => {
            console.log('[ShadowHub] ✓ Connected');
            setWsConnected(true);
            reconnectAttemptsRef.current = 0;

            // Send keepalive every 25s (before server's 30s timeout)
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
                        const updated = { ...updatedInstance };
                        updated.health_status = message.health_status || 'MONITOR';
                        updated.pilar1_status = message.pilar1_status || 'UNKNOWN';
                        updated.pilar2_status = message.pilar2_status || 'UNKNOWN';
                        updated.pilar3_status = message.pilar3_status || 'UNKNOWN';
                        updated.metrics = {
                            ...updated.metrics,
                            profit_factor: message.metrics.profit_factor,
                            win_rate: message.metrics.win_rate,
                            max_drawdown_pct: message.metrics.max_drawdown_pct,
                            consecutive_losses_max: message.metrics.consecutive_losses_max,
                            total_trades_executed: message.metrics.total_trades_executed,
                        };
                        updated.last_evaluation = message.timestamp || new Date().toISOString();

                        updateInstanceRef.current(updated);

                        if (bestPerformerRef.current === null || message.metrics.profit_factor > bestPerformerRef.current.metrics.profit_factor) {
                            setBesPerformerRef.current(updated);
                        }
                    }
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
            
            // Cleanup keepalive interval
            if (keepaliveIntervalId) {
                clearInterval(keepaliveIntervalId);
            }
            
            // Reconnect with exponential backoff
            reconnectAttemptsRef.current++;
            if (reconnectAttemptsRef.current <= 5) {
                const delayMs = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current - 1), 30000);
                console.log(`[ShadowHub] Reconnecting in ${delayMs}ms...`);
                setTimeout(() => {
                    if (wsRef.current?.readyState === WebSocket.CLOSED) {
                        const newWs = new WebSocket(wsUrl);
                        wsRef.current = newWs;
                        
                        newWs.onopen = () => {
                            setWsConnected(true);
                            reconnectAttemptsRef.current = 0;
                            
                            // Restart keepalive for new connection
                            keepaliveIntervalId = setInterval(() => {
                                if (newWs.readyState === WebSocket.OPEN) {
                                    newWs.send(JSON.stringify({ type: 'KEEPALIVE' }));
                                    console.debug('[ShadowHub] ℹ Sent keepalive ping');
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
            // Cleanup on unmount
            if (keepaliveIntervalId) {
                clearInterval(keepaliveIntervalId);
            }
            if (ws && ws.readyState !== WebSocket.CLOSED) {
                ws.close();
            }
        };
    }, [wsUrl]); // ← SOLO wsUrl, las funciones se acceden vía refs

    return (
        <div data-testid="shadow-hub" className="w-full h-full space-y-6 p-6">
            {/* Competition Dashboard: 3x2 grid of SHADOW instances */}
            <CompetitionDashboard />

            {/* Justified Actions Log: Real-time event stream */}
            <JustifiedActionsLog />

            {/* Status Badge - Shows active shadow mode, connection state, and best performer */}
            {instances.length > 0 && (
                <div className="text-xs text-blue-400 font-mono space-y-1">
                    <div>
                        Active Instances: {instances.length} | Best Performer:{' '}
                        {bestPerformer?.instance_id || 'None'} (PF: {bestPerformer?.metrics.profit_factor.toFixed(2) || 'N/A'})
                    </div>
                    <div>WebSocket: {wsConnected ? '✓ Connected' : '✗ Waiting for connection...'}</div>
                </div>
            )}
        </div>
    );
};

export default ShadowHub;
