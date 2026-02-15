import React from 'react';
import { TrendingUp, TrendingDown, Activity, Zap, PieChart } from 'lucide-react';
import { HeatmapData } from '../../hooks/useHeatmapData';
import InfoTooltip from './InfoTooltip';

interface MetricWidgetProps {
    data: HeatmapData | null;
    loading: boolean;
}

const MetricWidget: React.FC<MetricWidgetProps> = ({ data, loading }) => {
    if (loading && !data) return null;
    if (!data || !data.cells.length) return null;

    // Calculate Metrics
    const totalCells = data.cells.length;
    const bullishCount = data.cells.filter(c => c.metrics?.bias === 'BULLISH').length;
    const bearishCount = data.cells.filter(c => c.metrics?.bias === 'BEARISH').length;

    const sentiment = totalCells > 0 ? (bullishCount / (bullishCount + bearishCount || 1)) * 100 : 50;

    const trendParticipation = (data.cells.filter(c => c.regime === 'TREND').length / totalCells) * 100;
    const avgADX = data.cells.reduce((acc, c) => acc + (c.metrics?.adx || 0), 0) / totalCells;

    return (
        <div className="flex flex-wrap items-center gap-4 animate-in fade-in slide-in-from-top-4 duration-500 bg-gray-900/40 backdrop-blur-md border border-gray-800/50 p-2 px-4 rounded-xl">
            {/* Market Sentiment */}
            <div className="flex items-center gap-3 pr-4 border-r border-gray-800/50">
                <div className="flex flex-col">
                    <div className="flex items-center">
                        <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Sentiment</p>
                        <InfoTooltip
                            title="Market Sentiment"
                            content="Porcentaje de sesgo alcista detectado en todos los instrumentos y temporalidades escaneadas. >50% indica optimismo general."
                        />
                    </div>
                    <h3 className="text-sm font-bold text-white">{sentiment.toFixed(0)}% <span className="text-[10px] text-gray-400 font-normal uppercase">Bull</span></h3>
                </div>
                <div className="w-12 h-1 bg-gray-800 rounded-full overflow-hidden relative">
                    <div
                        className="absolute h-full bg-emerald-500 transition-all duration-1000"
                        style={{ width: `${sentiment}%` }}
                    />
                </div>
            </div>

            {/* Volatility / ADX */}
            <div className="flex items-center gap-3 pr-4 border-r border-gray-800/50">
                <div className="p-1.5 bg-yellow-500/10 rounded-md">
                    <Zap className="w-3.5 h-3.5 text-yellow-400" />
                </div>
                <div>
                    <div className="flex items-center">
                        <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Avg ADX</p>
                        <InfoTooltip
                            title="Average ADX"
                            content="Indica la fuerza promedio de las tendencias actuales. Valores por encima de 25 sugieren tendencias sólidas y operables."
                        />
                    </div>
                    <h3 className="text-sm font-bold text-white leading-none">{avgADX.toFixed(1)}</h3>
                </div>
            </div>

            {/* Trend Intensity */}
            <div className="flex items-center gap-3 pr-4 border-r border-gray-800/50">
                <div className="p-1.5 bg-emerald-500/10 rounded-md">
                    <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                </div>
                <div>
                    <div className="flex items-center">
                        <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Trend Flow</p>
                        <InfoTooltip
                            title="Trend Flow"
                            content="Porcentaje del mercado que se encuentra en un régimen de tendencia activo vs rango lateral. Mide la 'salud' direccional."
                        />
                    </div>
                    <h3 className="text-sm font-bold text-white leading-none">{trendParticipation.toFixed(1)}%</h3>
                </div>
            </div>

            {/* Quick Status Icon */}
            <div className="ml-auto flex items-center gap-2">
                <Activity className={`w-4 h-4 ${avgADX > 25 ? 'text-yellow-400 animate-pulse' : 'text-gray-600'}`} />
                <span className="text-[10px] text-gray-500 font-mono uppercase">Live Analytics</span>
            </div>
        </div>
    );
};

export default MetricWidget;
