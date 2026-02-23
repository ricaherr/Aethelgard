import { motion } from 'framer-motion';
import { MarketRegime } from '../../types/aethelgard';
import { TrendingUp, TrendingDown, PauseCircle, AlertTriangle } from 'lucide-react';
import { cn } from '../../utils/cn';

interface RegimeBadgeProps {
    regime: MarketRegime;
    size?: 'small' | 'medium' | 'large';
    showLabel?: boolean;
    animated?: boolean;
}

export function RegimeBadge({
    regime,
    size = 'medium',
    showLabel = true,
    animated = true
}: RegimeBadgeProps) {
    // Mapeo de regímenes a estilos
    const regimeConfig: Record<MarketRegime, any> = {
        'TREND': {
            bgColor: 'bg-aethelgard-green/15',
            borderColor: 'border-aethelgard-green/40',
            textColor: 'text-aethelgard-green',
            dotColor: 'bg-aethelgard-green',
            icon: <TrendingUp size={16} />,
            label: 'TREND REGIME'
        },
        'RANGE': {
            bgColor: 'bg-yellow-500/15',
            borderColor: 'border-yellow-500/40',
            textColor: 'text-yellow-400',
            dotColor: 'bg-yellow-400',
            icon: <PauseCircle size={16} />,
            label: 'RANGE REGIME'
        },
        'VOLATILE': {
            bgColor: 'bg-orange-500/15',
            borderColor: 'border-orange-500/40',
            textColor: 'text-orange-400',
            dotColor: 'bg-orange-400',
            icon: <AlertTriangle size={16} />,
            label: 'VOLATILE REGIME'
        },
        'SHOCK': {
            bgColor: 'bg-red-500/15',
            borderColor: 'border-red-500/40',
            textColor: 'text-red-400',
            dotColor: 'bg-red-400',
            icon: <AlertTriangle size={16} />,
            label: 'SHOCK REGIME'
        },
        'BULL': {
            bgColor: 'bg-green-500/15',
            borderColor: 'border-green-500/40',
            textColor: 'text-green-400',
            dotColor: 'bg-green-400',
            icon: <TrendingUp size={16} />,
            label: 'BULL REGIME'
        },
        'BEAR': {
            bgColor: 'bg-red-500/15',
            borderColor: 'border-red-500/40',
            textColor: 'text-red-400',
            dotColor: 'bg-red-400',
            icon: <TrendingDown size={16} />,
            label: 'BEAR REGIME'
        },
        'CRASH': {
            bgColor: 'bg-red-600/15',
            borderColor: 'border-red-600/40',
            textColor: 'text-red-400',
            dotColor: 'bg-red-500',
            icon: <AlertTriangle size={16} />,
            label: 'CRASH REGIME'
        },
        'NORMAL': {
            bgColor: 'bg-white/5',
            borderColor: 'border-white/10',
            textColor: 'text-white/60',
            dotColor: 'bg-white/40',
            icon: <TrendingDown size={16} />,
            label: 'NORMAL REGIME'
        }
    };

    const config = regimeConfig[regime] || regimeConfig['NORMAL'];

    const sizeClasses = {
        small: 'px-2 py-1 text-[10px]',
        medium: 'px-3 py-1.5 text-xs',
        large: 'px-4 py-2 text-sm'
    };

    const dotSize = {
        small: 'w-1.5 h-1.5',
        medium: 'w-2 h-2',
        large: 'w-2.5 h-2.5'
    };

    const iconSize = size === 'small' ? 12 : size === 'medium' ? 14 : 16;

    return (
        <motion.div
            initial={animated ? { opacity: 0, scale: 0.9 } : undefined}
            animate={animated ? { opacity: 1, scale: 1 } : undefined}
            transition={{ duration: 0.3 }}
            className={cn(
                'inline-flex items-center gap-2 rounded-full border backdrop-blur-sm transition-all duration-300',
                sizeClasses[size],
                config.bgColor,
                config.borderColor,
                config.textColor,
                'font-bold tracking-wider uppercase',
                animated && 'hover:scale-105'
            )}
        >
            {/* Heartbeat Dot Animation */}
            <motion.div
                animate={animated ? { scale: [1, 1.3, 1] } : undefined}
                transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    repeatType: 'loop'
                }}
                className={cn(
                    'rounded-full',
                    dotSize[size],
                    config.dotColor,
                    animated && `shadow-[0_0_${size === 'small' ? '8' : size === 'medium' ? '12' : '16'}px_${regime === 'TREND'
                        ? 'rgba(0,255,200,0.5)'
                        : regime === 'RANGE'
                            ? 'rgba(255,193,7,0.5)'
                            : regime === 'CRASH'
                                ? 'rgba(255,0,0,0.5)'
                                : 'rgba(255,255,255,0.3)'
                    }]`
                )}
            />

            {/* Icon + Label */}
            <div className="flex items-center gap-1">
                <div className="flex-shrink-0">
                    {(() => {
                        const Icon = regime === 'TREND' || regime === 'BULL'
                            ? TrendingUp
                            : regime === 'RANGE'
                                ? PauseCircle
                                : regime === 'CRASH' || regime === 'BEAR' || regime === 'SHOCK'
                                    ? AlertTriangle
                                    : TrendingDown;
                        return <Icon size={iconSize} />;
                    })()}
                </div>
                {showLabel && <span>{config.label}</span>}
            </div>

            {/* Confidence Indicator (optional pulse ring) */}
            {animated && (
                <motion.div
                    initial={{ opacity: 0.5, scale: 1 }}
                    animate={{ opacity: 0, scale: 1.5 }}
                    transition={{
                        duration: 1.5,
                        repeat: Infinity,
                        repeatType: 'loop'
                    }}
                    className={cn(
                        'absolute inset-0 rounded-full border',
                        config.borderColor
                    )}
                />
            )}
        </motion.div>
    );
}
