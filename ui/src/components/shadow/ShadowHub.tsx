import React, { useEffect, useCallback } from 'react';
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

    // Fetch initial SHADOW instances
    useEffect(() => {
        const fetchInstances = async () => {
            try {
                const response = await fetch('/api/shadow/instances');
                if (!response.ok) throw new Error('Failed to fetch instances');
                const data: ShadowInstance[] = await response.json();
                setInstances(data);

                // Set best performer (highest profit_factor among HEALTHY)
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

    // WebSocket listener for SHADOW_STATUS_UPDATE events
    useEffect(() => {
        let ws: WebSocket | null = null;

        const connectWS = () => {
            try {
                ws = new WebSocket(wsUrl);

                ws.onopen = () => {
                    console.log('[ShadowHub] WebSocket connected');
                };

                ws.onmessage = (event: MessageEvent) => {
                    try {
                        const message = JSON.parse(event.data);

                        if (message.event_type === 'SHADOW_STATUS_UPDATE') {
                            const wsEvent: WebSocketShadowEvent = message;

                            // Find and update instance
                            const updatedInstance = instances.find(
                                (i: ShadowInstance) => i.instance_id === wsEvent.instance_id
                            );

                            if (updatedInstance) {
                                updatedInstance.health_status = wsEvent.health_status;
                                updatedInstance.pilar1_status = wsEvent.pillar1_profitability;
                                updatedInstance.pilar2_status = wsEvent.pillar2_resiliencia;
                                updatedInstance.pilar3_status = wsEvent.pillar3_consistency;
                                updatedInstance.metrics.profit_factor = wsEvent.profit_factor;
                                updatedInstance.metrics.win_rate = wsEvent.win_rate;
                                updatedInstance.metrics.max_drawdown_pct = wsEvent.max_drawdown;
                                updatedInstance.last_evaluation = wsEvent.timestamp;

                                updateInstance(updatedInstance);

                                // Update best performer if needed
                                if (
                                    bestPerformer === null ||
                                    wsEvent.profit_factor > bestPerformer.metrics.profit_factor
                                ) {
                                    setBesPerformer(updatedInstance);
                                }
                            }
                        }
                    } catch (parseError) {
                        console.error('[ShadowHub] WebSocket message parse error:', parseError);
                    }
                };

                ws.onerror = (error: Event) => {
                    console.error('[ShadowHub] WebSocket error:', error);
                };

                ws.onclose = () => {
                    console.log('[ShadowHub] WebSocket disconnected');
                    // Attempt reconnect after 5 seconds
                    setTimeout(connectWS, 5000);
                };
            } catch (error) {
                console.error('[ShadowHub] WebSocket connection error:', error);
            }
        };

        connectWS();

        return () => {
            if (ws) {
                ws.close();
            }
        };
    }, [wsUrl, instances, updateInstance, bestPerformer, setBesPerformer]);

    return (
        <div data-testid="shadow-hub" className="w-full h-full space-y-6 p-6">
            {/* Competition Dashboard: 3x2 grid of SHADOW instances */}
            <CompetitionDashboard />

            {/* Justified Actions Log: Real-time event stream */}
            <JustifiedActionsLog />

            {/* Status Badge - Shows active shadow mode and best performer */}
            {instances.length > 0 && (
                <div className="text-xs text-blue-400 font-mono">
                    Active Instances: {instances.length} | Best Performer:{' '}
                    {bestPerformer?.instance_id || 'None'} (PF: {bestPerformer?.metrics.profit_factor.toFixed(2) || 'N/A'})
                </div>
            )}
        </div>
    );
};

export default ShadowHub;
