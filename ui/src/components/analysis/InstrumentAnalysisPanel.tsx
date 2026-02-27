import React, { useEffect, useState, useCallback } from 'react';
import { GlassPanel } from '../common/GlassPanel';
import { Zap, TrendingUp, TrendingDown, BarChart2, CheckCircle, AlertCircle } from 'lucide-react';
import { useApi } from '../../hooks/useApi';

interface InstrumentAnalysisPanelProps {
  symbol: string;
}

const badgeColor = (trend: string) => {
  if (trend === 'BULLISH') return 'bg-green-600/80 text-white';
  if (trend === 'BEARISH') return 'bg-red-600/80 text-white';
  if (trend === 'RANGE') return 'bg-yellow-500/80 text-black';
  return 'bg-gray-700/80 text-white';
};

const InstrumentAnalysisPanel: React.FC<InstrumentAnalysisPanelProps> = ({ symbol }) => {
  const { apiFetch } = useApi();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalysis = useCallback(() => {
    setLoading(true);
    setError(null);
    apiFetch(`/api/instrument/${symbol}/analysis`)
      .then(res => {
        if (!res.ok) throw new Error('Error al obtener análisis');
        return res.json();
      })
      .then(setData)
      .catch(err => {
        setError('No se pudo cargar el análisis. Intenta nuevamente.');
        // Reporte para admins (puede ser log, Sentry, etc.)
        console.error('[InstrumentAnalysisPanel] Error:', err);
      })
      .finally(() => setLoading(false));
  }, [apiFetch, symbol]);

  useEffect(() => {
    fetchAnalysis();
    // eslint-disable-next-line
  }, [fetchAnalysis]);

  return (
    <GlassPanel className="w-full h-full flex flex-col gap-4">
      <div className="flex items-center gap-3 mb-2">
        <BarChart2 className="text-aethelgard-green" size={22} />
        <h2 className="font-bold text-lg">Análisis del Instrumento</h2>
        {(data?.regime?.current || data?.trend) && (
          <span className={`ml-2 px-3 py-1 rounded-full text-xs font-bold uppercase ${badgeColor(data?.regime?.current || data?.trend)}`}>
            {data?.regime?.current || data?.trend}
          </span>
        )}
      </div>
      {loading && <div className="text-white/60">Cargando análisis...</div>}
      {error && (
        <div className="bg-red-900/60 text-red-200 p-2 rounded flex items-center gap-2">
          <AlertCircle size={18} /> {error}
          <button className="ml-auto px-2 py-1 bg-red-700/40 rounded text-xs" onClick={fetchAnalysis}>Reintentar</button>
        </div>
      )}
      {!loading && !error && data && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-white/60">Fuerza de tendencia:</span>
            <span className="font-mono text-base text-aethelgard-green">
              {typeof data.trend?.strength === 'number'
                ? data.trend.strength.toFixed(2)
                : data.trend_strength && typeof data.trend_strength === 'number'
                  ? data.trend_strength.toFixed(2)
                  : 'N/A'}
            </span>
            {((data.trend?.strength !== undefined && typeof data.trend.strength === 'number') ||
              (data.trend_strength !== undefined && typeof data.trend_strength === 'number')) && (
                <div className="w-32 h-2 bg-white/10 rounded-full overflow-hidden min-w-[100px]">
                  <div
                    className="h-2 bg-aethelgard-green"
                    style={{
                      width: `${Math.min(100, Math.abs(
                        (data.trend?.strength ?? data.trend_strength ?? 0) * 100
                      ))}%`
                    }}
                  />
                </div>
              )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Zap size={16} className="text-yellow-400 shrink-0" />
            <span className="text-sm text-white/60">ADX:</span>
            <span className="font-mono text-base">
              {typeof data.regime?.adx === 'number'
                ? data.regime.adx.toFixed(2)
                : typeof data.adx === 'number'
                  ? data.adx.toFixed(2)
                  : 'N/A'}
            </span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-white/60 shrink-0">Estrategias sugeridas:</span>
            {data.applicable_strategies?.length > 0 || data.strategies?.length > 0 ? (
              (data.applicable_strategies || data.strategies || []).map((s: any, idx: number) => (
                <span key={idx} className="px-2 py-1 bg-aethelgard-blue/20 rounded text-xs font-semibold text-aethelgard-blue border border-aethelgard-blue/30 mr-1 mb-1 whitespace-nowrap">
                  {typeof s === 'string' ? s : s.name || s.description || 'Strategy'}
                </span>
              ))
            ) : (
              <span className="text-xs text-white/40">Ninguna</span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-white/60 shrink-0">Señales activas:</span>
            {data.signals?.length > 0 ? (
              data.signals.map((sig: any, idx: number) => (
                <span key={idx} className="flex items-center gap-1 px-2 py-1 bg-aethelgard-green/20 rounded text-xs font-semibold text-aethelgard-green border border-aethelgard-green/30 mr-1 mb-1 whitespace-nowrap">
                  <CheckCircle size={12} className="shrink-0" /> {typeof sig === 'string' ? sig : sig.symbol || 'Signal'}
                </span>
              ))
            ) : (
              <span className="text-xs text-white/40">Ninguna</span>
            )}
          </div>
        </div>
      )}
    </GlassPanel>
  );
};

export default InstrumentAnalysisPanel;
