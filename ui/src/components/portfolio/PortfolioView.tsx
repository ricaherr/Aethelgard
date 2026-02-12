import { useEffect, useState } from 'react';
import { RiskSummary as RiskSummaryType, PositionMetadata } from '../../types/aethelgard';
import { RiskSummary } from './RiskSummary';
import { ActivePositions } from './ActivePositions';

export function PortfolioView() {
    const [positions, setPositions] = useState<PositionMetadata[]>([]);
    const [riskSummary, setRiskSummary] = useState<RiskSummaryType | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchPortfolioData = async () => {
        try {
            console.log('[Portfolio] Fetching positions...');
            
            // Fetch positions
            const positionsRes = await fetch('/api/positions/open');
            console.log('[Portfolio] Positions response status:', positionsRes.status);
            const positionsData = await positionsRes.json();
            console.log('[Portfolio] Positions data:', positionsData);
            setPositions(positionsData.positions || []);

            // Fetch risk summary (includes real-time balance from MT5 if connected)
            console.log('[Portfolio] Fetching risk summary...');
            const riskRes = await fetch('/api/risk/summary');
            console.log('[Portfolio] Risk response status:', riskRes.status);
            const riskData = await riskRes.json();
            console.log('[Portfolio] Risk data:', riskData);
            setRiskSummary(riskData);

            console.log('[Portfolio] Data loaded successfully');
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
            {/* Left Panel - Risk Summary */}
            <div className="w-80 flex-shrink-0">
                {riskSummary && <RiskSummary summary={riskSummary} />}
            </div>

            {/* Right Panel - Active Positions */}
            <div className="flex-1">
                <ActivePositions positions={positions} />
            </div>
        </div>
    );
}
