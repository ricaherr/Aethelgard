/**
 * Widget "Coherence Health Meter"
 * 
 * Medidor de Fidelidad del Modelo: Compara rendimiento teórico (Shadow) 
 * vs ejecución real (Live). Detecta en milisegundos si el modelo está "roto".
 * 
 * HU 6.3: Coherence Drift Monitoring
 * Trace_ID: COHERENCE-DRIFT-2026-001
 */

import React, { useState, useEffect } from 'react';

interface CoherenceMetrics {
  coherence_score: number;      // 0.0 - 1.0 (as percentage: 0-100%)
  status: 'COHERENT' | 'MONITORING' | 'INCOHERENT' | 'INSUFFICIENT_DATA' | 'ERROR';
  veto_new_entries: boolean;
  theoretical_sharpe: number;
  real_sharpe: number;
  performance_degradation: number;  // 0.0 - 1.0
  executions_analyzed: number;
  theoretical_latency_ms: number;
  real_latency_ms: number;
  recovery_trend?: boolean;
  reason: string;
  timestamp: string;
  trace_id: string;
}

interface CoherenceMeterProps {
  symbol?: string;
  apiUrl?: string;
  refreshInterval?: number; // ms
  onVetoChange?: (vetoed: boolean, reason: string | null) => void;
}

const CoherenceMeter: React.FC<CoherenceMeterProps> = ({
  symbol = 'EURUSD',
  apiUrl = '/api/coherence',
  refreshInterval = 10000,
  onVetoChange,
}) => {
  const [metrics, setMetrics] = useState<CoherenceMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [history, setHistory] = useState<CoherenceMetrics[]>([]);

  // Fetch coherence metrics from backend
  const fetchMetrics = async () => {
    try {
      const response = await fetch(`${apiUrl}/detect-drift?symbol=${symbol}`);
      if (!response.ok) throw new Error('Failed to fetch coherence metrics');
      
      const data: CoherenceMetrics = await response.json();
      setMetrics(data);
      setHistory(prev => [...prev.slice(-9), data]); // Keep last 10 for sparkline
      setLoading(false);
      setError(null);
      setLastUpdate(new Date());

      // Notify parent of veto status
      if (onVetoChange) {
        onVetoChange(data.veto_new_entries, data.reason || null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, refreshInterval);
    return () => clearInterval(interval);
  }, [symbol, refreshInterval, apiUrl]);

  // Get color based on coherence score
  const getScoreColor = (score: number): string => {
    if (score >= 0.95) return '#10B981'; // Emerald green - perfect
    if (score >= 0.90) return '#3B82F6'; // Blue - very good
    if (score >= 0.80) return '#F59E0B'; // Amber - acceptable
    if (score >= 0.70) return '#EF4444'; // Red - degraded
    return '#7F1D1D'; // Dark red - critical
  };

  // Get status label and color
  const getStatusBadge = (status: string): { label: string; bg: string; text: string } => {
    const badges: Record<string, { label: string; bg: string; text: string }> = {
      COHERENT: { label: '✓ COHERENT', bg: 'bg-green-100', text: 'text-green-800' },
      MONITORING: { label: '⚠ MONITORING', bg: 'bg-yellow-100', text: 'text-yellow-800' },
      INCOHERENT: { label: '✗ INCOHERENT', bg: 'bg-red-100', text: 'text-red-800' },
      INSUFFICIENT_DATA: { label: '? COLLECTING', bg: 'bg-gray-100', text: 'text-gray-800' },
      ERROR: { label: '⛔ ERROR', bg: 'bg-red-100', text: 'text-red-800' },
    };
    return badges[status] || badges.INSUFFICIENT_DATA;
  };

  if (loading && !metrics) {
    return (
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 w-full">
        <div className="text-center text-gray-400">
          <div className="animate-spin inline-block">⟳</div> Loading coherence metrics...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900 border border-red-700 rounded-lg p-4 w-full">
        <div className="text-red-200">
          <strong>Coherence Service Error:</strong> {error}
        </div>
      </div>
    );
  }

  if (!metrics) {
    return (
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 w-full">
        <div className="text-gray-400">No coherence data available</div>
      </div>
    );
  }

  const scorePercent = metrics.coherence_score * 100;
  const degradationPercent = metrics.performance_degradation * 100;
  const badge = getStatusBadge(metrics.status);
  const scoreColor = getScoreColor(metrics.coherence_score);

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 w-full">
      {/* Header: Title & Status */}
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-lg font-bold text-white">
          🔬 Model Coherence Health — {symbol}
        </h3>
        <div className={`px-3 py-1 rounded text-sm font-semibold ${badge.bg} ${badge.text}`}>
          {badge.label}
        </div>
      </div>

      {/* Coherence Score - Large Radial Gauge */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex-1">
          {/* Circular Progress */}
          <svg width="120" height="120" className="mx-auto">
            {/* Background circle */}
            <circle cx="60" cy="60" r="55" fill="none" stroke="#374151" strokeWidth="8" />
            
            {/* Progress circle */}
            <circle
              cx="60"
              cy="60"
              r="55"
              fill="none"
              stroke={scoreColor}
              strokeWidth="8"
              strokeDasharray={`${2 * Math.PI * 55}`}
              strokeDashoffset={`${2 * Math.PI * 55 * (1 - metrics.coherence_score)}`}
              strokeLinecap="round"
              style={{ transition: 'stroke-dashoffset 0.3s ease' }}
            />
            
            {/* Center text */}
            <text
              x="60"
              y="60"
              textAnchor="middle"
              dy="0.3em"
              fontSize="24"
              fontWeight="bold"
              fill={scoreColor}
            >
              {scorePercent.toFixed(0)}%
            </text>
          </svg>
        </div>

        {/* Right side: Metrics */}
        <div className="flex-1 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">Theoretical Sharpe:</span>
            <span className="text-blue-400 font-mono">{metrics.theoretical_sharpe.toFixed(3)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Real Sharpe:</span>
            <span className={metrics.real_sharpe >= metrics.theoretical_sharpe * 0.85 ? 'text-green-400' : 'text-red-400'} style={{ fontFamily: 'monospace' }}>
              {metrics.real_sharpe.toFixed(3)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Degradation:</span>
            <span className={degradationPercent > 15 ? 'text-orange-400 font-semibold' : 'text-yellow-400'} style={{ fontFamily: 'monospace' }}>
              {degradationPercent.toFixed(1)}%
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Executions:</span>
            <span className="text-gray-300" style={{ fontFamily: 'monospace' }}>
              {metrics.executions_analyzed}
            </span>
          </div>
        </div>
      </div>

      {/* Latency Comparison */}
      <div className="bg-gray-800 rounded p-3 mb-3">
        <div className="flex justify-between items-center mb-2">
          <span className="text-xs font-semibold text-gray-400">LATENCY PROFILE</span>
          <span className="text-xs text-gray-500">
            Target: {metrics.theoretical_latency_ms.toFixed(1)}ms | Observed: {metrics.real_latency_ms.toFixed(1)}ms
          </span>
        </div>
        {/* Latency bar */}
        <div className="bg-gray-700 rounded h-2">
          <div
            className="bg-cyan-500 h-2 rounded"
            style={{
              width: `${Math.min(100, (metrics.real_latency_ms / 50) * 100)}%`,
              transition: 'width 0.3s ease',
            }}
          />
        </div>
      </div>

      {/* Divergence Alert */}
      {metrics.veto_new_entries && (
        <div className="bg-red-900 border border-red-700 rounded-lg p-3 mb-3">
          <div className="text-red-200 font-semibold text-sm">
            ⛔ VETO: New entries blocked
          </div>
          <div className="text-red-300 text-xs mt-1">
            {metrics.reason}
          </div>
        </div>
      )}

      {/* Recovery Trend */}
      {metrics.recovery_trend && (
        <div className="bg-green-900 border border-green-700 rounded-lg p-3 mb-3">
          <div className="text-green-200 font-semibold text-sm">
            ↗ RECOVERY TREND DETECTED
          </div>
          <div className="text-green-300 text-xs mt-1">
            System recovering from drift period. Metrics improving.
          </div>
        </div>
      )}

      {/* Status Message */}
      <div className="bg-gray-800 rounded p-2 mb-3">
        <div className="text-gray-300 text-xs">
          <div><strong>Status:</strong> {metrics.status}</div>
          <div><strong>Reason:</strong> {metrics.reason}</div>
        </div>
      </div>

      {/* History Sparkline (last 10 readings) */}
      {history.length > 1 && (
        <div className="bg-gray-800 rounded p-2">
          <div className="text-xs font-semibold text-gray-400 mb-1">COHERENCE TREND (Last 10)</div>
          <svg width="100%" height="30" className="max-w-full">
            {history.map((h, i) => {
              const x = (i / (history.length - 1)) * 100;
              const y = 30 - h.coherence_score * 25;
              const color = h.veto_new_entries ? '#EF4444' : h.coherence_score >= 0.8 ? '#10B981' : '#F59E0B';
              return (
                <circle
                  key={i}
                  cx={`${x}%`}
                  cy={y}
                  r="2"
                  fill={color}
                />
              );
            })}
          </svg>
        </div>
      )}

      {/* Footer: Last Update */}
      <div className="text-xs text-gray-500 mt-3 text-right">
        Updated: {lastUpdate.toLocaleTimeString()} | Trace: {metrics.trace_id}
      </div>
    </div>
  );
};

export default CoherenceMeter;
