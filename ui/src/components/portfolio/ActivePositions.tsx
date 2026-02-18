import { TrendingUp, TrendingDown, Info, LineChart, Maximize2, Minimize2 } from 'lucide-react';
import { PositionMetadata } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';
import { motion, AnimatePresence } from 'framer-motion';
import { useState, useEffect } from 'react';
import ChartView from '../analysis/ChartView';
import { CandlestickData } from 'lightweight-charts';

interface ActivePositionsProps {
    positions: PositionMetadata[];
    fullscreenTicket?: number | null;
    onFullscreenToggle?: (ticket: number | null) => void;
}

export function ActivePositions({ positions, fullscreenTicket, onFullscreenToggle }: ActivePositionsProps) {
    // Filter positions: if fullscreen active, show only that trade
    const displayPositions = fullscreenTicket !== null
        ? positions.filter(p => p.ticket === fullscreenTicket)
        : positions;

    const totalProfit = displayPositions.reduce((sum, p) => sum + p.profit_usd, 0);
    const totalRisk = displayPositions.reduce((sum, p) => sum + p.initial_risk_usd, 0);
    const avgRMultiple = displayPositions.length > 0
        ? displayPositions.reduce((sum, p) => sum + p.r_multiple, 0) / displayPositions.length
        : 0;

    return (
        <GlassPanel className="h-full flex flex-col border-white/5">
            {/* Header with Stats */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h3 className="text-white/90 font-outfit font-bold tracking-tight text-lg">
                        Active Positions
                        {fullscreenTicket !== null && (
                            <span className="ml-2 text-sm text-purple-400">· FULLSCREEN</span>
                        )}
                    </h3>
                    <p className="text-white/50 text-[10px] uppercase tracking-[0.2em] mt-1">
                        {displayPositions.length} {fullscreenTicket !== null ? 'Selected' : 'Open'} · Avg {avgRMultiple.toFixed(2)}R
                    </p>
                </div>
                <div className="flex gap-4">
                    <div className="text-right">
                        <div className="text-[10px] text-white/50 uppercase font-bold tracking-widest">Total P/L</div>
                        <div className={`text-lg font-mono font-bold ${totalProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {totalProfit >= 0 ? '+' : ''}${totalProfit.toFixed(2)}
                        </div>
                    </div>
                    <div className="text-right">
                        <div className="text-[10px] text-white/50 uppercase font-bold tracking-widest">Total Risk</div>
                        <div className="text-lg font-mono font-bold text-orange-400">
                            ${totalRisk.toFixed(2)}
                        </div>
                    </div>
                </div>
            </div>

            {/* Positions List */}
            <div className="flex-1 space-y-3 overflow-y-auto scrollbar-hide pr-1">
                <AnimatePresence initial={false}>
                    {displayPositions.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center opacity-20 py-20">
                            <Info size={48} className="mb-4" />
                            <p className="text-sm font-outfit uppercase tracking-widest">No Active Positions</p>
                        </div>
                    ) : (
                        displayPositions.map((position) => (
                            <PositionCard
                                key={position.ticket}
                                position={position}
                                fullscreenTicket={fullscreenTicket}
                                onFullscreenToggle={onFullscreenToggle}
                            />
                        ))
                    )}
                </AnimatePresence>
            </div>
        </GlassPanel>
    );
}

interface PositionCardProps {
    position: PositionMetadata;
    fullscreenTicket?: number | null;
    onFullscreenToggle?: (ticket: number | null) => void;
}

function PositionCard({ position, fullscreenTicket, onFullscreenToggle }: PositionCardProps) {
    const [showChart, setShowChart] = useState(false);
    const [chartData, setChartData] = useState<CandlestickData[]>([]);
    const [loadingChart, setLoadingChart] = useState(false);

    const isFullscreen = fullscreenTicket === position.ticket;
    const isProfit = position.profit_usd >= 0;

    // Infer position type if not provided
    const isBuy = position.type === 'BUY' ||
        (!position.type && position.sl < position.entry_price && position.tp > position.entry_price);

    const rColor =
        position.r_multiple >= 1 ? 'text-green-400' :
            position.r_multiple >= 0 ? 'text-yellow-400' :
                'text-red-400';

    const assetBadge: Record<string, string> = {
        forex: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
        metal: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
        crypto: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
        index: 'bg-gray-500/20 text-gray-400 border-gray-500/30'
    };

    // Cargar datos del gráfico si se muestra
    useEffect(() => {
        if ((showChart || isFullscreen) && position.timeframe && chartData.length === 0) {
            setLoadingChart(true);
            fetch(`/api/chart/${position.symbol}/${position.timeframe}`)
                .then(res => res.json())
                .then(data => {
                    if (data.candles && Array.isArray(data.candles)) {
                        setChartData(data.candles);
                    } else if (Array.isArray(data)) { // Fallback si el backend devuelve array directo
                        setChartData(data);
                    }
                })
                .catch(err => console.error("Error loading chart:", err))
                .finally(() => setLoadingChart(false));
        }
    }, [showChart, isFullscreen, position.symbol, position.timeframe, chartData.length]);

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            whileHover={{ scale: 1.005, backgroundColor: 'rgba(255,255,255,0.03)' }}
            className="p-4 rounded-xl border border-white/5 bg-white/[0.01] transition-all group"
        >
            {/* Header: Symbol + Asset Badge + R-Multiple + Chart Button */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                    <span className="text-base font-outfit font-bold text-white/90">{position.symbol}</span>

                    {/* High Exposure Badge */}
                    {position.initial_risk_usd > 100 && (
                        <span className="text-[9px] px-2 py-0.5 rounded bg-red-500/20 text-red-500 border border-red-500/30 font-bold animate-pulse">
                            HIGH EXPOSURE
                        </span>
                    )}

                    <span className={`text-[9px] px-2 py-0.5 rounded uppercase font-bold border ${assetBadge[position.asset_type] || assetBadge['forex']}`}>
                        {position.asset_type}
                    </span>

                    {/* Chart Toggle Button */}
                    {position.timeframe && (
                        <>
                            <button
                                onClick={() => setShowChart(!showChart)}
                                className={`
                                    px-2 py-0.5 rounded text-[9px] transition-all border
                                    ${showChart
                                        ? 'bg-aethelgard-blue/20 text-aethelgard-blue border-aethelgard-blue/30'
                                        : 'bg-white/5 text-white/40 hover:text-white/70 hover:bg-white/10 border-white/10'
                                    }
                                `}
                                title={`${showChart ? 'Hide' : 'Show'} chart`}
                            >
                                <LineChart size={9} />
                            </button>

                            {/* Fullscreen Toggle Button */}
                            {onFullscreenToggle && (
                                <button
                                    onClick={() => onFullscreenToggle(isFullscreen ? null : position.ticket)}
                                    className={`
                                        px-2 py-0.5 rounded text-[9px] transition-all border
                                        ${isFullscreen
                                            ? 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                                            : 'bg-white/5 text-white/40 hover:text-white/70 hover:bg-white/10 border-white/10'
                                        }
                                    `}
                                    title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen chart'}
                                >
                                    {isFullscreen ? <Minimize2 size={9} /> : <Maximize2 size={9} />}
                                </button>
                            )}
                        </>
                    )}
                </div>

                <div className="flex items-center gap-3">
                    <div className="text-right">
                        <div className="text-[9px] text-white/50 uppercase font-bold tracking-widest">R-Multiple</div>
                        <div className={`text-lg font-bold ${rColor}`}>
                            {position.r_multiple >= 0 ? '+' : ''}{position.r_multiple.toFixed(2)}R
                        </div>
                    </div>
                    {isProfit ? <TrendingUp size={18} className="text-green-400" /> : <TrendingDown size={18} className="text-red-400" />}
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-4 gap-3 text-xs">
                <div>
                    <div className="text-white/50 uppercase font-bold tracking-widest text-[9px] mb-1">Entry</div>
                    <div className="font-mono text-white/70">{position.entry_price.toLocaleString()}</div>
                </div>

                <div>
                    <div className="text-white/50 uppercase font-bold tracking-widest text-[9px] mb-1">Profit</div>
                    <div className={`font-mono font-bold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                        {isProfit ? '+' : ''}${position.profit_usd.toFixed(2)}
                    </div>
                </div>

                <div>
                    <div className="text-white/50 uppercase font-bold tracking-widest text-[9px] mb-1">Risk</div>
                    <div className="font-mono font-bold text-orange-400">
                        ${position.initial_risk_usd.toFixed(2)}
                    </div>
                </div>

                <div>
                    <div className="text-white/50 uppercase font-bold tracking-widest text-[9px] mb-1">Volume</div>
                    <div className="font-mono text-white/70">
                        {position.volume.toFixed(2)}
                    </div>
                </div>
            </div>

            {/* Modification Failures / Alerts */}
            {(position as any).metadata?.modification_failures && (
                <div className="mt-3 p-2 bg-red-900/10 border border-red-500/20 rounded-lg flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-ping" />
                    <span className="text-[9px] text-red-400 font-bold uppercase tracking-widest">
                        Error de Modificación: {(position as any).metadata.modification_failures}
                    </span>
                </div>
            )}

            {/* Footer: SL/TP + TF + Strategy + Regime */}
            <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between text-[10px]">
                <div className="flex gap-4">
                    <span className="text-white/40">
                        SL: <span className="text-red-400 font-mono">{position.sl.toLocaleString()}</span>
                    </span>
                    <span className="text-white/40">
                        TP: <span className="text-green-400 font-mono">{position.tp.toLocaleString()}</span>
                    </span>
                </div>
                <div className="flex gap-3 text-white/40">
                    {position.timeframe && (
                        <span>
                            TF: <span className="text-cyan-400 font-bold">{position.timeframe}</span>
                        </span>
                    )}
                    {position.strategy && (
                        <span>
                            Strategy: <span className="text-purple-400 font-bold">{position.strategy}</span>
                        </span>
                    )}
                    <span>
                        Regime: <span className="text-aethelgard-blue font-bold">{position.entry_regime}</span>
                    </span>
                </div>
            </div>

            {/* Expandable Chart */}
            <AnimatePresence>
                {(showChart || isFullscreen) && position.timeframe && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: isFullscreen ? 650 : 420, opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3 }}
                        className="mt-4 pt-4 border-t border-white/5 overflow-hidden flex flex-col"
                    >
                        <div className="mb-2 flex items-center justify-between flex-shrink-0">
                            <div className="text-[10px] uppercase tracking-widest text-white/50 font-bold">
                                Chart · {position.symbol} · {position.timeframe}
                                {isFullscreen && (
                                    <span className="ml-2 text-purple-400">· FULLSCREEN MODE</span>
                                )}
                            </div>
                            {loadingChart && <span className="text-[10px] text-aethelgard-blue animate-pulse">Loading Chart...</span>}
                        </div>
                        <div className="flex-1 min-h-0 relative">
                            <ChartView
                                symbol={position.symbol}
                                data={chartData}
                                currentTimeframe={position.timeframe}
                                // Hide controls for compact view if not fullscreen? Maybe in future.
                                height={isFullscreen ? 600 : 350}
                                entryPrice={position.entry_price}
                                stopLoss={position.sl}
                                takeProfit={position.tp}
                                isBuy={isBuy}
                            />
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
}
