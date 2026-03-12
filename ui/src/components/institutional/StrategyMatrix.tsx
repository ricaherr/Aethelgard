import React, { useState } from 'react';
import { motion } from 'framer-motion';

interface Strategy {
  id?: string;
  strategy_id?: string;
  status?: string;
  pnl?: number;
}

interface StrategyMatrixProps {
  strategies: Strategy[];
  anomalies: number;
}

/**
 * StrategyMatrix: Compact 2×3 grid of 6 strategies
 * - Each cell shows: Strategy ID, Status indicator, PnL
 * - Legend hidden behind (i) icon
 * - Color: Green (profit) ↔ Red (loss)
 */
export const StrategyMatrix: React.FC<StrategyMatrixProps> = ({ strategies, anomalies }) => {
  const [showLegend, setShowLegend] = useState(false);

  // Ensure 6 slots (fill with defaults if needed)
  const displayStrategies = [
    ...strategies.slice(0, 6),
    ...Array(Math.max(0, 6 - strategies.length))
      .fill(null)
      .map((_, i) => ({
        id: `EMPTY_${i}`,
        strategy_id: `—`,
        status: 'IDLE',
        pnl: 0,
      })),
  ];

  const getStatusColor = (status: string) => {
    switch ((status || 'IDLE').toUpperCase()) {
      case 'LIVE':
        return '#00D4FF';
      case 'SHADOW':
        return '#FFD700';
      case 'IDLE':
        return '#666666';
      case 'BLOCKED':
        return '#FF0066';
      default:
        return '#666666';
    }
  };

  const getPnLColor = (pnl: number | undefined) => {
    if (!pnl || pnl === 0) return '#CCCCCC';
    return pnl > 0 ? '#00FF41' : '#FF0066';
  };

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'rgba(10, 15, 35, 0.3)',
        border: '0.5px solid rgba(0, 180, 220, 0.2)',
        borderRadius: '4px',
        padding: '12px',
        gap: '8px',
        backdropFilter: 'blur(8px)',
        boxShadow: 'inset 0 0 10px rgba(0, 180, 220, 0.05)',
      }}
    >
      {/* HEADER WITH INFO ICON */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingBottom: '8px',
          borderBottom: '0.5px solid rgba(0, 180, 220, 0.1)',
        }}
      >
        <span
          style={{
            fontSize: '9px',
            fontFamily: 'monospace',
            color: '#00D4FF',
            fontWeight: 'bold',
            textTransform: 'uppercase',
            letterSpacing: '1px',
          }}
        >
          Strategy Matrix
        </span>
        <button
          onClick={() => setShowLegend(!showLegend)}
          style={{
            background: 'rgba(0, 180, 220, 0.1)',
            border: '0.5px solid rgba(0, 180, 220, 0.3)',
            color: '#00D4FF',
            width: '18px',
            height: '18px',
            borderRadius: '50%',
            cursor: 'pointer',
            fontSize: '9px',
            fontWeight: 'bold',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.2s ease',
          }}
          onMouseOver={(e) => {
            e.currentTarget.style.background = 'rgba(0, 180, 220, 0.2)';
            e.currentTarget.style.boxShadow = '0 0 8px rgba(0, 180, 220, 0.4)';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.background = 'rgba(0, 180, 220, 0.1)';
            e.currentTarget.style.boxShadow = 'none';
          }}
        >
          (i)
        </button>
      </div>

      {/* LEGEND (CONDITIONAL) */}
      {showLegend && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          style={{
            background: 'rgba(2, 2, 2, 0.6)',
            border: '0.5px solid rgba(0, 180, 220, 0.2)',
            padding: '8px',
            fontSize: '7px',
            fontFamily: 'monospace',
            color: '#666666',
            gap: '4px',
            display: 'flex',
            flexDirection: 'column',
            marginBottom: '8px',
            borderRadius: '2px',
          }}
        >
          <span>● Cyan: LIVE | ● Yellow: SHADOW | ● Gray: IDLE | ● Magenta: BLOCKED</span>
          <span>🟢 Green: Profitable | 🔴 Red: Loss | ⚪ Gray: B/E</span>
        </motion.div>
      )}

      {/* STRATEGY GRID (2×3) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gridTemplateRows: 'auto auto auto',
          gap: '8px',
          flex: 1,
        }}
      >
        {displayStrategies.slice(0, 6).map((strat, idx) => {
          const statusColor = getStatusColor(strat.status || 'IDLE');
          const pnlColor = getPnLColor(strat.pnl);
          const strategyId = strat.strategy_id || strat.id || `STRAT_${idx}`;
          const isEmpty = strategyId.startsWith('EMPTY');

          return (
            <motion.div
              key={`${strategyId}-${idx}`}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.4, delay: idx * 0.05 }}
              style={{
                background: isEmpty ? 'rgba(50, 50, 70, 0.2)' : 'rgba(10, 20, 40, 0.4)',
                border: `0.5px solid ${statusColor}40`,
                borderRadius: '3px',
                padding: '6px',
                display: 'flex',
                flexDirection: 'column',
                gap: '3px',
                minHeight: '60px',
                justifyContent: 'space-between',
                cursor: isEmpty ? 'default' : 'pointer',
                transition: 'all 0.3s ease',
              }}
              onMouseOver={(e) => {
                if (!isEmpty) {
                  e.currentTarget.style.background = 'rgba(10, 20, 40, 0.6)';
                  e.currentTarget.style.boxShadow = `0 0 8px ${statusColor}40`;
                }
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.background = isEmpty ? 'rgba(50, 50, 70, 0.2)' : 'rgba(10, 20, 40, 0.4)';
                e.currentTarget.style.boxShadow = 'none';
              }}
            >
              {/* STRATEGY IDENTIFIER */}
              <div
                style={{
                  fontSize: '8px',
                  fontFamily: 'monospace',
                  color: statusColor,
                  fontWeight: 'bold',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  whiteSpace: 'nowrap',
                  textOverflow: 'ellipsis',
                  overflow: 'hidden',
                }}
              >
                ◆ {strategyId}
              </div>

              {/* STATUS INDICATOR */}
              <div
                style={{
                  fontSize: '7px',
                  fontFamily: 'monospace',
                  color: '#999999',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}
              >
                <span
                  style={{
                    display: 'inline-block',
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: statusColor,
                    marginRight: '4px',
                  }}
                />
                {strat.status || 'IDLE'}
              </div>

              {/* PnL VALUE */}
              <div
                style={{
                  fontSize: '9px',
                  fontFamily: 'monospace',
                  color: pnlColor,
                  fontWeight: 'bold',
                  letterSpacing: '0.5px',
                }}
              >
                {strat.pnl !== undefined && strat.pnl !== 0
                  ? `${strat.pnl > 0 ? '+' : ''}$${strat.pnl.toFixed(0)}`
                  : '—'}
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* FOOTER */}
      {anomalies > 0 && (
        <div
          style={{
            fontSize: '7px',
            fontFamily: 'monospace',
            color: '#FF0066',
            padding: '4px',
            borderTop: '0.5px solid rgba(255, 0, 102, 0.2)',
            textTransform: 'uppercase',
          }}
        >
          ⚠️ {anomalies} Active Anomalies
        </div>
      )}
    </div>
  );
};
