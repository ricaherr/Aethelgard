import { Shield, AlertCircle, TrendingUp } from 'lucide-react';
import { RiskSummary as RiskSummaryType } from '../../types/aethelgard';
import { GlassPanel } from '../common/GlassPanel';

interface RiskSummaryProps {
    summary: RiskSummaryType;
}

export function RiskSummary({ summary }: RiskSummaryProps) {
    const riskLevel =
        summary.risk_percentage > summary.max_allowed_risk_pct * 0.9 ? 'critical' :
        summary.risk_percentage > summary.max_allowed_risk_pct * 0.7 ? 'warning' :
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

    return (
        <GlassPanel className="h-full border-white/5">
            {/* Header */}
            <div className="flex items-center gap-2 mb-6">
                <Shield size={20} className="text-aethelgard-blue" />
                <h3 className="text-white/90 font-outfit font-bold tracking-tight">Risk Management</h3>
            </div>

            {/* Risk Gauge */}
            <div className="mb-6">
                <div className="flex justify-between text-xs mb-2">
                    <span className="text-white/50 uppercase tracking-widest font-bold text-[10px]">Total Account Risk</span>
                    <span className={`font-bold ${getRiskTextColor()}`}>
                        {summary.risk_percentage.toFixed(1)}% / {summary.max_allowed_risk_pct}%
                    </span>
                </div>
                <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                    <div
                        className={`h-full transition-all duration-500 ${getRiskColor()}`}
                        style={{ width: `${Math.min((summary.risk_percentage / summary.max_allowed_risk_pct) * 100, 100)}%` }}
                    />
                </div>
            </div>

            {/* Total Risk Amount */}
            <div className="mb-6 p-4 bg-white/[0.02] border border-white/10 rounded-lg">
                <div className="text-[10px] text-white/50 uppercase font-bold tracking-widest mb-1">Total Risk Exposure</div>
                <div className="text-2xl font-outfit font-bold text-orange-400">
                    ${summary.total_risk_usd.toFixed(2)}
                </div>
                <div className="text-xs text-white/40 mt-1">
                    of ${summary.account_balance.toFixed(2)} balance
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
                                    <div className={`w-2 h-2 rounded-full ${
                                        type === 'forex' ? 'bg-blue-400' :
                                        type === 'metal' ? 'bg-yellow-400' :
                                        type === 'crypto' ? 'bg-purple-400' :
                                        'bg-gray-400'
                                    }`} />
                                    <span className="text-white/70 capitalize font-medium">{type}</span>
                                </div>
                                <div className="flex items-center gap-3">
                                    <span className="text-white/40 text-xs">{data.count} pos</span>
                                    <span className="font-mono font-bold text-white/80">${data.risk.toFixed(0)}</span>
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
