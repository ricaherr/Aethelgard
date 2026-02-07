import { useState, useEffect, useCallback, useRef } from 'react';
import { MarketRegime, Signal, CerebroThought, SystemStatus, EdgeMetrics } from '../types/aethelgard';

export function useAethelgard() {
    const [regime, setRegime] = useState<MarketRegime>('NEUTRAL');
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
        const wsUrl = `${protocol}//${host}/ws/UI/dashboard_nextgen`;

        console.log(`📡 Connecting to Aethelgard: ${wsUrl}`);

        ws.current = new WebSocket(wsUrl);

        ws.current.onopen = () => {
            console.log('✅ Connected to Aethelgard Brain');
            setStatus(prev => ({ ...prev, connected: true }));
        };

        ws.current.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleIncomingData(data);
            } catch (err) {
                console.error('❌ Error parsing WS message:', err);
            }
        };

        ws.current.onclose = () => {
            console.log('🔌 Disconnected from Brain. Retrying in 5s...');
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
                    heartbeats: { ...prev.heartbeats, ...payload }
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
                console.log(`ℹ️ Received unknown event type: ${type}`);
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

    return {
        regime,
        signals,
        thoughts,
        status,
        metrics,
        sendCommand
    };
}
