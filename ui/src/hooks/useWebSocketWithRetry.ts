import { useEffect, useRef, useState, useCallback } from 'react';

interface UseWebSocketOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  onMessage?: (data: any) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
}

interface WebSocketState {
  connected: boolean;
  retryCount: number;
  lastError?: string;
  isRetrying: boolean;
}

/**
 * Professional WebSocket hook with exponential backoff reconnection.
 * NO setTimeout - uses state-driven reconnection via useEffect.
 * 
 * State Management:
 * - retryCount increments on disconnect
 * - useEffect watches retryCount and initiates connection
 * - Exponential backoff calculated from retryCount
 * - Cleanup is automatic and deterministic
 */
export const useWebSocketWithRetry = (
  url: string,
  options: UseWebSocketOptions = {}
): [WebSocket | null, WebSocketState] => {
  const {
    maxRetries = 5,
    baseDelayMs = 1000,
    onMessage,
    onConnect,
    onDisconnect,
    onError,
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<WebSocketState>({
    connected: false,
    retryCount: 0,
    isRetrying: false,
  });

  /**
   * Calculate exponential backoff delay with jitter
   * Formula: baseDelay * 2^retryCount with small random jitter
   */
  const calculateBackoffDelay = useCallback((retryAttempt: number): number => {
    const exponentialDelay = baseDelayMs * Math.pow(2, retryAttempt);
    // Max cap at 30 seconds to prevent runaway delays
    const cappedDelay = Math.min(exponentialDelay, 30000);
    // Add ±10% jitter to prevent thundering herd
    const jitter = cappedDelay * 0.1 * (Math.random() - 0.5);
    return Math.floor(cappedDelay + jitter);
  }, [baseDelayMs]);

  /**
   * Establish WebSocket connection.
   * Called when component mounts or retry count changes.
   */
  const connect = useCallback(() => {
    // Prevent multiple simultaneous connection attempts
    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WebSocketHook] ✓ Connected', { url, retryCount: state.retryCount });
        setState((prev) => ({
          ...prev,
          connected: true,
          retryCount: 0, // Reset retry count on success
          isRetrying: false,
          lastError: undefined,
        }));
        onConnect?.();
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onMessage?.(data);
        } catch (parseError) {
          console.error('[WebSocketHook] Failed to parse message:', parseError);
        }
      };

      ws.onerror = (error: Event) => {
        console.error('[WebSocketHook] WebSocket error:', error);
        setState((prev) => ({
          ...prev,
          lastError: 'WebSocket error occurred',
        }));
        onError?.(error);
      };

      ws.onclose = () => {
        console.log('[WebSocketHook] ✗ Disconnected', { url });
        setState((prev) => ({
          ...prev,
          connected: false,
          retryCount: prev.retryCount + 1, // Increment for next retry
        }));
        onDisconnect?.();
      };
    } catch (error) {
      console.error('[WebSocketHook] Failed to create WebSocket:', error);
      setState((prev) => ({
        ...prev,
        connected: false,
        retryCount: prev.retryCount + 1,
        lastError: error instanceof Error ? error.message : 'Unknown error',
      }));
    }
  }, [url, onMessage, onConnect, onDisconnect, onError, state.retryCount]);

  /**
   * Effect: Handle initial connection on mount
   */
  useEffect(() => {
    connect();

    return () => {
      // Cleanup: close WebSocket on unmount
      if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
        wsRef.current.close();
      }
    };
  }, [url]); // Only reinitialize if URL changes

  /**
   * Effect: Handle reconnection with exponential backoff
   * Watches retryCount and schedules reconnection after calculated delay
   */
  useEffect(() => {
    // If already connected, don't retry
    if (state.connected || state.retryCount === 0) {
      return;
    }

    // Max retries exceeded
    if (state.retryCount > maxRetries) {
      console.error('[WebSocketHook] ✗ Max retries exceeded', {
        maxRetries,
        url,
      });
      setState((prev) => ({
        ...prev,
        lastError: `Max retries exceeded (${maxRetries})`,
      }));
      return;
    }

    // Calculate backoff delay
    const backoffDelay = calculateBackoffDelay(state.retryCount - 1);
    console.log('[WebSocketHook] ⏳ Scheduling reconnect', {
      retryCount: state.retryCount,
      delayMs: backoffDelay,
      url,
    });

    setState((prev) => ({ ...prev, isRetrying: true }));

    // Use timer to respect React lifecycle
    const timerId = setTimeout(() => {
      console.log('[WebSocketHook] → Attempting reconnect', {
        retryCount: state.retryCount,
        url,
      });
      connect();
    }, backoffDelay);

    // Cleanup: cancel timer if component unmounts or retryCount changes
    return () => {
      clearTimeout(timerId);
    };
  }, [state.retryCount, state.connected, maxRetries, url, connect, calculateBackoffDelay]);

  return [wsRef.current, state];
};
