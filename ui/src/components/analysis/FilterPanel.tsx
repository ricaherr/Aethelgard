import React, { useState } from 'react';
import { Filter, ChevronDown } from 'lucide-react';

interface FilterPanelProps {
    activeFilters: {
        probability: string[];
        time: string[];
        regime: string[];
        strategy: string[];
        symbols: string[];
        timeframes: string[];
        category: string[];
        status: string[];
        limit?: number;
    };
    onFiltersChange: (filters: any) => void;
}

const SYMBOL_CATEGORIES = {
    'forex_majors': {
        label: 'Forex Majors',
        symbols: ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD']
    },
    'forex_minors': {
        label: 'Forex Minors',
        symbols: ['EURGBP', 'EURJPY', 'EURCHF', 'EURAUD', 'EURCAD', 'GBPJPY', 'GBPCHF', 'GBPAUD']
    },
    'indices': {
        label: 'Indices',
        symbols: ['US30', 'US500', 'NAS100', 'GER40', 'UK100', 'JPN225']
    },
    'commodities': {
        label: 'Commodities',
        symbols: ['XAUUSD', 'XAGUSD', 'USOIL', 'UKOIL']
    }
};

const FILTER_OPTIONS = {
    probability: [
        { value: '90+', label: '>90%', color: 'bg-green-600' },
        { value: '80-90', label: '80-90%', color: 'bg-yellow-600' },
        { value: '70-80', label: '70-80%', color: 'bg-orange-600' }
    ],
    time: [
        { value: '15min', label: 'Last 15min' },
        { value: 'today', label: 'Today' },
        { value: 'week', label: 'This Week' }
    ],
    regime: [
        { value: 'TREND', label: 'TREND', icon: '📈' },
        { value: 'RANGE', label: 'RANGE', icon: '↔️' },
        { value: 'VOLATILITY', label: 'VOLATILITY', icon: '⚡' }
    ],
    strategy: [
        { value: 'Trifecta', label: 'Trifecta' },
        { value: 'Oliver Velez', label: 'Oliver Velez' },
        { value: 'RSI_MACD', label: 'RSI + MACD' }
    ],
    timeframes: [
        { value: 'M1', label: 'M1' },
        { value: 'M5', label: 'M5' },
        { value: 'M15', label: 'M15' },
        { value: 'H1', label: 'H1' }
    ],
    status: [
        { value: 'PENDING', label: 'Active', color: 'bg-emerald-600' },
        { value: 'EXECUTED', label: 'Executed', color: 'bg-blue-600' },
        { value: 'EXPIRED', label: 'Expired', color: 'bg-orange-600' },
        { value: 'REJECTED', label: 'Rejected', color: 'bg-red-600' }
    ]
};

export const FilterPanel: React.FC<FilterPanelProps> = ({
    activeFilters,
    onFiltersChange
}) => {
    const [isExpanded, setIsExpanded] = useState(true);
    const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

    const toggleFilter = (category: keyof typeof activeFilters, value: string) => {
        // Skip for non-array filters like limit
        if (category === 'limit') return;

        const current = activeFilters[category] as string[] || [];
        const updated = current.includes(value)
            ? current.filter(v => v !== value)
            : [...current, value];

        onFiltersChange({
            ...activeFilters,
            [category]: updated
        });
    };

    const toggleCategory = (categoryKey: string) => {
        const categorySymbols = SYMBOL_CATEGORIES[categoryKey as keyof typeof SYMBOL_CATEGORIES].symbols;
        const currentSymbols = activeFilters.symbols || [];

        // Check if all symbols in category are selected
        const allSelected = categorySymbols.every(sym => currentSymbols.includes(sym));

        let updatedSymbols;
        if (allSelected) {
            // Deselect all symbols in this category
            updatedSymbols = currentSymbols.filter(sym => !categorySymbols.includes(sym));
        } else {
            // Select all symbols in this category
            updatedSymbols = [...new Set([...currentSymbols, ...categorySymbols])];
        }

        onFiltersChange({
            ...activeFilters,
            symbols: updatedSymbols
        });
    };

    const clearAllFilters = () => {
        onFiltersChange({
            probability: [],
            time: [],
            regime: [],
            strategy: [],
            symbols: [],
            timeframes: [],
            category: [],
            status: ['PENDING']
        });
    };

    const activeCount = Object.values(activeFilters).flat().length;

    return (
        <div className="bg-gray-800 rounded-lg border border-gray-700">
            <div className="flex items-center justify-between p-4 border-b border-gray-700">
                <div className="flex items-center gap-2">
                    <Filter className="w-5 h-5 text-blue-400" />
                    <h3 className="font-semibold text-white">Filters</h3>
                    {activeCount > 0 && (
                        <span className="px-2 py-0.5 bg-blue-600 text-white text-xs rounded-full">
                            {activeCount}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    {activeCount > 0 && (
                        <button
                            onClick={clearAllFilters}
                            className="text-xs text-gray-400 hover:text-white transition-colors"
                        >
                            Clear All
                        </button>
                    )}
                    <button
                        onClick={() => setIsExpanded(!isExpanded)}
                        className="text-gray-400 hover:text-white transition-colors"
                    >
                        {isExpanded ? '−' : '+'}
                    </button>
                </div>
            </div>

            {isExpanded && (
                <div className="p-4 space-y-4">
                    {/* Status */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 mb-2 block">
                            🚦 SIGNAL STATUS
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.status.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('status', option.value)}
                                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${activeFilters.status?.includes(option.value)
                                        ? `${option.color} text-white`
                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                        }`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Probability */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 mb-2 block">
                            🎯 PROBABILITY
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.probability.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('probability', option.value)}
                                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${activeFilters.probability?.includes(option.value)
                                        ? `${option.color} text-white`
                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                        }`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Time */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 mb-2 block">
                            ⏱️ TIME
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.time.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('time', option.value)}
                                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${activeFilters.time?.includes(option.value)
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                        }`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Regime */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 mb-2 block">
                            📊 REGIME
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.regime.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('regime', option.value)}
                                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${activeFilters.regime?.includes(option.value)
                                        ? 'bg-purple-600 text-white'
                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                        }`}
                                >
                                    {option.icon} {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Strategy */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 mb-2 block">
                            🎲 STRATEGY
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.strategy.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('strategy', option.value)}
                                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${activeFilters.strategy?.includes(option.value)
                                        ? 'bg-indigo-600 text-white'
                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                        }`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Symbols - Hierarchical */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 mb-2 block">
                            💱 SYMBOLS
                        </label>
                        <div className="space-y-2">
                            {Object.entries(SYMBOL_CATEGORIES).map(([key, category]) => {
                                const categorySymbols = category.symbols;
                                const selectedInCategory = categorySymbols.filter(sym =>
                                    activeFilters.symbols?.includes(sym)
                                ).length;
                                const allSelected = selectedInCategory === categorySymbols.length;
                                const someSelected = selectedInCategory > 0 && !allSelected;

                                return (
                                    <div key={key} className="border border-gray-700 rounded-lg">
                                        <button
                                            onClick={() => setExpandedCategory(expandedCategory === key ? null : key)}
                                            className="w-full flex items-center justify-between p-2 hover:bg-gray-750 rounded-lg transition-colors"
                                        >
                                            <div className="flex items-center gap-2">
                                                <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${expandedCategory === key ? 'rotate-180' : ''
                                                    }`} />
                                                <span className="text-sm font-medium text-white">{category.label}</span>
                                                {selectedInCategory > 0 && (
                                                    <span className="px-1.5 py-0.5 bg-cyan-600 text-white text-xs rounded">
                                                        {selectedInCategory}
                                                    </span>
                                                )}
                                            </div>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    toggleCategory(key);
                                                }}
                                                className={`px-2 py-1 rounded text-xs font-medium transition-all ${allSelected
                                                    ? 'bg-cyan-600 text-white'
                                                    : someSelected
                                                        ? 'bg-cyan-600/50 text-white'
                                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                                    }`}
                                            >
                                                {allSelected ? 'All' : someSelected ? 'Some' : 'None'}
                                            </button>
                                        </button>

                                        {expandedCategory === key && (
                                            <div className="p-2 pt-0 grid grid-cols-2 gap-1">
                                                {categorySymbols.map(symbol => (
                                                    <button
                                                        key={symbol}
                                                        onClick={() => toggleFilter('symbols', symbol)}
                                                        className={`px-2 py-1 rounded text-xs font-medium transition-all ${activeFilters.symbols?.includes(symbol)
                                                            ? 'bg-cyan-600 text-white'
                                                            : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                                            }`}
                                                    >
                                                        {symbol}
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Timeframes */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 mb-2 block">
                            ⏰ TIMEFRAMES
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.timeframes.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('timeframes', option.value)}
                                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${activeFilters.timeframes?.includes(option.value)
                                        ? 'bg-teal-600 text-white'
                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                        }`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    {/* Limit */}
                    <div>
                        <label className="text-xs font-semibold text-gray-400 mb-2 block">
                            🔢 LIMIT
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {[100, 200, 500, 1000].map(limit => (
                                <button
                                    key={limit}
                                    onClick={() => onFiltersChange({ ...activeFilters, limit: limit })}
                                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${activeFilters.limit === limit
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                        }`}
                                >
                                    {limit}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
