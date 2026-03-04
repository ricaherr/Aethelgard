import React, { useState } from 'react';
import { Filter, ChevronDown, X } from 'lucide-react';

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
        <div className="bg-gradient-to-b from-gray-900/80 to-gray-900/40 rounded-xl border border-gray-800/60 backdrop-blur-md shadow-lg hover:border-gray-700/60 transition-border duration-300">
            <div className="flex items-center justify-between p-5 border-b border-gray-800/40">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-500/15 rounded-lg backdrop-blur-sm border border-blue-500/20">
                        <Filter className="w-5 h-5 text-blue-400" />
                    </div>
                    <div>
                        <h3 className="font-bold text-white text-sm tracking-wide">Filters</h3>
                        <p className="text-[11px] text-gray-500 mt-0.5">Refine signals</p>
                    </div>
                    {activeCount > 0 && (
                        <span className="ml-2 px-2.5 py-1 bg-gradient-to-r from-blue-600 to-blue-500 text-white text-xs font-bold rounded-full shadow-lg shadow-blue-500/20">
                            {activeCount}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    {activeCount > 0 && (
                        <button
                            onClick={clearAllFilters}
                            className="text-xs text-gray-400 hover:text-red-400 transition-colors duration-200 font-semibold flex items-center gap-1 px-2 py-1 rounded-lg hover:bg-red-500/10"
                        >
                            <X className="w-3.5 h-3.5" />
                            Clear
                        </button>
                    )}
                    <button
                        onClick={() => setIsExpanded(!isExpanded)}
                        className={`text-gray-400 hover:text-white transition-all duration-300 p-1.5 rounded-lg hover:bg-gray-800/50 ${isExpanded ? 'text-blue-400' : ''}`}
                    >
                        <ChevronDown className={`w-5 h-5 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`} />
                    </button>
                </div>
            </div>

            {isExpanded && (
                <div className="p-5 space-y-6 animate-in fade-in slide-in-from-top-2 duration-300">
                    {/* Status */}
                    <div className="space-y-3">
                        <label className="text-xs font-bold text-gray-300 mb-2 block uppercase tracking-wide">
                            🚦 Signal Status
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.status.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('status', option.value)}
                                    className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${activeFilters.status?.includes(option.value)
                                        ? `${option.color} text-white shadow-lg scale-105`
                                        : 'bg-gray-800/60 text-gray-300 hover:bg-gray-700/80 border border-gray-700/40'
                                        }`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Probability */}
                    <div className="space-y-3">
                        <label className="text-xs font-bold text-gray-300 mb-2 block uppercase tracking-wide">
                            🎯 Probability
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.probability.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('probability', option.value)}
                                    className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${activeFilters.probability?.includes(option.value)
                                        ? `${option.color} text-white shadow-lg scale-105`
                                        : 'bg-gray-800/60 text-gray-300 hover:bg-gray-700/80 border border-gray-700/40'
                                        }`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Time */}
                    <div className="space-y-3">
                        <label className="text-xs font-bold text-gray-300 mb-2 block uppercase tracking-wide">
                            ⏱️ Time
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.time.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('time', option.value)}
                                    className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${activeFilters.time?.includes(option.value)
                                        ? 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-lg scale-105'
                                        : 'bg-gray-800/60 text-gray-300 hover:bg-gray-700/80 border border-gray-700/40'
                                        }`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Regime */}
                    <div className="space-y-3">
                        <label className="text-xs font-bold text-gray-300 mb-2 block uppercase tracking-wide">
                            📊 Regime
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.regime.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('regime', option.value)}
                                    className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${activeFilters.regime?.includes(option.value)
                                        ? 'bg-gradient-to-r from-purple-600 to-purple-500 text-white shadow-lg scale-105'
                                        : 'bg-gray-800/60 text-gray-300 hover:bg-gray-700/80 border border-gray-700/40'
                                        }`}
                                >
                                    {option.icon} {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Strategy */}
                    <div className="space-y-3">
                        <label className="text-xs font-bold text-gray-300 mb-2 block uppercase tracking-wide">
                            🎲 Strategy
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.strategy.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('strategy', option.value)}
                                    className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${activeFilters.strategy?.includes(option.value)
                                        ? 'bg-gradient-to-r from-indigo-600 to-indigo-500 text-white shadow-lg scale-105'
                                        : 'bg-gray-800/60 text-gray-300 hover:bg-gray-700/80 border border-gray-700/40'
                                        }`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Symbols - Hierarchical */}
                    <div className="space-y-3">
                        <label className="text-xs font-bold text-gray-300 mb-2 block uppercase tracking-wide">
                            💱 Symbols
                        </label>
                        <div className="space-y-2 max-h-64 overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-gray-800">
                            {Object.entries(SYMBOL_CATEGORIES).map(([key, category]) => {
                                const categorySymbols = category.symbols;
                                const selectedInCategory = categorySymbols.filter(sym =>
                                    activeFilters.symbols?.includes(sym)
                                ).length;
                                const allSelected = selectedInCategory === categorySymbols.length;
                                const someSelected = selectedInCategory > 0 && !allSelected;

                                return (
                                    <div key={key} className="bg-gray-800/40 border border-gray-700/60 rounded-lg overflow-hidden hover:border-gray-600/80 transition-border duration-200">
                                        <button
                                            onClick={() => setExpandedCategory(expandedCategory === key ? null : key)}
                                            className="w-full flex items-center justify-between p-3 hover:bg-gray-800/60 rounded-lg transition-colors duration-200"
                                        >
                                            <div className="flex items-center gap-2">
                                                <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform duration-300 ${expandedCategory === key ? 'rotate-180' : ''
                                                    }`} />
                                                <span className="text-sm font-semibold text-white">{category.label}</span>
                                                {selectedInCategory > 0 && (
                                                    <span className="px-2 py-0.5 bg-cyan-600/30 text-cyan-300 text-xs rounded-full border border-cyan-500/30 font-bold">
                                                        {selectedInCategory}/{categorySymbols.length}
                                                    </span>
                                                )}
                                            </div>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    toggleCategory(key);
                                                }}
                                                className={`px-3 py-1.5 rounded text-xs font-bold transition-all duration-200 ${allSelected
                                                    ? 'bg-gradient-to-r from-cyan-600 to-cyan-500 text-white shadow-lg shadow-cyan-500/20'
                                                    : someSelected
                                                        ? 'bg-cyan-600/60 text-cyan-100 border border-cyan-500/40'
                                                        : 'bg-gray-700/50 text-gray-300 hover:bg-gray-600/60 border border-gray-600/40'
                                                    }`}
                                            >
                                                {allSelected ? 'All' : someSelected ? 'Some' : 'None'}
                                            </button>
                                        </button>

                                        {expandedCategory === key && (
                                            <div className="p-3 pt-2 grid grid-cols-2 gap-2 bg-gray-900/40 border-t border-gray-700/40 animate-in slide-in-from-top-1 duration-200">
                                                {categorySymbols.map(symbol => (
                                                    <button
                                                        key={symbol}
                                                        onClick={() => toggleFilter('symbols', symbol)}
                                                        className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all duration-200 ${activeFilters.symbols?.includes(symbol)
                                                            ? 'bg-gradient-to-r from-cyan-600 to-cyan-500 text-white shadow-lg shadow-cyan-500/20 scale-105'
                                                            : 'bg-gray-700/60 text-gray-300 hover:bg-gray-600/80 border border-gray-600/40 hover:border-gray-500/60'
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
                    <div className="space-y-3">
                        <label className="text-xs font-bold text-gray-300 mb-2 block uppercase tracking-wide">
                            ⏰ Timeframes
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_OPTIONS.timeframes.map(option => (
                                <button
                                    key={option.value}
                                    onClick={() => toggleFilter('timeframes', option.value)}
                                    className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${activeFilters.timeframes?.includes(option.value)
                                        ? 'bg-gradient-to-r from-teal-600 to-teal-500 text-white shadow-lg scale-105'
                                        : 'bg-gray-800/60 text-gray-300 hover:bg-gray-700/80 border border-gray-700/40'
                                        }`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Limit */}
                    <div className="space-y-3 pb-2">
                        <label className="text-xs font-bold text-gray-300 mb-2 block uppercase tracking-wide">
                            🔢 Result Limit
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {[100, 200, 500, 1000].map(limit => (
                                <button
                                    key={limit}
                                    onClick={() => onFiltersChange({ ...activeFilters, limit: limit })}
                                    className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${activeFilters.limit === limit
                                        ? 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-lg scale-105'
                                        : 'bg-gray-800/60 text-gray-300 hover:bg-gray-700/80 border border-gray-700/40'
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
