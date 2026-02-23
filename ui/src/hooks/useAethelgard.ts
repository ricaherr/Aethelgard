import { useState, useEffect, useCallback, useRef } from 'react';
import { MarketRegime, Signal, CerebroThought, SystemStatus, EdgeMetrics } from '../types/aethelgard';

export function useAethelgard() {
    const [regime, setRegime] = useState<MarketRegime>('NORMAL');
    const [signals, setSignals] = useState<Signal[]>([]);
    const [thoughts, setThoughts] = useState<CerebroThought[]>([]);
    const [status, setStatus] = useState<SystemStatus>({
        connected: false,
        lastUpdate: new Date().toISOString(),
        heartbeats: {}
    });
    const [metrics, setMetrics] = useState<EdgeMetrics>({
        adx_strength: 0,
        volatility: 'Low',
        global_bias: 'Neutral',
        confidence: 0,
        active_agents: 0,
        optimization_rate: 0
    });

    const ws = useRef<WebSocket | null>(null);

    const connect = useCallback(() => {
        // Determine WS URL (handling dev/prod)
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host;
        const wsUrl = `${protocol}//${host}/ws/GENERIC/dashboard_nextgen`;


        ws.current = new WebSocket(wsUrl);

        setStatus(prev => ({ ...prev, connected: true }));

        ws.current.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleIncomingData(data);
            } catch (err) {
                console.error('❌ Error parsing WS message:', err);
            }
        };

        ws.current.onclose = () => {
            setStatus(prev => ({ ...prev, connected: false }));
            setTimeout(connect, 5000);
        };

        ws.current.onerror = (err) => {
            console.error('⚠️ WebSocket Error:', err);
        };
    }, []);

    const handleIncomingData = (data: any) => {
        const { type, payload } = data;

        switch (type) {
            case 'REGIME_UPDATE':
                setRegime(payload.regime);
                if (payload.metrics) setMetrics(prev => ({ ...prev, ...payload.metrics }));
                break;

            case 'SIGNAL_NEW':
            case 'SIGNAL_UPDATE':
                setSignals(prev => {
                    const exists = prev.find(s => s.id === payload.id);
                    if (exists) {
                        return prev.map(s => s.id === payload.id ? { ...s, ...payload } : s);
                    }
                    return [payload, ...prev].slice(0, 50);
                });
                break;

            case 'SYSTEM_HEARTBEAT':
                setStatus(prev => ({
                    ...prev,
                    lastUpdate: new Date().toISOString(),
                    heartbeats: { ...prev.heartbeats, ...payload },
                    cpu_load: payload.cpu_load,
                    satellites: payload.satellites || prev.satellites
                }));
                break;

            case 'BREIN_THOUGHT':
                setThoughts(prev => [{
                    id: Math.random().toString(36).substr(2, 9),
                    timestamp: new Date().toISOString(),
                    ...payload
                }, ...prev].slice(0, 100));
                break;

            default:
                break;
        }
    };

    useEffect(() => {
        connect();
        return () => ws.current?.close();
    }, [connect]);

    const sendCommand = (action: string, params: any = {}) => {
        if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({ action, params }));
        }
    };

    const runAudit = async () => {
        try {
            const response = await fetch('/api/system/audit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();

            // Retornar true si la auditoría tuvo éxito, false en caso contrario
            return data.success === true;
        } catch (error) {
            console.error("Error triggering audit:", error);
            return false;
        }
    };

    const runRepair = async (stage: string) => {
        try {
            const response = await fetch('/api/system/audit/repair', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ stage })
            });
            return response.ok;
        } catch (error) {
            console.error(`Error repairing stage ${stage}:`, error);
            return false;
        }
    };

    const getTuningLogs = async (limit: number = 50) => {
        try {
            const response = await fetch(`/api/edge/tuning-logs?limit=${limit}`);
            const data = await response.json();
            return data.history || [];
        } catch (error) {
            console.error("Error fetching tuning logs:", error);
            return [];
        }
    };

    return {
        regime,
        signals,
        thoughts,
        status,
        metrics,
        sendCommand,
        runAudit,
        runRepair,
        getTuningLogs
    };
}
