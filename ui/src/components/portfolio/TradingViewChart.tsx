/**
 * TradingView Lightweight Chart Component
 * 
 * Displays candlestick chart with:
 * - Entry Price line (green/red)
 * - Stop Loss line (red)
 * - Take Profit line (green)
 * - EMA 20 (yellow)
 * - EMA 200 (blue)
 * 
 * Usage:
 *   <TradingViewChart 
 *     symbol="EURUSD" 
 *     timeframe="M5" 
 *     entryPrice={1.0850}
 *     stopLoss={1.0820}
 *     takeProfit={1.0900}
 *     isBuy={true}
 *   />
 */
import { useEffect, useRef, useState } from 'react';
import { TrendingUp, TrendingDown, Eye, EyeOff, Settings } from 'lucide-react';
import { 
    createChart, 
    IChartApi, 
    ISeriesApi, 
    CandlestickData, 
    LineData 
} from 'lightweight-charts';

interface TradingViewChartProps {
    symbol: string;
    timeframe?: string;
    height?: number;
    entryPrice?: number;
    stopLoss?: number;
    takeProfit?: number;
    isBuy?: boolean;
}

export function TradingViewChart({ 
    symbol, 
    timeframe: initialTimeframe = 'M5', 
    height = 400, 
    entryPrice,
    stopLoss,
    takeProfit,
    isBuy = true
}: TradingViewChartProps) {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    
    // Trading toolbar state
    const [selectedTimeframe, setSelectedTimeframe] = useState(initialTimeframe);
    const [showEMA20, setShowEMA20] = useState(true);
    const [showEMA200, setShowEMA200] = useState(true);
    const [ema20Period, setEma20Period] = useState(20);
    const [ema200Period, setEma200Period] = useState(200);
    const [showSettings, setShowSettings] = useState(false);
    
    const timeframes = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'];

    useEffect(() => {
        if (!chartContainerRef.current) return;

        // Get container dimensions
        const containerWidth = chartContainerRef.current.clientWidth;
        const containerHeight = chartContainerRef.current.clientHeight || height || 400;

        // Create chart instance
        const chart = createChart(chartContainerRef.current, {
            width: containerWidth,
            height: containerHeight,
            layout: {
                background: { color: '#0a0b0f' },
                textColor: '#D9D9D9',
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
            },
            crosshair: {
                mode: 1, // Normal crosshair
            },
            rightPriceScale: {
                borderColor: 'rgba(255, 255, 255, 0.1)',
            },
            timeScale: {
                borderColor: 'rgba(255, 255, 255, 0.1)',
                timeVisible: true,
                secondsVisible: false,
            },
            handleScroll: {
                mouseWheel: true,
                pressedMouseMove: true,
            },
            handleScale: {
                axisPressedMouseMove: true,
                mouseWheel: true,
                pinch: true,
            },
        });

        chartRef.current = chart;

        // Add candlestick series
        const candleSeries = chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        // Generate simulated candle data (500 velas para EMA 200 extensa)
        const candleData = generateSimulatedData(entryPrice || 1.1000, 500);
        candleSeries.setData(candleData);
        
        // Add entry marker if price is available (al 85% para que sea reciente)
        if (entryPrice) {
            const entryIndex = Math.floor(candleData.length * 0.85);
            const entryTime = candleData[entryIndex].time;
            const actualEntryPrice = candleData[entryIndex].close; // Usar precio real de la vela
            
            candleSeries.setMarkers([
                {
                    time: entryTime,
                    position: isBuy ? 'belowBar' : 'aboveBar',
                    color: isBuy ? '#22c55e' : '#ef4444',
                    shape: isBuy ? 'arrowUp' : 'arrowDown',
                    text: isBuy ? 'BUY' : 'SELL',
                    size: 1,
                }
            ]);
        }

        // Add EMA 20 (yellow) - if enabled
        let ema20Series: ISeriesApi<"Line"> | null = null;
        if (showEMA20) {
            ema20Series = chart.addLineSeries({
                color: '#fbbf24',
                lineWidth: 2,
                priceLineVisible: false,
                lastValueVisible: true,
            });
            const ema20Data = calculateEMA(candleData, ema20Period);
            ema20Series.setData(ema20Data);
        }

        // Add EMA 200 (blue) - if enabled
        let ema200Series: ISeriesApi<"Line"> | null = null;
        if (showEMA200) {
            ema200Series = chart.addLineSeries({
                color: '#3b82f6',
                lineWidth: 2,
                priceLineVisible: false,
                lastValueVisible: true,
            });
            const ema200Data = calculateEMA(candleData, ema200Period);
            ema200Series.setData(ema200Data);
        }

        // Add price level lines if available
        if (entryPrice) {
            // Entry Price Line (green for BUY, red for SELL)
            candleSeries.createPriceLine({
                price: entryPrice,
                color: isBuy ? '#22c55e' : '#ef4444',
                lineWidth: 2 as const,
                lineStyle: 2 as const, // Dashed
                lineVisible: true,
                axisLabelVisible: true,
                title: 'Entry',
            });
        }

        if (stopLoss && stopLoss > 0) {
            // Stop Loss Line (always red)
            candleSeries.createPriceLine({
                price: stopLoss,
                color: '#ef4444',
                lineWidth: 3 as const,
                lineStyle: 0 as const, // Solid
                lineVisible: true,
                axisLabelVisible: true,
                title: 'SL',
            });
        }

        if (takeProfit && takeProfit > 0) {
            // Take Profit Line (always green)
            candleSeries.createPriceLine({
                price: takeProfit,
                color: '#22c55e',
                lineWidth: 3 as const,
                lineStyle: 0 as const, // Solid
                lineVisible: true,
                axisLabelVisible: true,
                title: 'TP',
            });
        }

        // Mostrar las últimas 60 velas (posición inicial en tiempo reciente)
        chart.timeScale().setVisibleLogicalRange({
            from: Math.max(0, candleData.length - 60),
            to: candleData.length - 1,
        });

        // Handle resize
        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                const newWidth = chartContainerRef.current.clientWidth;
                const newHeight = chartContainerRef.current.clientHeight || height || 400;
                chartRef.current.applyOptions({
                    width: newWidth,
                    height: newHeight,
                });
            }
        };

        window.addEventListener('resize', handleResize);

        // Cleanup
        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, [symbol, selectedTimeframe, height, entryPrice, stopLoss, takeProfit, isBuy, showEMA20, showEMA200, ema20Period, ema200Period]);

    return (
        <div className="flex flex-col h-full space-y-2">
            {/* Chart Header with Entry Point Badge */}
            <div className="flex items-center justify-between px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg flex-shrink-0">
                <div className="flex items-center gap-3">
                    <span className="text-white/70 font-medium text-sm">{symbol}</span>
                    {entryPrice && (
                        <div className="flex items-center gap-2 px-2.5 py-1 bg-gradient-to-r from-green-500/10 to-emerald-500/10 border border-green-500/30 rounded">
                            {isBuy ? (
                                <TrendingUp size={16} className="text-green-400 font-bold" strokeWidth={2.5} />
                            ) : (
                                <TrendingDown size={16} className="text-red-400 font-bold" strokeWidth={2.5} />
                            )}
                            <span className={`${isBuy ? 'text-green-400' : 'text-red-400'} text-xs font-mono font-bold uppercase`}>
                                {isBuy ? 'BUY' : 'SELL'} @ {entryPrice.toFixed(5)}
                            </span>
                        </div>
                    )}
                </div>
            </div>
            
            {/* Trading Toolbar */}
            <div className="flex items-center justify-between px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg flex-shrink-0">
                {/* Timeframe Selector */}
                <div className="flex items-center gap-1.5">
                    <span className="text-white/40 text-[10px] uppercase mr-1">Timeframe:</span>
                    {timeframes.map((tf) => (
                        <button
                            key={tf}
                            onClick={() => setSelectedTimeframe(tf)}
                            className={`px-2 py-1 text-[10px] font-medium rounded transition-all ${
                                selectedTimeframe === tf
                                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                                    : 'text-white/40 hover:text-white/60 hover:bg-white/5'
                            }`}
                        >
                            {tf}
                        </button>
                    ))}
                </div>
                
                {/* Indicators Toggles */}
                <div className="flex items-center gap-3">
                    <span className="text-white/40 text-[10px] uppercase">Indicators:</span>
                    <button
                        onClick={() => setShowEMA20(!showEMA20)}
                        className={`flex items-center gap-1.5 px-2 py-1 text-[10px] font-medium rounded transition-all ${
                            showEMA20
                                ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
                                : 'text-white/40 hover:text-white/60 hover:bg-white/5'
                        }`}
                    >
                        {showEMA20 ? <Eye size={10} /> : <EyeOff size={10} />}
                        <div className="w-3 h-0.5 bg-yellow-400 rounded"></div>
                        <span>EMA {ema20Period}</span>
                    </button>
                    <button
                        onClick={() => setShowEMA200(!showEMA200)}
                        className={`flex items-center gap-1.5 px-2 py-1 text-[10px] font-medium rounded transition-all ${
                            showEMA200
                                ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                                : 'text-white/40 hover:text-white/60 hover:bg-white/5'
                        }`}
                    >
                        {showEMA200 ? <Eye size={10} /> : <EyeOff size={10} />}
                        <div className="w-3 h-0.5 bg-blue-400 rounded"></div>
                        <span>EMA {ema200Period}</span>
                    </button>
                    <button
                        onClick={() => setShowSettings(!showSettings)}
                        className={`flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded transition-all ${
                            showSettings
                                ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                                : 'text-white/40 hover:text-white/60 hover:bg-white/5'
                        }`}
                        title="Settings"
                    >
                        <Settings size={12} />
                    </button>
                </div>
            </div>
            
            {/* Settings Panel */}
            {showSettings && (
                <div className="px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg space-y-2 flex-shrink-0">
                    <div className="text-[10px] uppercase tracking-widest text-white/50 font-bold mb-2">
                        Indicator Settings
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        {/* EMA 20 Settings */}
                        <div className="space-y-1.5">
                            <label className="flex items-center gap-2 text-[10px] text-yellow-400">
                                <div className="w-3 h-0.5 bg-yellow-400 rounded"></div>
                                EMA Short Period
                            </label>
                            <input
                                type="number"
                                min="5"
                                max="50"
                                value={ema20Period}
                                onChange={(e) => setEma20Period(parseInt(e.target.value) || 20)}
                                className="w-full px-2 py-1 text-xs bg-white/5 border border-white/10 rounded text-white/90 focus:border-yellow-500/50 focus:outline-none"
                            />
                        </div>
                        {/* EMA 200 Settings */}
                        <div className="space-y-1.5">
                            <label className="flex items-center gap-2 text-[10px] text-blue-400">
                                <div className="w-3 h-0.5 bg-blue-400 rounded"></div>
                                EMA Long Period
                            </label>
                            <input
                                type="number"
                                min="50"
                                max="300"
                                value={ema200Period}
                                onChange={(e) => setEma200Period(parseInt(e.target.value) || 200)}
                                className="w-full px-2 py-1 text-xs bg-white/5 border border-white/10 rounded text-white/90 focus:border-blue-500/50 focus:outline-none"
                            />
                        </div>
                    </div>
                </div>
            )}

            {/* Chart Container - Responsive */}
            <div
                ref={chartContainerRef}
                className="flex-1 rounded-lg overflow-hidden border border-white/10 bg-[#0a0b0f] min-h-[300px]"
                style={{ height: '100%' }}
            />
        </div>
    );
}

// Helper function to generate simulated candle data
function generateSimulatedData(basePrice: number, count: number): CandlestickData[] {
    const data: CandlestickData[] = [];
    const now = Math.floor(Date.now() / 1000);
    const interval = 300; // 5 minutes in seconds

    // Start with a price slightly below basePrice to create movement towards it
    let price = basePrice * 0.998; // Start 0.2% below

    for (let i = count; i >= 0; i--) {
        const time = (now - i * interval) as any;
        
        // Simulate price movement (random walk with slight upward bias towards basePrice)
        const targetBias = (basePrice - price) * 0.001; // Gentle pull towards basePrice
        const randomChange = (Math.random() - 0.5) * 0.002 * basePrice; // ±0.2% variation
        const change = randomChange + targetBias;
        
        const open = price;
        const close = price + change;
        const high = Math.max(open, close) + Math.random() * 0.0005 * basePrice;
        const low = Math.min(open, close) - Math.random() * 0.0005 * basePrice;

        data.push({
            time,
            open,
            high,
            low,
            close,
        });

        price = close;
    }

    return data;
}

// Helper function to calculate EMA
function calculateEMA(candleData: CandlestickData[], period: number): LineData[] {
    const emaData: LineData[] = [];
    let ema = 0;
    const multiplier = 2 / (period + 1);

    candleData.forEach((candle, index) => {
        if (index === 0) {
            ema = candle.close;
        } else {
            ema = (candle.close - ema) * multiplier + ema;
        }

        // Only add data points after the period
        if (index >= period - 1) {
            emaData.push({
                time: candle.time,
                value: ema,
            });
        }
    });

    return emaData;
}
