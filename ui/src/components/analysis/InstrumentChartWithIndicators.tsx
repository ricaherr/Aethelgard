import React, { useEffect, useState } from 'react';
import ChartView from './ChartView';
import { CandlestickData } from 'lightweight-charts';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface InstrumentChartWithIndicatorsProps {
  symbol: string;
  selectedSignal?: any; // Full signal object
}

const InstrumentChartWithIndicators: React.FC<InstrumentChartWithIndicatorsProps> = ({
  symbol,
  selectedSignal
}) => {
  const [chartData, setChartData] = useState<CandlestickData[]>([]);
  // Use signal timeframe or default to M5
  const [timeframe, setTimeframe] = useState<string>(selectedSignal?.timeframe || 'M5');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showOverlay, setShowOverlay] = useState(true);

  // Sync timeframe when selectedSignal changes
  useEffect(() => {
    if (selectedSignal?.timeframe) {
      setTimeframe(selectedSignal.timeframe);
    }
  }, [selectedSignal]);

  // Metadatos adicionales que podrían venir del endpoint
  const [meta, setMeta] = useState<{
    entryPrice?: number;
    stopLoss?: number;
    takeProfit?: number;
    isBuy?: boolean;
  }>({});

  const fetchChart = () => {
    setLoading(true);
    setError(null);
    fetch(`/api/chart/${symbol}/${timeframe}`)
      .then(res => {
        if (!res.ok) throw new Error('Error al obtener gráfica');
        return res.json();
      })
      .then(data => {
        if (Array.isArray(data)) {
          setChartData(data);
        } else if (data.candles) {
          setChartData(data.candles);
          setMeta({
            entryPrice: data.entryPrice,
            stopLoss: data.stopLoss,
            takeProfit: data.takeProfit,
            isBuy: data.isBuy
          });
        } else {
          setChartData([]);
        }
      })
      .catch(err => {
        const errorMsg = err.message === '404'
          ? 'Instrumento no soportado por el broker actual.'
          : 'No se pudo cargar la gráfica. Verifica la conexión.';
        setError(errorMsg);
        console.error('[InstrumentChartWithIndicators] Error:', err);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchChart();
    // eslint-disable-next-line
  }, [symbol, timeframe]);

  return (
    <div className="absolute inset-0 flex flex-col bg-gray-900/50 rounded-none xl:rounded-lg border-x border-gray-800 overflow-hidden">

      {/* Signal Info Overlay - Bottom Left */}
      {selectedSignal && (
        <div className="absolute bottom-16 left-4 z-20 max-w-xs">
          {/* Collapsed State (Mini Badge) */}
          <div className={`transition-all duration-300 ${!showOverlay ? 'opacity-100' : 'opacity-0 pointer-events-none absolute'}`}>
            <button
              onClick={() => setShowOverlay(true)}
              className="bg-gray-800/90 backdrop-blur border border-gray-700 rounded-lg px-3 py-1.5 flex items-center gap-2 shadow-lg hover:bg-gray-700 transition-colors"
            >
              <span className={`w-2 h-2 rounded-full ${selectedSignal.direction === 'BUY' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
              <span className="text-xs font-bold text-white uppercase">{selectedSignal.symbol}</span>
              <ChevronDown className="w-3 h-3 text-gray-400" />
            </button>
          </div>

          {/* Expanded State */}
          <div className={`bg-gray-900/90 backdrop-blur-md border border-gray-700/50 rounded-lg p-3 shadow-2xl transition-all duration-300 origin-top-left ${showOverlay ? 'scale-100 opacity-100' : 'scale-95 opacity-0 pointer-events-none'}`}>
            <div className="flex items-center justify-between mb-2 pb-2 border-b border-gray-700/50 cursor-pointer" onClick={() => setShowOverlay(false)}>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-black px-1.5 py-0.5 rounded ${selectedSignal.direction === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                  {selectedSignal.direction}
                </span>
                <span className="text-sm font-bold text-white">{selectedSignal.symbol}</span>
              </div>
              <ChevronUp className="w-3.5 h-3.5 text-gray-400 hover:text-white" />
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <span className="text-gray-400">Entry:</span>
                <span className="text-white font-mono">{Number(selectedSignal.entry_price).toFixed(5)}</span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-gray-400">TP:</span>
                <span className="text-emerald-400 font-mono">{selectedSignal.tp ? Number(selectedSignal.tp).toFixed(5) : '-'}</span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-gray-400">SL:</span>
                <span className="text-rose-400 font-mono">{selectedSignal.sl ? Number(selectedSignal.sl).toFixed(5) : '-'}</span>
              </div>
              {selectedSignal.score && (
                <div className="flex justify-between items-center text-xs pt-1 border-t border-gray-700/30 mt-1">
                  <span className="text-gray-500">Score:</span>
                  <span className="text-blue-400 font-bold">{Math.round(selectedSignal.score * 100)}%</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}


      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900/80 z-10">
          <span className="text-aethelgard-blue animate-pulse">Cargando datos de mercado...</span>
        </div>
      )}

      {error && (
        <div className="absolute z-20 top-4 left-1/2 -translate-x-1/2 bg-red-900/90 text-red-200 px-4 py-2 rounded-lg flex items-center gap-3 backdrop-blur-sm border border-red-700/50">
          <span>⚠️ {error}</span>
          <button
            className="px-2 py-1 bg-red-800/50 hover:bg-red-700/50 rounded text-xs transition-colors"
            onClick={fetchChart}
          >
            Reintentar
          </button>
        </div>
      )}

      <ChartView
        symbol={symbol}
        data={chartData}
        currentTimeframe={timeframe}
        onTimeframeChange={setTimeframe}
        entryPrice={meta.entryPrice}
        stopLoss={meta.stopLoss}
        takeProfit={meta.takeProfit}
        isBuy={meta.isBuy}
        signalTimestamp={selectedSignal?.timestamp}
        signalPrice={selectedSignal?.entry_price}
      />
    </div>
  );
};

export default InstrumentChartWithIndicators;
