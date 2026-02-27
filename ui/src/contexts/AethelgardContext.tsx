import React, { createContext, useContext, ReactNode, useState, useEffect, useCallback, useRef } from 'react';
import { MarketRegime, Signal, CerebroThought, SystemStatus, EdgeMetrics } from '../types/aethelgard';
import { useAuthContext } from './AuthContext';
import { useApi } from '../hooks/useApi';

interface AethelgardContextType {
    regime: MarketRegime;
    signals: Signal[];
    thoughts: CerebroThought[];
    status: SystemStatus;
    metrics: EdgeMetrics;
    riskStatus: any;
    modulesStatus: any;
    sendCommand: (action: string, params?: any) => void;
    runAudit: () => Promise<boolean>;
    runRepair: (stage: string) => Promise<boolean>;
    getTuningLogs: (limit?: number) => Promise<any[]>;
}

const AethelgardContext = createContext<AethelgardContextType | undefined>(undefined);

export function AethelgardProvider({ children }: { children: ReactNode }) {
    const { token } = useAuthContext();
    const { apiFetch } = useApi();
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
    const [riskStatus, setRiskStatus] = useState<any>(null);
    const [modulesStatus, setModulesStatus] = useState<any>(null);

    const ws = useRef<WebSocket | null>(null);
    const reconnectTimeout = useRef<any>(null);

    const handleIncomingData = useCallback((data: any) => {
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
    }, []);

    const connect = useCallback(() => {
        if (!token) return;
        if (ws.current?.readyState === WebSocket.OPEN || ws.current?.readyState === WebSocket.CONNECTING) return;

        // Determine WS URL (handling dev/prod)
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host;
        const wsUrl = `${protocol}//${host}/ws/GENERIC/dashboard_nextgen?token=${token}`;

        console.log('🔌 [CONTEXT] Connecting to Brain WebSocket...');
        const socket = new WebSocket(wsUrl);
        ws.current = socket;

        socket.onopen = () => {
            console.log('✅ [CONTEXT] WebSocket Connected');
            setStatus(prev => ({ ...prev, connected: true }));
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleIncomingData(data);
            } catch (err) {
                console.error('❌ Error parsing WS message:', err);
            }
        };

        socket.onclose = () => {
            console.log('🔌 [CONTEXT] WebSocket Disconnected');
            setStatus(prev => ({ ...prev, connected: false }));
            if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
            reconnectTimeout.current = setTimeout(connect, 5000);
        };

        socket.onerror = (err) => {
            console.error('⚠️ [CONTEXT] WebSocket Error:', err);
        };
    }, [token, handleIncomingData]);

    // WebSocket Lifecycle
    useEffect(() => {
        if (token) {
            connect();
        }
        return () => {
            if (ws.current) {
                ws.current.close();
                ws.current = null;
            }
            if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
        };
    }, [token, connect]);

    // Shared Status Polling
    useEffect(() => {
        if (!token) return;

        const fetchSharedStatus = async () => {
            try {
                const [riskRes, modulesRes] = await Promise.all([
                    apiFetch('/api/risk/status'),
                    apiFetch('/api/modules/status')
                ]);

                if (riskRes.ok) setRiskStatus(await riskRes.json());
                if (modulesRes.ok) setModulesStatus(await modulesRes.json());
            } catch (err) {
                console.error('Error polling system status:', err);
            }
        };

        fetchSharedStatus();
        const interval = setInterval(fetchSharedStatus, 20000);
        return () => clearInterval(interval);
    }, [token, apiFetch]);

    const sendCommand = useCallback((action: string, params: any = {}) => {
        if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({ action, params }));
        }
    }, []);

    const runAudit = useCallback(async () => {
        try {
            const response = await apiFetch('/api/system/audit', {
                method: 'POST'
            });
            const data = await response.json();
            return data.success === true;
        } catch (error) {
            console.error("Error triggering audit:", error);
            return false;
        }
    }, [apiFetch]);

    const runRepair = useCallback(async (stage: string) => {
        try {
            const response = await apiFetch('/api/system/audit/repair', {
                method: 'POST',
                body: JSON.stringify({ stage })
            });
            return response.ok;
        } catch (error) {
            console.error(`Error repairing stage ${stage}:`, error);
            return false;
        }
    }, [apiFetch]);

    const getTuningLogs = useCallback(async (limit: number = 50) => {
        try {
            const response = await apiFetch(`/api/edge/history?limit=${limit}`);
            const data = await response.json();
            return data.history || [];
        } catch (error) {
            console.error("Error fetching tuning logs:", error);
            return [];
        }
    }, [apiFetch]);

    const value = {
        regime,
        signals,
        thoughts,
        status,
        metrics,
        riskStatus,
        modulesStatus,
        sendCommand,
        runAudit,
        runRepair,
        getTuningLogs
    };

    return (
        <AethelgardContext.Provider value={value}>
            {children}
        </AethelgardContext.Provider>
    );
}

export function useAethelgardContext() {
    const context = useContext(AethelgardContext);
    if (context === undefined) {
        throw new Error('useAethelgardContext must be used within an AethelgardProvider');
    }
    return context;
}
