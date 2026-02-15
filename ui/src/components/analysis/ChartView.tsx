
import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickData, LineData, SeriesMarker } from 'lightweight-charts';
import { TrendingUp, TrendingDown, Eye, EyeOff, Settings, Activity } from 'lucide-react';
import { cn } from '../../utils/cn';

interface ChartViewProps {
    symbol: string;
    data: CandlestickData[];
    markers?: any[]; // TODO: Define strict marker type
    className?: string;
    height?: number;
    entryPrice?: number;
    stopLoss?: number;
    takeProfit?: number;
    isBuy?: boolean;
    onTimeframeChange?: (tf: string) => void;
    currentTimeframe?: string;
    signalTimestamp?: string | number; // ISO string or Unix timestamp
    signalPrice?: number;
}

export const ChartView: React.FC<ChartViewProps> = ({
    symbol,
    data,
    markers = [],
    className,
    height = 500,
    entryPrice,
    stopLoss,
    takeProfit,
    isBuy,
    onTimeframeChange,
    currentTimeframe = 'M5',
    signalTimestamp,
    signalPrice
}) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
    const ema20SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
    const ema200SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

    // Configuraciones de usuario (podrían moverse a un contexto o props)
    const [showEMA20, setShowEMA20] = useState(true);
    const [showEMA200, setShowEMA200] = useState(true);
    const [ema20Period, setEma20Period] = useState(20);
    const [ema200Period, setEma200Period] = useState(200);
    const [showSettings, setShowSettings] = useState(false);

    const timeframes = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'];

    // Helper para calcular EMA
    const calculateEMA = (data: CandlestickData[], period: number): LineData[] => {
        const emaData: LineData[] = [];
        const multiplier = 2 / (period + 1);
        let ema = 0;

        data.forEach((candle, index) => {
            if (candle.close === undefined || candle.close === null) return;

            if (index === 0) {
                ema = candle.close;
            } else {
                ema = (candle.close - ema) * multiplier + ema;
            }

            if (index >= period - 1) {
                emaData.push({ time: candle.time, value: ema });
            }
        });
        return emaData;
    };

    // Inicialización del Gráfico
    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { color: 'transparent' },
                textColor: '#9ca3af', // gray-400
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
            },
            crosshair: {
                mode: 1, // Magnet
            },
            rightPriceScale: {
                borderColor: 'rgba(255, 255, 255, 0.1)',
            },
            timeScale: {
                borderColor: 'rgba(255, 255, 255, 0.1)',
                timeVisible: true,
            },
        });

        chartRef.current = chart;

        candlestickSeriesRef.current = chart.addCandlestickSeries({
            upColor: '#10b981', // emerald-500
            downColor: '#ef4444', // red-500
            borderVisible: false,
            wickUpColor: '#10b981',
            wickDownColor: '#ef4444',
        });

        ema20SeriesRef.current = chart.addLineSeries({
            color: '#3b82f6', // blue-500
            lineWidth: 2,
            priceLineVisible: false,
            crosshairMarkerVisible: false,
        });

        ema200SeriesRef.current = chart.addLineSeries({
            color: '#ef4444', // red-500
            lineWidth: 2,
            priceLineVisible: false,
            crosshairMarkerVisible: false,
        });

        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({
                    width: chartContainerRef.current.clientWidth,
                    height: chartContainerRef.current.clientHeight,
                });
            }
        };

        // Use ResizeObserver for container resizing (better than window resize)
        const resizeObserver = new ResizeObserver(() => {
            handleResize();
        });

        if (chartContainerRef.current) {
            resizeObserver.observe(chartContainerRef.current);
        }

        // Force initial resize
        handleResize();

        return () => {
            resizeObserver.disconnect();
            chart.remove();
            chartRef.current = null;
            candlestickSeriesRef.current = null;
            ema20SeriesRef.current = null;
            ema200SeriesRef.current = null;
        };

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
            chartRef.current = null;
            candlestickSeriesRef.current = null;
            ema20SeriesRef.current = null;
            ema200SeriesRef.current = null;
        };
    }, []);

    // Actualización de Datos y Configuración
    useEffect(() => {
        if (!chartRef.current || !candlestickSeriesRef.current || !data || data.length === 0) return;

        // 1. Sanitize Data (Sort by time, remove duplicates, ensure valid values)
        const cleanData = [...data]
            .filter(item => item.time && item.open !== null && item.high !== null && item.low !== null && item.close !== null)
            .sort((a, b) => (a.time as number) - (b.time as number))
            .filter((item, index, self) =>
                index === 0 || item.time !== self[index - 1].time
            );

        if (cleanData.length === 0) return;

        // 1. Set Data
        candlestickSeriesRef.current.setData(cleanData);

        // 2. Set Markers
        const chartMarkers: any[] = []; // Type SeriesMarker<Time>

        // Marker de la señal si existe timestamp
        if (signalTimestamp) {
            // Convert string timestamp to chart time
            const signalTime = new Date(signalTimestamp).getTime() / 1000 as Time;
            const signalMarker: SeriesMarker<Time> = {
                time: signalTime,
                position: 'aboveBar',
                color: '#facc15', // yellow-400
                shape: 'arrowDown',
                text: 'SIGNAL',
                size: 2, // Larger marker
            };
            chartMarkers.push(signalMarker);
        }

        if (candlestickSeriesRef.current) {
            candlestickSeriesRef.current.setMarkers(chartMarkers);
        }

        // 3. Price Lines (Entry, SL, TP)
        // Limpiar líneas anteriores (hacky en lightweight-charts v3, mejor recrear series si cambian mucho)

        // Configurar líneas de precio si existen y son válidas
        if (entryPrice && Number.isFinite(entryPrice) && entryPrice > 0) {
            candlestickSeriesRef.current.createPriceLine({
                price: entryPrice,
                color: isBuy ? '#10b981' : '#ef4444',
                lineWidth: 2,
                lineStyle: 2, // Dashed
                axisLabelVisible: true,
                title: isBuy ? 'BUY' : 'SELL',
                lineVisible: true,
            });
        }

        if (stopLoss && Number.isFinite(stopLoss) && stopLoss > 0) {
            candlestickSeriesRef.current.createPriceLine({
                price: stopLoss,
                color: '#ef4444',
                lineWidth: 2,
                lineStyle: 0, // Solid
                axisLabelVisible: true,
                title: 'SL',
                lineVisible: true,
            });
        }

        if (takeProfit && Number.isFinite(takeProfit) && takeProfit > 0) {
            candlestickSeriesRef.current.createPriceLine({
                price: takeProfit,
                color: '#10b981',
                lineWidth: 2,
                lineStyle: 0, // Solid
                axisLabelVisible: true,
                title: 'TP',
                lineVisible: true,
            });
        }

        // 3.1 Signal Price Line (Horizontal - Yellow)
        if (signalPrice && Number.isFinite(signalPrice) && signalPrice > 0) {
            candlestickSeriesRef.current.createPriceLine({
                price: signalPrice,
                color: '#facc15', // yellow-400
                lineWidth: 1, // Thinner line
                lineStyle: 2, // Dashed
                axisLabelVisible: true, // SHOW Price Label
                title: '', // No Text Overlay
                lineVisible: true,
            });
        }

        // 4. Update Indicators
        try {
            // Re-verify cleanData exists and has length
            if (cleanData && cleanData.length > 0) {
                if (ema20SeriesRef.current) {
                    if (showEMA20) {
                        const ema20Data = calculateEMA(cleanData, ema20Period);
                        // Ensure EMA data is sorted and unique (calculateEMA handles uniqueness now, but sorting relies on cleanData order)
                        ema20SeriesRef.current.setData(ema20Data);
                        ema20SeriesRef.current.applyOptions({ visible: true });
                    } else {
                        ema20SeriesRef.current.applyOptions({ visible: false });
                    }
                }

                if (ema200SeriesRef.current) {
                    if (showEMA200) {
                        const ema200Data = calculateEMA(cleanData, ema200Period);
                        ema200SeriesRef.current.setData(ema200Data);
                        ema200SeriesRef.current.applyOptions({ visible: true });
                    } else {
                        ema200SeriesRef.current.applyOptions({ visible: false });
                    }
                }
            }
        } catch (err) {
            console.error("ChartView Error (Indicators):", err);
        }

        // Fit content solo la primera vez o si cambia el símbolo
        // chartRef.current.timeScale().fitContent(); 
    }, [data, entryPrice, stopLoss, takeProfit, isBuy, showEMA20, showEMA200, ema20Period, ema200Period]);


    return (
        <div className={cn("flex flex-col gap-2 w-full h-full", className)}>
            {/* Header / Toolbar */}
            <div className="flex flex-wrap items-center justify-between p-2 bg-gray-900/50 border border-gray-800 rounded-lg gap-2">
                <div className="flex items-center gap-4">
                    <h3 className="text-white font-bold flex items-center gap-2">
                        <Activity size={18} className="text-aethelgard-blue" />
                        {symbol}
                    </h3>

                    {/* Timeframe Selector */}
                    <div className="flex items-center bg-gray-800 rounded-md p-0.5">
                        {timeframes.map((tf) => (
                            <button
                                key={tf}
                                onClick={() => onTimeframeChange && onTimeframeChange(tf)}
                                className={cn(
                                    "px-2 py-0.5 text-xs font-medium rounded transition-all",
                                    currentTimeframe === tf
                                        ? "bg-aethelgard-blue text-white shadow-sm"
                                        : "text-gray-400 hover:text-white hover:bg-gray-700"
                                )}
                            >
                                {tf}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setShowEMA20(!showEMA20)}
                        className={`px-3 py-1 text-xs font-bold rounded flex items-center gap-2 transition-all ${showEMA20
                            ? 'bg-blue-500/20 text-blue-400 border border-blue-500/50'
                            : 'bg-gray-800 text-gray-500 border border-gray-700 hover:border-gray-500'
                            }`}
                    >
                        {showEMA20 ? <Eye size={12} /> : <EyeOff size={12} />}
                        EMA 20
                    </button>

                    <button
                        onClick={() => setShowEMA200(!showEMA200)}
                        className={`px-3 py-1 text-xs font-bold rounded flex items-center gap-2 transition-all ${showEMA200
                            ? 'bg-red-500/20 text-red-400 border border-red-500/50'
                            : 'bg-gray-800 text-gray-500 border border-gray-700 hover:border-gray-500'
                            }`}
                    >
                        {showEMA200 ? <Eye size={12} /> : <EyeOff size={12} />}
                        EMA 200
                    </button>

                    <button
                        onClick={() => setShowSettings(!showSettings)}
                        className="p-1 text-gray-400 hover:text-white transition-colors"
                        title="Configuración"
                    >
                        <Settings size={14} />
                    </button>
                </div>
            </div>

            {/* Settings Panel (Overlay) */}
            {showSettings && (
                <div className="p-3 bg-gray-800 rounded-lg border border-gray-700 animate-in fade-in zoom-in-95 grid grid-cols-2 gap-4 absolute z-10 top-14 right-4 shadow-xl">
                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-blue-400 font-bold">EMA 20 (Azul)</label>
                        <input
                            type="number"
                            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white w-20"
                            value={ema20Period}
                            onChange={(e) => setEma20Period(Number(e.target.value))}
                        />
                    </div>
                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-red-400 font-bold">EMA 200 (Roja)</label>
                        <input
                            type="number"
                            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white w-20"
                            value={ema200Period}
                            onChange={(e) => setEma200Period(Number(e.target.value))}
                        />
                    </div>
                </div>
            )}

            {/* Chart Container - Flex child that MUST shrink */}
            <div
                ref={chartContainerRef}
                className="relative w-full flex-1 min-h-0 rounded-xl overflow-hidden border border-gray-800 bg-gray-900/40 backdrop-blur-sm"
            />
        </div>
    );
};

export default ChartView;
