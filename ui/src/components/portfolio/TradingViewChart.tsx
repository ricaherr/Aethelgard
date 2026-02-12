/**
 * TradingView Lightweight Chart Component
 * 
 * Displays candlestick chart with timeframe and symbol
 * Indicators (EMA 20, EMA 200, etc.) can be added manually via the chart toolbar
 * 
 * Usage:
 *   <TradingViewChart symbol="EURUSD" timeframe="M5" />
 */
import { useEffect, useRef } from 'react';
import { TrendingUp } from 'lucide-react';

interface TradingViewChartProps {
    symbol: string;
    timeframe?: string;
    height?: number;
    entryPrice?: number;
}

export function TradingViewChart({ symbol, timeframe = 'M5', height = 400, entryPrice }: TradingViewChartProps) {
    const container = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!container.current) return;

        // Map timeframe to TradingView interval
        const intervalMap: Record<string, string> = {
            'M1': '1',
            'M5': '5',
            'M15': '15',
            'M30': '30',
            'H1': '60',
            'H4': '240',
            'D1': 'D',
            'W1': 'W',
            'MN': 'M'
        };

        const tvInterval = intervalMap[timeframe] || '5';

        // Create TradingView widget script
        const script = document.createElement('script');
        script.src = 'https://s3.tradingview.com/tv.js';
        script.async = true;
        script.onload = () => {
            if (typeof (window as any).TradingView !== 'undefined') {
                new (window as any).TradingView.widget({
                    container_id: container.current?.id,
                    width: '100%',
                    height: height,
                    symbol: `FX:${symbol}`,
                    interval: tvInterval,
                    timezone: 'Etc/UTC',
                    theme: 'dark',
                    style: '1', // Candlestick
                    locale: 'es',
                    toolbar_bg: '#0a0b0f',
                    enable_publishing: false,
                    hide_side_toolbar: false,
                    allow_symbol_change: false,
                    // Note: EMA indicators can be added manually via the chart UI
                    // Auto-loading studies in free widget has limitations
                    studies: [],
                    backgroundColor: '#0a0b0f',
                    gridColor: 'rgba(255, 255, 255, 0.05)',
                    hide_top_toolbar: false,
                    withdateranges: true,
                    hide_legend: false,
                    save_image: false,
                });
            }
        };

        document.head.appendChild(script);

        return () => {
            document.head.removeChild(script);
        };
    }, [symbol, timeframe, height]);

    return (
        <div className="space-y-2">
            {/* Chart Header with Entry Point Badge */}
            <div className="flex items-center justify-between px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg">
                <div className="flex items-center gap-3">
                    <span className="text-white/70 font-medium text-sm">{symbol}</span>
                    <span className="text-white/40 text-xs">{timeframe}</span>
                </div>
                {entryPrice && (
                    <div className="flex items-center gap-2 px-2.5 py-1 bg-green-500/10 border border-green-500/20 rounded">
                        <TrendingUp size={12} className="text-green-400" />
                        <span className="text-green-400 text-xs font-mono font-bold">
                            Entry: {entryPrice.toFixed(5)}
                        </span>
                    </div>
                )}
            </div>

            {/* TradingView Chart */}
            <div
                ref={container}
                id={`tradingview_${symbol}_${timeframe}_${Math.random()}`}
                className="rounded-lg overflow-hidden border border-white/10"
            />
        </div>
    );
}
