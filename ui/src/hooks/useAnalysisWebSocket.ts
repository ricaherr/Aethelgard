import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from './useAuth';

export interface AnalysisUpdate {
    type: 'ANALYSIS_UPDATE' | 'TRADER_PAGE_UPDATE';
    payload: {
        priority?: 'high' | 'low';
        analysis_detected?: boolean;
        analysis_signals?: Record<string, any>;
        elements?: any[];
        element_count?: number;
        timestamp?: string;
    };
}

export const useAnalysisWebSocket = () => {
    const { isAuthenticated } = useAuth();
    const [connected, setConnected] = useState(false);
    const [analysisData, setAnalysisData] = useState<AnalysisUpdate['payload'] | null>(null);
    const [loading, setLoading] = useState(true);
    const ws = useRef<WebSocket | null>(null);
    const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

    const connect = useCallback(() => {
        if (!isAuthenticated) {
            setLoading(false);
            return;
        }

        // Prevent duplicate connections
        if (ws.current?.readyState === WebSocket.OPEN || ws.current?.readyState === WebSocket.CONNECTING) {
            return;
        }

        // Determine WS URL
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname === 'localhost' 
            ? 'localhost:8000' 
            : window.location.host;
        const wsUrl = `${protocol}//${host}/ws/GENERIC/analysis`;

        console.log('🔌 [ANALYSIS WS] Connecting to analysis stream:', wsUrl);

        try {
            const socket = new WebSocket(wsUrl);
            ws.current = socket;

            socket.onopen = () => {
                console.log('✅ [ANALYSIS WS] Connected to analysis WebSocket');
                setConnected(true);
                setLoading(false);
                // Clear reconnect timeout on successful connection
                if (reconnectTimeout.current) {
                    clearTimeout(reconnectTimeout.current);
                    reconnectTimeout.current = null;
                }
            };

            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'ANALYSIS_UPDATE' || data.type === 'TRADER_PAGE_UPDATE') {
                        console.log('📊 [ANALYSIS WS] Received analysis update:', data.type);
                        setAnalysisData(data.payload);
                    }
                } catch (err) {
                    console.error('❌ [ANALYSIS WS] Error parsing message:', err);
                }
            };

            socket.onclose = () => {
                console.log('🔌 [ANALYSIS WS] Disconnected from analysis WebSocket');
                setConnected(false);
                
                // Auto-reconnect after 3 seconds
                if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
                reconnectTimeout.current = setTimeout(() => {
                    console.log('🔄 [ANALYSIS WS] Attempting reconnect...');
                    connect();
                }, 3000);
            };

            socket.onerror = (err) => {
                console.error('⚠️ [ANALYSIS WS] WebSocket error:', err);
                setConnected(false);
            };
        } catch (err) {
            console.error('❌ [ANALYSIS WS] Failed to create WebSocket:', err);
            setConnected(false);
        }
    }, [isAuthenticated]);

    // Connect on mount
    useEffect(() => {
        if (isAuthenticated) {
            connect();
        }

        return () => {
            if (ws.current) {
                ws.current.close();
                ws.current = null;
            }
            if (reconnectTimeout.current) {
                clearTimeout(reconnectTimeout.current);
            }
        };
    }, [isAuthenticated, connect]);

    return {
        connected,
        analysisData,
        loading,
        refetch: connect
    };
};
