
import React, { useEffect, useState } from 'react';
import { TradingViewChart } from '../portfolio/TradingViewChart';

interface InstrumentChartWithIndicatorsProps {
  symbol: string;
}

const InstrumentChartWithIndicators: React.FC<InstrumentChartWithIndicatorsProps> = ({ symbol }) => {
  const [chartData, setChartData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchChart = () => {
    setLoading(true);
    setError(null);
    fetch(`/api/chart/${symbol}/M15`)
      .then(res => {
        if (!res.ok) throw new Error('Error al obtener gráfica');
        return res.json();
      })
      .then(setChartData)
      .catch(err => {
        setError('No se pudo cargar la gráfica. Intenta nuevamente.');
        console.error('[InstrumentChartWithIndicators] Error:', err);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchChart();
    // eslint-disable-next-line
  }, [symbol]);

  // Mapear los datos del endpoint al formato esperado por TradingViewChart
  // Suponiendo que chartData tiene: candles [{time, open, high, low, close}], entryPrice, stopLoss, takeProfit, isBuy

  return (
    <div className="instrument-chart-with-indicators">
      <h2>Gráfica e Indicadores</h2>
      {loading && <div>Cargando gráfica...</div>}
      {error && (
        <div className="bg-red-900/60 text-red-200 p-2 rounded flex items-center gap-2">
          <span>⚠️</span> {error}
          <button className="ml-auto px-2 py-1 bg-red-700/40 rounded text-xs" onClick={fetchChart}>Reintentar</button>
        </div>
      )}
      {!loading && !error && chartData && chartData.candles && (
        <TradingViewChart
          symbol={symbol}
          timeframe="M15"
          entryPrice={chartData.entryPrice}
          stopLoss={chartData.stopLoss}
          takeProfit={chartData.takeProfit}
          isBuy={chartData.isBuy}
          // Puedes pasar más props si tu TradingViewChart los soporta
        />
      )}
      {!loading && (!chartData || !chartData.candles) && (
        <div>No hay datos de gráfica disponibles.</div>
      )}
    </div>
  );
};

export default InstrumentChartWithIndicators;
