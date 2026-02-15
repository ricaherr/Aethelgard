
import React, { useEffect, useState } from 'react';
import { GlassPanel } from '../common/GlassPanel';
import { Activity, Clock, CheckCircle, AlertTriangle } from 'lucide-react';

const badgeColor = (state: string) => {
  if (state === 'RUNNING') return 'bg-aethelgard-green/80 text-white';
  if (state === 'IDLE') return 'bg-gray-500/80 text-white';
  if (state === 'ERROR') return 'bg-red-600/80 text-white';
  return 'bg-yellow-500/80 text-black';
};

const ScannerStatusMonitor: React.FC = () => {
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = () => {
    setLoading(true);
    setError(null);
    fetch('/api/scanner/status')
      .then(res => {
        if (!res.ok) throw new Error('Error al obtener estado del scanner');
        return res.json();
      })
      .then(setStatus)
      .catch(err => {
        setError('No se pudo cargar el estado del scanner. Intenta nuevamente.');
        console.error('[ScannerStatusMonitor] Error:', err);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  return (
    <GlassPanel className="w-full h-full flex flex-col gap-4">
      <div className="flex items-center gap-3 mb-2">
        <Activity className="text-aethelgard-blue" size={22} />
        <h2 className="font-bold text-lg">Estado del Scanner</h2>
        {status?.state && (
          <span className={`ml-2 px-3 py-1 rounded-full text-xs font-bold uppercase ${badgeColor(status.state)}`}>
            {status.state}
          </span>
        )}
      </div>
      {loading && <div className="text-white/60">Cargando estado del scanner...</div>}
      {error && (
        <div className="bg-red-900/60 text-red-200 p-2 rounded flex items-center gap-2">
          <AlertTriangle size={18} /> {error}
          <button className="ml-auto px-2 py-1 bg-red-700/40 rounded text-xs" onClick={fetchStatus}>Reintentar</button>
        </div>
      )}
      {!loading && !error && status && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-white/60">Último escaneo:</span>
            <span className="font-mono text-base text-aethelgard-blue whitespace-nowrap">{status.last_scan ? new Date(status.last_scan).toLocaleString() : 'N/A'}</span>
            {status.last_result === 'OK' && <CheckCircle size={16} className="text-aethelgard-green shrink-0" />}
            {status.last_result === 'ERROR' && <AlertTriangle size={16} className="text-red-500 shrink-0" />}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-white/60">Próximo escaneo:</span>
            <span className="font-mono text-base text-yellow-400 whitespace-nowrap">{status.next_scan ? new Date(status.next_scan).toLocaleString() : 'N/A'}</span>
            <Clock size={16} className="text-yellow-400 shrink-0" />
          </div>
          {status.upcoming_scans?.length > 0 && (
            <div className="flex flex-col gap-1 mt-2 w-full overflow-hidden">
              <span className="text-xs text-white/40 mb-1">Próximos escaneos programados:</span>
              <ul className="list-disc ml-6 break-all">
                {status.upcoming_scans.map((ts: string, idx: number) => (
                  <li key={idx} className="text-xs text-white/60">{new Date(ts).toLocaleString()}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </GlassPanel>
  );
};

export default ScannerStatusMonitor;
