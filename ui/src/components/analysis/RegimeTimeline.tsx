
import React, { useEffect, useState } from 'react';
import { GlassPanel } from '../common/GlassPanel';
import { TrendingUp, TrendingDown, PauseCircle } from 'lucide-react';

interface RegimeTimelineProps {
  symbol: string;
}

const regimeColor = (regime: string) => {
  if (regime === 'BULLISH' || regime === 'TREND') return 'bg-aethelgard-green/80 text-white';
  if (regime === 'BEARISH' || regime === 'CRASH') return 'bg-red-600/80 text-white';
  if (regime === 'RANGE') return 'bg-yellow-500/80 text-black';
  return 'bg-gray-700/80 text-white';
};

const regimeIcon = (regime: string) => {
  if (regime === 'BULLISH' || regime === 'TREND') return <TrendingUp size={14} className="inline-block mr-1" />;
  if (regime === 'BEARISH' || regime === 'CRASH') return <TrendingDown size={14} className="inline-block mr-1" />;
  if (regime === 'RANGE') return <PauseCircle size={14} className="inline-block mr-1" />;
  return null;
};

const RegimeTimeline: React.FC<RegimeTimelineProps> = ({ symbol }) => {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = () => {
    setLoading(true);
    setError(null);
    fetch(`/api/regime/${symbol}/history`)
      .then(res => {
        if (!res.ok) throw new Error('Error al obtener régimen');
        return res.json();
      })
      .then(data => setHistory(Array.isArray(data.history) ? data.history : []))
      .catch(err => {
        setError('No se pudo cargar el historial de régimen. Intenta nuevamente.');
        console.error('[RegimeTimeline] Error:', err);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchHistory();
    // eslint-disable-next-line
  }, [symbol]);

  return (
    <GlassPanel className="w-full h-full flex flex-col gap-4">
      <div className="flex items-center gap-3 mb-2">
        <PauseCircle className="text-yellow-400" size={22} />
        <h2 className="font-bold text-lg">Régimen de Mercado</h2>
      </div>
      {loading && <div className="text-white/60">Cargando régimen...</div>}
      {error && (
        <div className="bg-red-900/60 text-red-200 p-2 rounded flex items-center gap-2">
          <PauseCircle size={18} /> {error}
          <button className="ml-auto px-2 py-1 bg-red-700/40 rounded text-xs" onClick={fetchHistory}>Reintentar</button>
        </div>
      )}
      {!loading && !error && history.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-row items-center gap-2 overflow-x-auto pb-2 flex-wrap">
            {history.slice(-12).map((reg, idx) => (
              <span key={idx} className={`flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold uppercase whitespace-nowrap ${regimeColor(reg.regime)}`} title={reg.timestamp}>
                {regimeIcon(reg.regime)}
                {reg.regime}
                <span className="ml-1 text-[10px] text-white/40">{new Date(reg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              </span>
            ))}
          </div>
        </div>
      )}
      {!loading && history.length === 0 && (
        <div className="text-xs text-white/40">No hay historial de régimen disponible.</div>
      )}
    </GlassPanel>
  );
};

export default RegimeTimeline;
