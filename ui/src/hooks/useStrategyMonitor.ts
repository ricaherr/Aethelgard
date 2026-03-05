import { useEffect, useRef, useState, useCallback } from 'react';

interface StrategyMetrics {
  strategy_id: string;
  status: 'LIVE' | 'QUARANTINE' | 'SHADOW' | 'UNKNOWN';
  dd_pct: number;
  consecutive_losses: number;
  win_rate: number;
  profit_factor: number;
  blocked_for_trading: boolean;
  updated_at: string;
  trades_count?: number;
}

interface UseStrategyMonitorHook {
  strategies: StrategyMetrics[];
  loading: boolean;
  error: string | null;
  isConnected: boolean;
}

/**
 * Custom hook for real-time strategy monitoring via WebSocket.
 * RULE T1: Automatic tenant isolation via token in WebSocket URL.
 * 
 * Usage:
 * const { strategies, loading, error, isConnected } = useStrategyMonitor();
 */
export const useStrategyMonitor = (token?: string): UseStrategyMonitorHook => {
  const [strategies, setStrategies] = useState<StrategyMetrics[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = useRef(1000); // Start at 1s, exponential backoff

  const connect = useCallback(() => {
    // Get token from props or localStorage
    const authToken = token || localStorage.getItem('access_token');
    
    if (!authToken) {
      setError('No authentication token available');
      setLoading(false);
      return;
    }

    try {
      // RULE T1: WebSocket URL includes tenant token
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${protocol}//${window.location.host}/ws/strategy/monitor?token=${encodeURIComponent(authToken)}`;
      
      const socket = new WebSocket(url);

      socket.addEventListener('open', () => {
        console.log('[Strategy Monitor] WebSocket connected');
        setIsConnected(true);
        setLoading(false);
        setError(null);
        reconnectAttempts.current = 0;
        reconnectDelay.current = 1000;
      });

      socket.addEventListener('message', (event) => {
        try {
          const message = JSON.parse(event.data);

          if (message.type === 'metrics') {
            // Update full metrics list
            setStrategies(message.data || []);
          } else if (message.type === 'status_changed') {
            // Update single strategy status
            setStrategies((prev) =>
              prev.map((s) =>
                s.strategy_id === message.strategy_id
                  ? { ...s, status: message.new_status }
                  : s
              )
            );
          } else if (message.type === 'error') {
            console.error('[Strategy Monitor] Server error:', message.message);
            setError(message.message);
          } else if (message.type === 'pong') {
            // Keepalive response, ignore
            console.debug('[Strategy Monitor] Pong received');
          }
        } catch (err) {
          console.error('[Strategy Monitor] Message parse error:', err);
        }
      });

      socket.addEventListener('error', (event) => {
        console.error('[Strategy Monitor] WebSocket error:', event);
        setError('WebSocket connection error');
        setIsConnected(false);
      });

      socket.addEventListener('close', () => {
        console.log('[Strategy Monitor] WebSocket disconnected');
        setIsConnected(false);
        ws.current = null;

        // Attempt reconnection (exponential backoff)
        if (reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current++;
          const delay = Math.min(reconnectDelay.current * Math.pow(1.5, reconnectAttempts.current), 30000);
          
          console.log(`[Strategy Monitor] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current}/${maxReconnectAttempts})`);
          
          reconnectTimeout.current = setTimeout(() => {
            connect();
          }, delay);
        } else {
          setError('Max reconnection attempts reached');
        }
      });

      ws.current = socket;
    } catch (err) {
      setError(`Connection error: ${err}`);
      setLoading(false);
    }
  }, [token]);

  // Setup and cleanup
  useEffect(() => {
    connect();

    return () => {
      // Cleanup on unmount
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [connect]);

  // Periodically send ping to keep alive
  useEffect(() => {
    if (!isConnected || !ws.current) return;

    const pingInterval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send('ping');
      }
    }, 30000); // Ping every 30s

    return () => clearInterval(pingInterval);
  }, [isConnected]);

  return {
    strategies,
    loading,
    error,
    isConnected,
  };
};
