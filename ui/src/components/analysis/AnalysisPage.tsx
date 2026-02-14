
import React, { useState } from 'react';
import SymbolSelector from './SymbolSelector';
import InstrumentAnalysisPanel from './InstrumentAnalysisPanel';
import ScannerStatusMonitor from './ScannerStatusMonitor';
import RegimeTimeline from './RegimeTimeline';
import InstrumentChartWithIndicators from './InstrumentChartWithIndicators';
import StrategyExplorer from './StrategyExplorer';
import SignalTrace from './SignalTrace';


const DEFAULT_SYMBOL = 'EURUSD';

const AnalysisPage: React.FC = () => {
  const [symbol, setSymbol] = useState<string>(DEFAULT_SYMBOL);
  const [activeTab, setActiveTab] = useState<'overview' | 'strategies' | 'trace'>('overview');
  const [selectedSignalId, setSelectedSignalId] = useState<string>('');

  return (
    <div className="analysis-dashboard">
      <SymbolSelector symbol={symbol} setSymbol={setSymbol} />

      {/* Tabs */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'overview'
              ? 'bg-aethelgard-green/20 text-aethelgard-green border border-aethelgard-green/30'
              : 'bg-white/5 text-white/60 hover:bg-white/10'
            }`}
        >
          Vista General
        </button>
        <button
          onClick={() => setActiveTab('strategies')}
          className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'strategies'
              ? 'bg-aethelgard-blue/20 text-aethelgard-blue border border-aethelgard-blue/30'
              : 'bg-white/5 text-white/60 hover:bg-white/10'
            }`}
        >
          Estrategias
        </button>
        <button
          onClick={() => setActiveTab('trace')}
          className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'trace'
              ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
              : 'bg-white/5 text-white/60 hover:bg-white/10'
            }`}
        >
          Trazabilidad
        </button>
      </div>

      {/* Content */}
      {activeTab === 'overview' && (
        <div className="analysis-panels-grid">
          <InstrumentAnalysisPanel symbol={symbol} />
          <ScannerStatusMonitor />
          <RegimeTimeline symbol={symbol} />
          <InstrumentChartWithIndicators symbol={symbol} />
        </div>
      )}

      {activeTab === 'strategies' && (
        <div className="analysis-panels-grid">
          <StrategyExplorer />
        </div>
      )}

      {activeTab === 'trace' && (
        <div className="analysis-panels-grid">
          <div className="mb-4">
            <label className="text-sm text-white/60 mb-2 block">Signal ID:</label>
            <input
              type="text"
              value={selectedSignalId}
              onChange={(e) => setSelectedSignalId(e.target.value)}
              placeholder="Ingresa el ID de la señal"
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:border-aethelgard-green"
            />
          </div>
          {selectedSignalId && <SignalTrace signalId={selectedSignalId} />}
          {!selectedSignalId && (
            <div className="text-white/40 text-center py-8">
              Ingresa un Signal ID para ver su trazabilidad
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AnalysisPage;
