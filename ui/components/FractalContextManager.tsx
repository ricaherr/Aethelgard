/**
 * Widget "Fractal Context Manager"
 * 
 * Visualización de "Alineación de Engranajes" para mostrar sincronización 
 * multi-temporal (M15, H1, H4).
 * 
 * HU 2.1: Autos para el Ejecutor - Temporal Unification Engine
 */

import React, { useState, useEffect } from 'react';

interface FractalMetrics {
  m15_regime: string;
  h1_regime: string;
  h4_regime: string;
  is_aligned: boolean;
  alignment_score: number;
  veto_signal: string | null;
  confidence_threshold: number;
  timestamp: string;
  m15_metrics?: Record<string, any>;
  h1_metrics?: Record<string, any>;
  h4_metrics?: Record<string, any>;
}

interface FractalContextManagerProps {
  apiUrl?: string;
  refreshInterval?: number; // ms
  onVetoChange?: (vetoed: boolean, reason: string | null) => void;
}

const FractalContextManager: React.FC<FractalContextManagerProps> = ({
  apiUrl = '/api/regime',
  refreshInterval = 5000,
  onVetoChange,
}) => {
  const [metrics, setMetrics] = useState<FractalMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  // Fetch alignment metrics from backend
  const fetchMetrics = async () => {
    try {
      const response = await fetch(`${apiUrl}/alignment-metrics`);
      if (!response.ok) throw new Error('Failed to fetch metrics');
      
      const data: FractalMetrics = await response.json();
      setMetrics(data);
      setLoading(false);
      setError(null);
      setLastUpdate(new Date());

      // Notify parent of veto status
      if (onVetoChange) {
        // Type-safe boolean check: veto_signal must be non-null AND in veto list
        const isVetoed: boolean = data.veto_signal !== null && 
          ['RETRACEMENT_RISK', 'CATASTROPHIC_CONFLICT', 'VOLATILITY_TRAP'].includes(data.veto_signal);
        onVetoChange(isVetoed, data.veto_signal || null);
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
  }, [refreshInterval, apiUrl]);

  // Render regime badge with color
  const renderRegimeBadge = (regime: string | undefined) => {
    if (!regime) return null;
    
    const regimeColors: Record<string, string> = {
      TREND: 'bg-blue-500',
      RANGE: 'bg-yellow-500',
      VOLATILE: 'bg-orange-500',
      SHOCK: 'bg-red-600',
      BULL: 'bg-green-500',
      BEAR: 'bg-red-500',
      CRASH: 'bg-black',
      NORMAL: 'bg-gray-400',
    };

    return (
      <span className={`px-3 py-1 rounded text-white text-sm font-semibold ${regimeColors[regime] || 'bg-gray-400'}`}>
        {regime}
      </span>
    );
  };

  // Render veto badge
  const renderVetoBadge = (veto: string | null | undefined) => {
    if (!veto) return null;

    const vetoColors: Record<string, string> = {
      RETRACEMENT_RISK: 'bg-orange-600 text-white',
      CATASTROPHIC_CONFLICT: 'bg-red-700 text-white',
      VOLATILITY_TRAP: 'bg-red-500 text-white',
      ALIGNED: 'bg-green-500 text-white',
      PARTIAL_CONFLICT: 'bg-yellow-600 text-white',
    };

    return (
      <div className={`px-4 py-2 rounded font-bold ${vetoColors[veto] || 'bg-gray-400'}`}>
        🚨 {veto}
      </div>
    );
  };

  if (loading) {
    return <div className="p-4 bg-gray-200 rounded">Cargando contexto fractal...</div>;
  }

  if (error) {
    return <div className="p-4 bg-red-200 rounded">Error: {error}</div>;
  }

  if (!metrics) {
    return <div className="p-4 bg-gray-200 rounded">Sin datos disponibles</div>;
  }

  return (
    <div className="p-6 bg-white rounded-lg shadow-lg border border-gray-300">
      <h2 className="text-2xl font-bold mb-4 text-gray-800">
        ⚙️ Alineación de Engranajes (Fractal Context)
      </h2>

      {/* Veto Alert */}
      {metrics.veto_signal && metrics.veto_signal !== 'ALIGNED' && (
        <div className="mb-4">
          {renderVetoBadge(metrics.veto_signal)}
          <p className="text-sm text-gray-600 mt-2">
            Confianza elevada a <strong>{(metrics.confidence_threshold * 100).toFixed(0)}%</strong>
          </p>
        </div>
      )}

      {/* Alignment Status */}
      <div className="mb-6 p-4 bg-blue-50 rounded border border-blue-300">
        <div className="flex items-center justify-between mb-3">
          <span className="font-semibold text-gray-700">Estado de Sincronización:</span>
          <span className={`text-lg font-bold ${metrics.is_aligned ? 'text-green-600' : 'text-orange-600'}`}>
            {metrics.is_aligned ? '✅ SINCRONIZADAS' : '⚠️ EN CONFLICTO'}
          </span>
        </div>
        <div className="w-full bg-gray-300 rounded h-4">
          <div
            className={`h-4 rounded ${metrics.is_aligned ? 'bg-green-500' : 'bg-orange-500'}`}
            style={{ width: `${metrics.alignment_score * 100}%` }}
          ></div>
        </div>
        <p className="text-sm text-gray-600 mt-2">
          Alineación: {(metrics.alignment_score * 100).toFixed(0)}%
        </p>
      </div>

      {/* Timeframe Regimes */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {/* M15 */}
        <div className="p-4 bg-gray-50 rounded border">
          <h3 className="font-bold text-gray-700 mb-3">📊 M15 (15min)</h3>
          {renderRegimeBadge(metrics.m15_regime)}
          {metrics.m15_metrics && (
            <div className="text-xs text-gray-600 mt-2">
              <p>ADX: {(metrics.m15_metrics.adx || 0).toFixed(2)}</p>
              <p>Bias: {metrics.m15_metrics.bias || 'N/A'}</p>
            </div>
          )}
        </div>

        {/* H1 */}
        <div className="p-4 bg-gray-50 rounded border">
          <h3 className="font-bold text-gray-700 mb-3">📊 H1 (1h)</h3>
          {renderRegimeBadge(metrics.h1_regime)}
          {metrics.h1_metrics && (
            <div className="text-xs text-gray-600 mt-2">
              <p>ADX: {(metrics.h1_metrics.adx || 0).toFixed(2)}</p>
              <p>Bias: {metrics.h1_metrics.bias || 'N/A'}</p>
            </div>
          )}
        </div>

        {/* H4 */}
        <div className="p-4 bg-gray-50 rounded border">
          <h3 className="font-bold text-gray-700 mb-3">📊 H4 (4h)</h3>
          {renderRegimeBadge(metrics.h4_regime)}
          {metrics.h4_metrics && (
            <div className="text-xs text-gray-600 mt-2">
              <p>ADX: {(metrics.h4_metrics.adx || 0).toFixed(2)}</p>
              <p>Bias: {metrics.h4_metrics.bias || 'N/A'}</p>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="text-xs text-gray-500 border-t pt-3">
        <p>Última actualización: {lastUpdate.toLocaleTimeString('es-ES')}</p>
        <p>Trace ID: {metrics.timestamp}</p>
      </div>
    </div>
  );
};

export default FractalContextManager;
