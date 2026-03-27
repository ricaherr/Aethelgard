import { useState, useEffect, useCallback } from 'react';

export type CheckStatus = 'OK' | 'WARN' | 'FAIL';
export type OverallStatus = 'OK' | 'DEGRADED' | 'CRITICAL' | 'UNAVAILABLE';

export interface OemCheckResult {
  status: CheckStatus;
  detail: string;
}

export interface OemHealth {
  status: OverallStatus;
  message?: string;
  checks: Record<string, OemCheckResult>;
  failing: string[];
  warnings: string[];
  last_checked_at: string | null;
}

const POLL_INTERVAL_MS = 15_000;

/**
 * Polls GET /api/system/health/edge every 15 s.
 * Returns the 9-check OEM health summary for display in the diagnostic UI.
 */
export const useOemHealth = () => {
  const [health, setHealth] = useState<OemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/system/health/edge');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: OemHealth = await res.json();
      setHealth(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fetch error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const id = setInterval(fetchHealth, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchHealth]);

  return { health, loading, error };
};
