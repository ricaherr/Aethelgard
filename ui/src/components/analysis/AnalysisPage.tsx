import React, { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import InstrumentChartWithIndicators from './InstrumentChartWithIndicators';
import { FilterPanel } from './FilterPanel';
import { SignalFeed } from './SignalFeed';
import HeatmapView from './HeatmapView';
import { useToast, ToastContainer } from '../common/Toast';
import { useHeatmapData } from '../../hooks/useHeatmapData';
import { useApi } from '../../hooks/useApi';
import { useSignalReviews } from '../../hooks/useSignalReviews';
import { SignalReviewPanel } from './SignalReviewPanel';

const DEFAULT_SYMBOL = 'EURUSD';
type ViewMode = 'feed' | 'heatmap';

const AnalysisPage: React.FC = () => {
  const { apiFetch } = useApi();
  const [symbol, setSymbol] = useState<string>(DEFAULT_SYMBOL);
  const [selectedSignal, setSelectedSignal] = useState<any | null>(null);
  const [fullscreenChart, setFullscreenChart] = useState<boolean>(false);
  const [filtersPanelCollapsed, setFiltersPanelCollapsed] = useState(false);
  const toast = useToast();
  const { data: heatmapData, loading: heatmapLoading } = useHeatmapData();
  const {
    pendingReviews,
    loading: reviewLoading,
    refreshPending,
    approveReview,
    rejectReview,
  } = useSignalReviews();

  // Active Filters with localStorage persistence
  const [activeFilters, setActiveFilters] = useState(() => {
    const saved = localStorage.getItem('aethelgard_active_filters');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) {
        console.error('Error parsing saved filters:', e);
      }
    }
    return {
      probability: [],
      time: [],
      regime: [],
      strategy: [],
      symbols: [],
      timeframes: [],
      category: [],
      status: [],
      limit: 100
    };
  });

  // View mode: feed or heatmap (simplified from multiple modes)
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    const saved = localStorage.getItem('aethelgard_analysis_view');
    return (saved as ViewMode) || 'feed';
  });

  // Persist view mode
  useEffect(() => {
    localStorage.setItem('aethelgard_analysis_view', viewMode);
  }, [viewMode]);

  // Fetch and restore user preferences
  const fetchUserPreferences = useCallback(async () => {
    try {
      const response = await apiFetch('/api/user/preferences?user_id=default');
      if (response.ok) {
        const prefs = await response.json();
        if (prefs.active_filters) {
          setActiveFilters((prev: any) => ({
            ...prev,
            ...prefs.active_filters,
            limit: prefs.active_filters.limit || prev.limit || 100
          }));
        }
      }
    } catch (error) {
      console.error('[Analysis] Error fetching preferences:', error);
    }
  }, [apiFetch]);

  useEffect(() => {
    fetchUserPreferences();
  }, [fetchUserPreferences]);

  const handleFiltersChange = async (newFilters: any) => {
    setActiveFilters(newFilters);
    localStorage.setItem('aethelgard_active_filters', JSON.stringify(newFilters));

    try {
      await apiFetch('/api/user/preferences', {
        method: 'POST',
        body: JSON.stringify({
          user_id: 'default',
          active_filters: newFilters
        })
      });
    } catch (error) {
      console.error('[Analysis] Error saving filters:', error);
    }
  };  const handleExecuteSignal = async (signalId: string) => {
    try {
      const response = await apiFetch('/api/signals/execute', {
        method: 'POST',
        body: JSON.stringify({ signal_id: signalId }),
      });

      // Defensive: ensure response is valid JSON
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API Error ${response.status}: ${errorText}`);
      }

      const result = await response.json();

      // Defensive: verify result structure
      if (result && typeof result === 'object') {
        if (result.success) {
          toast.success(result.message || 'Signal executed successfully');
          if ((window as any).__signalFeedRefresh) {
            (window as any).__signalFeedRefresh();
          }
        } else {
          toast.error(result.message || 'Failed to execute signal');
        }
      } else {
        throw new Error('Invalid response format from server');
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error executing signal';
      console.error('[Analysis] Error executing signal:', errorMsg);
      toast.error(errorMsg);
    }
  };

  const handleViewChart = (signal: any) => {
    setSymbol(signal.symbol);
    setSelectedSignal(signal);
    setFullscreenChart(true);
  };

  const handleApproveReview = async (signalId: string) => {
    const result = await approveReview(signalId, 'Approved from Analysis UI');
    if (result.success) {
      const execOk = !!result.execution?.success;
      if (execOk) {
        toast.success(result.execution?.message || 'Review approved and signal executed');
      } else {
        toast.error(result.execution?.message || 'Review approved, but execution failed');
      }
      if ((window as any).__signalFeedRefresh) {
        (window as any).__signalFeedRefresh();
      }
    } else {
      toast.error(result.detail || 'Failed to approve review');
    }
  };

  const handleRejectReview = async (signalId: string) => {
    const result = await rejectReview(signalId, 'Rejected from Analysis UI');
    if (result.success) {
      toast.success(result.message || 'Review rejected');
      if ((window as any).__signalFeedRefresh) {
        (window as any).__signalFeedRefresh();
      }
    } else {
      toast.error(result.detail || 'Failed to reject review');
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#050505] overflow-hidden">
      {/* Fullscreen Chart Mode */}
      <AnimatePresence>
        {fullscreenChart && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-50 bg-[#050505] flex flex-col"
          >
            {/* Fullscreen Header */}
            <div className="flex-shrink-0 px-6 py-3 border-b border-white/10 flex items-center justify-between bg-[#050505]">
              <button
                onClick={() => setFullscreenChart(false)}
                className="flex items-center gap-2 text-white/70 hover:text-white transition-colors"
              >
                <ChevronLeft size={20} />
                <span className="text-sm font-medium">Back</span>
              </button>
              <h2 className="text-lg font-bold text-white">{symbol} Analysis</h2>
              <div className="w-20" /> {/* Spacer for centering */}
            </div>

            {/* Chart Area - Full viewport */}
            <div className="flex-1 min-h-0">
              <InstrumentChartWithIndicators
                symbol={symbol}
                selectedSignal={selectedSignal}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Normal Layout */}
      {!fullscreenChart && (
        <>
          {/* Header */}
          <div className="flex-shrink-0 px-6 py-4 border-b border-white/10">
            <h1 className="text-2xl font-bold text-white">Analysis Engine</h1>
            <p className="text-white/50 text-sm mt-1">Real-time signal flow & market insights</p>
          </div>

          {/* V iews Toggle */}
          <div className="flex-shrink-0 px-6 py-3 flex gap-2 bg-white/[0.02] border-b border-white/10">
            <motion.button
              whileHover={{ y: -2 }}
              whileTap={{ y: 0 }}
              onClick={() => setViewMode('feed')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                viewMode === 'feed'
                  ? 'bg-aethelgard-blue text-white shadow-lg shadow-aethelgard-blue/20'
                  : 'text-white/50 hover:text-white/70'
              }`}
            >
              Signal Feed
            </motion.button>
            <motion.button
              whileHover={{ y: -2 }}
              whileTap={{ y: 0 }}
              onClick={() => setViewMode('heatmap')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                viewMode === 'heatmap'
                  ? 'bg-aethelgard-blue text-white shadow-lg shadow-aethelgard-blue/20'
                  : 'text-white/50 hover:text-white/70'
              }`}
            >
              Heatmap
            </motion.button>
          </div>

          {/* Main Content Area */}
          <div className="flex-1 flex gap-6 p-6 overflow-hidden">
            {/* Left Panel - Filters (Collapsible) */}
            <div
              className={`${
                filtersPanelCollapsed ? 'w-14' : 'w-80'
              } flex-shrink-0 transition-all duration-300 flex flex-col`}
            >
              <motion.button
                whileHover={{ x: 4 }}
                onClick={() => setFiltersPanelCollapsed(!filtersPanelCollapsed)}
                className="mb-3 p-2 rounded-lg bg-white/5 hover:bg-white/10 text-white/50 hover:text-white transition-colors"
                title={filtersPanelCollapsed ? 'Expand filters' : 'Collapse filters'}
              >
                {filtersPanelCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
              </motion.button>

              {!filtersPanelCollapsed && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-y-auto custom-scrollbar"
                >
                  <FilterPanel
                    activeFilters={activeFilters}
                    onFiltersChange={handleFiltersChange}
                  />
                </motion.div>
              )}
            </div>

            {/* Right Panel - Content */}
            <div className="flex-1 min-h-0 overflow-hidden">
              <AnimatePresence mode="wait">
                {viewMode === 'feed' ? (
                  <motion.div
                    key="feed"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="h-full overflow-y-auto custom-scrollbar pr-2"
                  >
                    <SignalReviewPanel
                      pendingReviews={pendingReviews}
                      loading={reviewLoading}
                      onRefresh={refreshPending}
                      onApprove={handleApproveReview}
                      onReject={handleRejectReview}
                    />
                    <SignalFeed
                      filters={activeFilters}
                      onExecuteSignal={handleExecuteSignal}
                      onViewChart={handleViewChart}
                      onViewTrace={() => {}}
                    />
                  </motion.div>
                ) : (
                  <motion.div
                    key="heatmap"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="h-full"
                  >
                    <HeatmapView />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </>
      )}

      <ToastContainer toasts={toast.toasts} onClose={toast.closeToast} />
    </div>
  );
};

export default AnalysisPage;
