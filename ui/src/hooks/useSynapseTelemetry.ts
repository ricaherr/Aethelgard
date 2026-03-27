import { useEffect, useRef, useState, useCallback } from 'react';
import { getWsUrl } from '../utils/wsUrl';

/**
 * Unified Telemetry Data from /ws/v3/synapse
 * Fractal V3 Glass Box
 */
export interface SystemHeartbeat {
  cpu_percent: number;
  memory_mb: number;
  broker_latency_ms: number;
  satellites: Array<{
    provider_id: string;
    status: 'CONNECTED' | 'DISCONNECTED' | 'UNKNOWN';
    last_sync_ms: number;
    is_primary: boolean;
  }>;
  timestamp: string;
  error?: string;
}

export interface ActiveScanners {
  assets: string[];
  status: 'SCANNING' | 'IDLE' | 'UNKNOWN';
  cpu_limit_exceeded: boolean;
  cpu_percent: number;
  scan_frequency_hz: number;
  timestamp: string;
  error?: string;
}

export interface StrategyMetric {
  strategy_id: string;
  status: 'LIVE' | 'QUARANTINE' | 'SHADOW' | 'UNKNOWN';
  dd_pct: number;
  consecutive_losses: number;
  win_rate: number;
  profit_factor: number;
  blocked_for_trading: boolean;
  updated_at: string;
}

export interface RiskBuffer {
  total_units_r: number;
  available_units_r: number;
  exposure_pct: number;
  risk_mode: 'NORMAL' | 'DEFENSIVE' | 'AGGRESSIVE' | 'UNKNOWN';
  timestamp: string;
  error?: string;
}

export interface AnomalyEvent {
  anomaly_id: string;
  type: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  message: string;
  timestamp: string;
}

export interface SynapseTelemetry {
  trace_id: string;
  timestamp: string;
  tenant_id: string;
  system_heartbeat: SystemHeartbeat;
  active_scanners: ActiveScanners;
  strategy_array: StrategyMetric[];
  risk_buffer: RiskBuffer;
  anomalies: {
    latest: AnomalyEvent[];
    count_last_5m: number;
    timestamp: string;
    error?: string;
  };
}

export interface UseSynapseTelemetryHook {
  telemetry: SynapseTelemetry | null;
  loading: boolean;
  error: string | null;
  isConnected: boolean;
  lastUpdate: string | null;
}

/**
 * Custom hook for unified system telemetry via /ws/v3/synapse WebSocket.
 * RULE T1: Automatic tenant isolation via token in WebSocket URL.
 * Performance: 60 FPS target, <10% CPU
 * 
 * Usage:
 * const { telemetry, loading, error, isConnected } = useSynapseTelemetry(token);
 */
export const useSynapseTelemetry = (token?: string): UseSynapseTelemetryHook => {
  const [telemetry, setTelemetry] = useState<SynapseTelemetry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = useRef(1000); // Start at 1s, exponential backoff
  const messageQueue = useRef<SynapseTelemetry[]>([]);
  const lastFrameTime = useRef<number>(0);
  const targetFPS = 60;
  const frameInterval = 1000 / targetFPS;

  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (ws.current?.readyState === WebSocket.OPEN || 
        ws.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    // Clear any pending reconnection
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
    }

    // Determine WS URL
    // NOTE: Browser auto-attaches HttpOnly cookies via WebSocket handshake.
    // Server reads token from cookies instead of query params.
    const wsUrl = getWsUrl('/ws/v3/synapse');

    try {
      console.log("[SYNAPSE] Connecting to", wsUrl);
      ws.current = new WebSocket(wsUrl);
      
      ws.current.onopen = () => {
        console.log("[SYNAPSE] WebSocket connected");
        setIsConnected(true);
        setError(null);
        setLoading(false);  // ← CRITICAL: Mark loading as complete when connected
        reconnectAttempts.current = 0;
        reconnectDelay.current = 1000;
        lastFrameTime.current = 0;
        messageQueue.current = [];
      };

      ws.current.onmessage = (event) => {
        try {
          const raw = JSON.parse(event.data);

          // Discard server-side error/ping messages that lack telemetry shape
          if (!raw || typeof raw !== 'object' || raw.type === 'error' || raw.type === 'pong' || !raw.system_heartbeat) {
            if (raw?.type === 'error') {
              console.warn("[SYNAPSE] Server error message:", raw.message);
            }
            return;
          }

          const data = raw as SynapseTelemetry;

          // Performance optimization: throttle updates to target FPS
          const now = performance.now();
          const timeSinceLastFrame = now - lastFrameTime.current;
          
          if (timeSinceLastFrame >= frameInterval) {
            // Enough time has passed - render immediately
            setTelemetry(data);
            setLastUpdate(new Date().toISOString());
            lastFrameTime.current = now;
            messageQueue.current = []; // Clear queue after rendering
          } else {
            // Queue this message for next frame
            messageQueue.current.push(data);
          }
          
          // If queue is full, render the latest
          if (messageQueue.current.length > 2) {
            const latest = messageQueue.current[messageQueue.current.length - 1];
            setTelemetry(latest);
            setLastUpdate(new Date().toISOString());
            lastFrameTime.current = now;
            messageQueue.current = [];
          }
        } catch (parseError) {
          console.error("[SYNAPSE] Message parse error:", parseError);
        }
      };

      ws.current.onerror = (event) => {
        console.error("[SYNAPSE] WebSocket error:", event);
        setError("WebSocket connection error");
        setIsConnected(false);
      };

      ws.current.onclose = () => {
        console.warn("[SYNAPSE] WebSocket closed");
        setIsConnected(false);
        
        // Attempt to reconnect with exponential backoff
        if (reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current++;
          const delay = Math.min(reconnectDelay.current * Math.pow(2, reconnectAttempts.current - 1), 30000);
          console.log(`[SYNAPSE] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current}/${maxReconnectAttempts})`);
          
          reconnectTimeout.current = setTimeout(() => {
            connect();
          }, delay);
        } else {
          setError("Max reconnection attempts exceeded");
        }
      };
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Unknown error during connection";
      setError(errorMsg);
      setLoading(false);
    }
  }, []);  // No dependencies - connect works without props

  useEffect(() => {
    // AUTO-CONNECT: Connect when component mounts (no token required)
    // Browser will auto-send HttpOnly cookies in WebSocket handshake
    // Server reads token from cookies, not from JS
    connect();

    // Cleanup on unmount
    return () => {
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [connect]);

  // Periodic keepalive ping
  useEffect(() => {
    if (!isConnected || !ws.current) return;

    const pingInterval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        try {
          ws.current.send('ping');
        } catch (err) {
          console.warn("[SYNAPSE] Ping error (will reconnect):", err);
        }
      }
    }, 30000); // Ping every 30 seconds

    return () => clearInterval(pingInterval);
  }, [isConnected]);

  return {
    telemetry,
    loading,
    error,
    isConnected,
    lastUpdate
  };
};
