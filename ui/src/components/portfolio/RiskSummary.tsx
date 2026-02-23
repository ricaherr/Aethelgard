import { Shield, AlertCircle, TrendingUp, WifiOff, Wifi, DollarSign, AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react';
import { RiskSummary as RiskSummaryType } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';

interface RiskSummaryProps {
    summary: RiskSummaryType;
    collapsed?: boolean;
    onToggleCollapse?: () => void;
}

export function RiskSummary({ summary, collapsed = false, onToggleCollapse }: RiskSummaryProps) {
    const riskLevel =
        (summary?.risk_percentage || 0) > (summary?.max_allowed_risk_pct || 5) * 0.9 ? 'critical' :
            (summary?.risk_percentage || 0) > (summary?.max_allowed_risk_pct || 5) * 0.7 ? 'warning' :
                'safe';

    const getRiskColor = () => {
        if (riskLevel === 'critical') return 'bg-red-500';
        if (riskLevel === 'warning') return 'bg-yellow-500';
        return 'bg-green-500';
    };

    const getRiskTextColor = () => {
        if (riskLevel === 'critical') return 'text-red-400';
        if (riskLevel === 'warning') return 'text-yellow-400';
        return 'text-green-400';
    };

    // Balance source indicator
    const getBalanceIndicator = () => {
        const source = summary.balance_metadata?.source || 'UNKNOWN';
        const isLive = summary.balance_metadata?.is_live || false;

        if (source === 'MT5_LIVE' || isLive) {
            return {
                icon: <Wifi size={12} />,
                color: 'text-green-400',
                label: 'Live from MT5',
                dotColor: 'bg-green-400'
            };
        } else if (source === 'CACHED') {
            return {
                icon: <DollarSign size={12} />,
                color: 'text-yellow-400',
                label: 'Cached data',
                dotColor: 'bg-yellow-400'
            };
        } else {
            return {
                icon: <WifiOff size={12} />,
                color: 'text-gray-400',
                label: 'Default value',
                dotColor: 'bg-gray-400'
            };
        }
    };

    const balanceIndicator = getBalanceIndicator();

    // Collapsed view: only icons
    if (collapsed) {
        return (
            <GlassPanel className="h-full border-white/5 flex flex-col items-center py-6 gap-6 relative">
                {/* Expand Button */}
                {onToggleCollapse && (
                    <button
                        onClick={onToggleCollapse}
                        className="absolute top-2 right-2 p-1 hover:bg-white/5 rounded-md transition-all"
                        title="Expand panel"
                    >
                        <ChevronRight size={12} className="text-white/50 hover:text-white/70" />
                    </button>
                )}

                <div className="flex flex-col items-center gap-1" title="Risk Management">
                    <Shield size={20} className="text-aethelgard-blue" />
                    <div className={`w-1.5 h-1.5 rounded-full ${getRiskColor()}`} />
                </div>

                <div className="flex flex-col items-center gap-1" title={`Balance: $${(summary?.account_balance || 0).toFixed(2)}`}>
                    <DollarSign size={18} className="text-green-400" />
                    <div className={`w-1.5 h-1.5 rounded-full ${balanceIndicator.dotColor}`} />
                </div>

                <div className="flex flex-col items-center gap-1" title={`Total Risk: $${(summary?.total_risk_usd || 0).toFixed(2)}`}>
                    <TrendingUp size={18} className={getRiskTextColor()} />
                    <span className="text-[8px] text-white/40">{(summary?.risk_percentage || 0).toFixed(0)}%</span>
                </div>

                {summary.warnings.length > 0 && (
                    <div className="flex flex-col items-center gap-1" title={`${summary.warnings.length} warnings`}>
                        <AlertTriangle size={18} className="text-yellow-400" />
                        <span className="text-[8px] text-yellow-400">{summary.warnings.length}</span>
                    </div>
                )}
            </GlassPanel>
        );
    }

    return (
        <GlassPanel className="h-full border-white/5 relative">
            {/* Header with Collapse Button */}
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                    <Shield size={20} className="text-aethelgard-blue" />
                    <h3 className="text-white/90 font-outfit font-bold tracking-tight">Risk Management</h3>
                </div>
                {onToggleCollapse && (
                    <button
                        onClick={onToggleCollapse}
                        className="p-1.5 hover:bg-white/5 rounded-md transition-all"
                        title="Collapse panel"
                    >
                        <ChevronLeft size={16} className="text-white/50 hover:text-white/70" />
                    </button>
                )}
            </div>

            {/* Risk Gauge */}
            <div className="mb-6">
                <div className="flex justify-between text-xs mb-2">
                    <span className="text-white/50 uppercase tracking-widest font-bold text-[10px]">Total Account Risk</span>
                    <span className={`font-bold ${getRiskTextColor()}`}>
                        {(summary?.risk_percentage || 0).toFixed(1)}% / {summary?.max_allowed_risk_pct || 0}%
                    </span>
                </div>
                <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                    <div
                        className={`h-full transition-all duration-500 ${getRiskColor()}`}
                        style={{ width: `${Math.min(((summary?.risk_percentage || 0) / (summary?.max_allowed_risk_pct || 1)) * 100, 100)}%` }}
                    />
                </div>
            </div>

            {/* Total Risk Amount */}
            <div className="mb-6 p-4 bg-white/[0.02] border border-white/10 rounded-lg">
                <div className="text-[10px] text-white/50 uppercase font-bold tracking-widest mb-1">Total Risk Exposure</div>
                <div className="text-2xl font-outfit font-bold text-orange-400">
                    ${(summary?.total_risk_usd || 0).toFixed(2)}
                </div>
                <div className="flex items-center justify-between mt-2">
                    <div className="text-xs text-white/40">
                        of ${(summary?.account_balance || 0).toFixed(2)} balance
                    </div>
                    {/* Balance source indicator */}
                    <div
                        className="flex items-center gap-1.5 group cursor-help"
                        title={`${balanceIndicator.label} - Last update: ${new Date(summary.balance_metadata?.last_update || '').toLocaleTimeString()}`}
                    >
                        <div className={`w-1.5 h-1.5 rounded-full ${balanceIndicator.dotColor} animate-pulse`} />
                        <span className={`text-[10px] ${balanceIndicator.color} opacity-70 group-hover:opacity-100 transition-opacity`}>
                            {balanceIndicator.icon}
                        </span>
                    </div>
                </div>
            </div>

            {/* Risk Distribution by Asset */}
            <div className="mb-6">
                <div className="text-[10px] text-white/50 uppercase font-bold tracking-widest mb-3">Risk Distribution</div>
                <div className="space-y-2">
                    {Object.entries(summary.positions_by_asset).map(([type, data]) => (
                        data.count > 0 && (
                            <div key={type} className="flex items-center justify-between text-sm p-2 bg-white/[0.02] rounded">
                                <div className="flex items-center gap-2">
                                    <div className={`w-2 h-2 rounded-full ${type === 'forex' ? 'bg-blue-400' :
                                            type === 'metal' ? 'bg-yellow-400' :
                                                type === 'crypto' ? 'bg-purple-400' :
                                                    'bg-gray-400'
                                        }`} />
                                    <span className="text-white/70 capitalize font-medium">{type}</span>
                                </div>
                                <div className="flex items-center gap-3">
                                    <span className="text-white/40 text-xs">{data.count} pos</span>
                                    <span className="font-mono font-bold text-white/80">${(data.risk || 0).toFixed(0)}</span>
                                </div>
                            </div>
                        )
                    ))}
                </div>
            </div>

            {/* Warnings */}
            {summary.warnings.length > 0 && (
                <div className="space-y-2">
                    <div className="text-[10px] text-white/50 uppercase font-bold tracking-widest mb-2">Alerts</div>
                    {summary.warnings.map((warning, i) => (
                        <div
                            key={i}
                            className="flex items-start gap-2 p-3 bg-yellow-500/10 border border-yellow-500/20 rounded text-xs"
                        >
                            <AlertCircle size={14} className="text-yellow-400 flex-shrink-0 mt-0.5" />
                            <span className="text-yellow-300/90 leading-relaxed">{warning}</span>
                        </div>
                    ))}
                </div>
            )}

            {/* Safe State Message */}
            {summary.warnings.length === 0 && (
                <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/20 rounded text-xs">
                    <TrendingUp size={14} className="text-green-400" />
                    <span className="text-green-300/90">Risk within acceptable limits</span>
                </div>
            )}
        </GlassPanel>
    );
}
