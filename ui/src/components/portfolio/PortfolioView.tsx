import { useEffect, useState } from 'react';
import { RiskSummary as RiskSummaryType, PositionMetadata } from '../../types/aethelgard';
import { RiskSummary } from './RiskSummary';
import { ActivePositions } from './ActivePositions';

export function PortfolioView() {
    const [positions, setPositions] = useState<PositionMetadata[]>([]);
    const [riskSummary, setRiskSummary] = useState<RiskSummaryType | null>(null);
    const [loading, setLoading] = useState(true);
    const [riskPanelCollapsed, setRiskPanelCollapsed] = useState(false);
    const [fullscreenTicket, setFullscreenTicket] = useState<number | null>(null);

    const fetchPortfolioData = async () => {
        try {

            // Fetch positions
            const positionsRes = await fetch('/api/positions/open');
            const positionsData = await positionsRes.json();
            setPositions(positionsData.positions || []);

            // Fetch risk summary (includes real-time balance from MT5 if connected)
            const riskRes = await fetch('/api/risk/summary');
            const riskData = await riskRes.json();
            setRiskSummary(riskData);

            setLoading(false);
        } catch (error) {
            console.error('[Portfolio] Error fetching portfolio data:', error);
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchPortfolioData();

        // Auto-refresh balance every 30s (balance updates from MT5 in real-time)
        const interval = setInterval(fetchPortfolioData, 30000);

        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="flex flex-col items-center gap-4">
                    <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-aethelgard-blue"></div>
                    <div className="text-white/50 text-sm uppercase tracking-widest">Loading Portfolio Data...</div>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full flex gap-6 p-6">
            {/* Left Panel - Risk Summary (Collapsible) */}
            <div className={`${riskPanelCollapsed || fullscreenTicket !== null ? 'w-16' : 'w-80'} flex-shrink-0 transition-all duration-300`}>
                {riskSummary && (
                    <RiskSummary
                        summary={riskSummary}
                        collapsed={riskPanelCollapsed || fullscreenTicket !== null}
                        onToggleCollapse={fullscreenTicket === null ? () => setRiskPanelCollapsed(!riskPanelCollapsed) : undefined}
                    />
                )}
            </div>

            {/* Right Panel - Active Positions */}
            <div className="flex-1">
                <ActivePositions
                    positions={positions}
                    fullscreenTicket={fullscreenTicket}
                    onFullscreenToggle={(ticket) => setFullscreenTicket(ticket)}
                />
            </div>
        </div>
    );
}
