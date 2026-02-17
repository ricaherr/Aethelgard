import React, { useState, useEffect } from 'react';
import { LayoutGrid, List, Map, BarChart3, Settings, ChevronUp, ChevronDown } from 'lucide-react';
import InstrumentAnalysisPanel from './InstrumentAnalysisPanel';
import ScannerStatusMonitor from './ScannerStatusMonitor';
import RegimeTimeline from './RegimeTimeline';
import InstrumentChartWithIndicators from './InstrumentChartWithIndicators';
import StrategyExplorer from './StrategyExplorer';
import SignalTrace from './SignalTrace';
import { FilterPanel } from './FilterPanel';
import { NotificationCenter } from './NotificationCenter';
import { SignalFeed } from './SignalFeed';
import HeatmapView from './HeatmapView';
import MetricWidget from './MetricWidget';
import TopOpportunities from './TopOpportunities';
import InfoTooltip from './InfoTooltip';
import { useHeatmapData } from '../../hooks/useHeatmapData';

const DEFAULT_SYMBOL = 'EURUSD';

type ViewMode = 'feed' | 'heatmap' | 'grid' | 'overview' | 'strategies' | 'trace';

const AnalysisPage: React.FC = () => {
  const [symbol, setSymbol] = useState<string>(DEFAULT_SYMBOL);
  const [selectedSignalId, setSelectedSignalId] = useState<string>('');

  // Chart Context State
  // Chart Context State
  const [selectedSignal, setSelectedSignal] = useState<any | null>(null);
  const [showContextPanel, setShowContextPanel] = useState(true);

  // Estado de filtros
  const [activeFilters, setActiveFilters] = useState({
    probability: [],
    time: [],
    regime: [],
    strategy: [],
    symbols: [],
    timeframes: [],
    category: [],
    status: [],
    limit: 100
  });

  // View mode con persistencia en localStorage (dato NO sensible)
  const { data: heatmapData, loading: heatmapLoading } = useHeatmapData();

  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    const saved = localStorage.getItem('aethelgard_analysis_view');
    return (saved as ViewMode) || 'feed';
  });

  // Persistir view mode en localStorage cuando cambia
  useEffect(() => {
    localStorage.setItem('aethelgard_analysis_view', viewMode);
  }, [viewMode]);

  // Cargar preferencias del usuario desde DB
  useEffect(() => {
    fetchUserPreferences();
  }, []);

  const fetchUserPreferences = async () => {
    try {
      const response = await fetch('/api/user/preferences?user_id=default');
      const prefs = await response.json();

      // Restaurar filtros activos si existen, preservando defaults nuevos (como limit)
      if (prefs.active_filters) {
        setActiveFilters(prev => ({
          ...prev,
          ...prefs.active_filters,
          // Ensure limit exists if not in prefs
          limit: prefs.active_filters.limit || prev.limit || 100
        }));
      }
    } catch (error) {
      console.error('Error fetching user preferences:', error);
    }
  };

  const handleFiltersChange = async (newFilters: any) => {
    setActiveFilters(newFilters);

    // Persistir filtros en DB
    try {
      await fetch('/api/user/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'default',
          active_filters: newFilters
        })
      });
    } catch (error) {
      console.error('Error saving filters:', error);
    }
  };

  const handleExecuteSignal = (signalId: string) => {
    console.log('Execute signal:', signalId);
    // TODO: Implementar ejecución de señal
  };

  const handleViewChart = (signal: any) => {
    setSymbol(signal.symbol);
    setSelectedSignal(signal);
    setViewMode('overview');
    // Auto-collapse context on signal view
    setShowContextPanel(false);
  };

  const handleViewTrace = (signalId: string) => {
    setSelectedSignalId(signalId);
    setViewMode('trace');
  };

  const tabs = [
    { id: 'feed', label: 'Feed', icon: List },
    { id: 'heatmap', label: 'Heatmap', icon: Map },
    { id: 'grid', label: 'Grid', icon: LayoutGrid },
    { id: 'overview', label: 'Overview', icon: BarChart3 },
    { id: 'strategies', label: 'Strategies', icon: Settings },
    { id: 'trace', label: 'Trace', icon: Map }
  ];

  const isFocusMode = viewMode === 'overview';

  return (
    <div className={`bg-gray-900 ${isFocusMode ? 'h-full w-full flex flex-col overflow-hidden rounded-xl border border-gray-800' : 'min-h-full'}`}>
      {/* Header - Hidden in Focus Mode */}
      {!isFocusMode && (
        <>
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-2xl font-bold text-white">Analysis Hub</h1>
            <NotificationCenter />
          </div>

          {/* Dashboard Section (Metrics & Alpha Opportunities) */}
          <div className="flex flex-col xl:flex-row gap-4 mb-4">
            <div className="flex-1">
              <MetricWidget data={heatmapData} loading={heatmapLoading} />
            </div>
            <div className="xl:w-auto">
              <TopOpportunities
                data={heatmapData}
                loading={heatmapLoading}
                onViewChart={handleViewChart}
              />
            </div>
          </div>
        </>
      )}

      {/* Focus Mode Back Button & Title - Fixed Height Header */}
      {isFocusMode && (
        <div className="flex-shrink-0 px-4 py-2 border-b border-gray-800 flex items-center justify-between bg-gray-900 z-20">
          <button
            onClick={() => setViewMode('feed')}
            className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
          >
            <ChevronDown className="rotate-90" size={20} />
            <span className="font-semibold text-sm">Volver</span>
          </button>
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-bold text-white">{symbol} Analysis</h1>
          </div>
        </div>
      )}

      {/* Tabs - Hidden in focus mode */}
      {!isFocusMode && (
        <div className="flex gap-2 mb-6">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setViewMode(tab.id as ViewMode)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${viewMode === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                  }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>
      )}

      {/* Main Content Area */}
      {/* If focus mode: flex-1 min-h-0 to allow shrinking. If not: just block. */}
      {isFocusMode ? (
        <div className="flex-1 flex min-h-0 overflow-hidden relative">
          {/* Chart Area - Takes all space, shrinks when context panel opens */}
          <div className="flex-1 flex flex-col min-h-0 relative">
            {/* The Chart Component Wrapper */}
            <div className="flex-1 min-h-0 relative w-full">
              <InstrumentChartWithIndicators
                symbol={symbol}
                selectedSignal={selectedSignal}
              />
            </div>

            {/* Context Panel - Sits below chart, pushes it up when open */}
            <div className="flex-shrink-0 w-full bg-gray-900 border-t border-gray-800 z-10">
              {/* Toggle Button Bar */}
              <div className="flex justify-between items-center px-4 py-1 bg-gray-800/50 cursor-pointer hover:bg-gray-800 transition-colors"
                onClick={() => setShowContextPanel(!showContextPanel)}>
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Market Analysis & Context</span>
                <div className="flex items-center gap-2 text-gray-400">
                  <span className="text-xs">{showContextPanel ? 'Ocultar' : 'Mostrar'}</span>
                  {showContextPanel ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                </div>
              </div>

              {/* Collapsible Content */}
              {showContextPanel && (
                <div className="h-[300px] overflow-y-auto p-4 border-t border-gray-800/30">
                  <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                    <div className="xl:col-span-2 min-w-0">
                      <InstrumentAnalysisPanel symbol={symbol} />
                    </div>
                    <div className="xl:col-span-1 min-w-0">
                      <ScannerStatusMonitor />
                    </div>
                  </div>
                  <div className="mt-4 bg-gray-800/40 rounded-xl border border-gray-700 flex flex-col">
                    <div className="p-3 border-b border-gray-800 flex items-center justify-between">
                      <div className="flex items-center">
                        <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Market Regime Timeline</h3>
                      </div>
                    </div>
                    <RegimeTimeline symbol={symbol} />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* Standard Layout for other views */
        <div className="flex gap-6 h-[calc(100vh-200px)]">
          {/* Sidebar - Filtros (solo en Feed/Grid) */}
          {(viewMode === 'feed' || viewMode === 'grid') && (
            <div className="w-80 flex-shrink-0 overflow-y-auto">
              <FilterPanel
                activeFilters={activeFilters}
                onFiltersChange={handleFiltersChange}
              />
            </div>
          )}

          {/* Main Panel scrollable */}
          <div className="flex-1 overflow-y-auto pr-4 custom-scrollbar">
            {viewMode === 'feed' && (
              <SignalFeed
                filters={activeFilters}
                onExecuteSignal={handleExecuteSignal}
                onViewChart={handleViewChart}
                onViewTrace={handleViewTrace}
              />
            )}

            {viewMode === 'heatmap' && (
              <HeatmapView />
            )}

            {viewMode === 'grid' && (
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
                <h2 className="text-xl font-bold text-white mb-4">Grid Dashboard</h2>
              </div>
            )}
            {viewMode === 'strategies' && <StrategyExplorer />}

            {viewMode === 'trace' && (
              <div className="space-y-4">
                <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                  <label className="text-sm text-gray-400 mb-2 block">Signal ID:</label>
                  <input
                    type="text"
                    value={selectedSignalId}
                    onChange={(e) => setSelectedSignalId(e.target.value)}
                    placeholder="Enter signal ID"
                    className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500"
                  />
                </div>
                {selectedSignalId && <SignalTrace signalId={selectedSignalId} />}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default AnalysisPage;
