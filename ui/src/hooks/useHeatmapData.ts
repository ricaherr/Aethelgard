import { useState, useEffect, useCallback } from 'react';

export interface HeatmapData {
    symbols: string[];
    timeframes: string[];
    cells: any[];
    timestamp: string;
}

const timeframeWeights: Record<string, number> = {
    'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
    'H1': 60, 'H4': 240, 'D1': 1440, 'W1': 10080, 'MN': 43200
};

const sortTimeframes = (tfs: string[]) => {
    return [...tfs].sort((a, b) => (timeframeWeights[a] || 999999) - (timeframeWeights[b] || 999999));
};

export const useHeatmapData = (refreshInterval: number = 10000) => {
    const [data, setData] = useState<HeatmapData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchHeatmap = useCallback(async () => {
        try {
            const response = await fetch('/api/analysis/heatmap');
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to fetch heatmap');
            }
            const result = await response.json();

            if (result.timeframes) {
                result.timeframes = sortTimeframes(result.timeframes);
            }

            setData(result);
            setError(null);
        } catch (err: any) {
            console.error('Heatmap fetch error:', err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchHeatmap();
        const interval = setInterval(fetchHeatmap, refreshInterval);
        return () => clearInterval(interval);
    }, [fetchHeatmap, refreshInterval]);

    return { data, loading, error, refetch: fetchHeatmap };
};
