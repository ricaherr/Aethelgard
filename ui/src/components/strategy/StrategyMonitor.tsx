import React from 'react';
import { useStrategyMonitor } from '../../hooks/useStrategyMonitor';
import './StrategyMonitor.css';

/**
 * Real-time Strategy Monitoring Dashboard
 * 
 * Displays live metrics for all strategies:
 * - Status (LIVE, QUARANTINE, SHADOW)
 * - Drawdown % (DD%)
 * - Consecutive Losses (CL)
 * - Win Rate (WR%)
 * - Profit Factor (PF)
 * - Online indicator
 * 
 * Updates every 5 seconds via WebSocket
 * RULE T1: Tenant-isolated (via token)
 */
export const StrategyMonitor: React.FC = () => {
  const { strategies, loading, error, isConnected } = useStrategyMonitor();

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'LIVE':
        return 'status-live';
      case 'QUARANTINE':
        return 'status-quarantine';
      case 'SHADOW':
        return 'status-shadow';
      default:
        return 'status-unknown';
    }
  };

  const getStatusLabel = (status: string): string => {
    switch (status) {
      case 'LIVE':
        return '🟢 LIVE';
      case 'QUARANTINE':
        return '🔴 QUARANTINE';
      case 'SHADOW':
        return '🟡 SHADOW';
      default:
        return '⚪ UNKNOWN';
    }
  };

  return (
    <div className="strategy-monitor">
      <div className="monitor-header">
        <h2>Strategy Monitor</h2>
        <div className="connection-status">
          {isConnected ? (
            <span className="connected">● Connected</span>
          ) : (
            <span className="disconnected">○ Disconnected</span>
          )}
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <p>Error: {error}</p>
        </div>
      )}

      {loading && (
        <div className="loading">
          <p>Loading strategy metrics...</p>
        </div>
      )}

      {!loading && strategies.length === 0 && !error && (
        <div className="empty-state">
          <p>No strategies found</p>
        </div>
      )}

      {strategies.length > 0 && (
        <div className="metrics-table">
          <table>
            <thead>
              <tr>
                <th>Strategy ID</th>
                <th>Status</th>
                <th>DD%</th>
                <th>CL</th>
                <th>WR%</th>
                <th>PF</th>
                <th>Trades</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((strategy) => (
                <tr key={strategy.strategy_id} className={getStatusColor(strategy.status)}>
                  <td className="strategy-id">
                    <code>{strategy.strategy_id}</code>
                  </td>
                  <td className="status">
                    {getStatusLabel(strategy.status)}
                  </td>
                  <td className="dd-pct">
                    <span className={strategy.dd_pct > 3 ? 'warning' : ''}>
                      {strategy.dd_pct.toFixed(2)}%
                    </span>
                  </td>
                  <td className="consecutive-losses">
                    {strategy.consecutive_losses > 0 ? (
                      <span className="alert">{strategy.consecutive_losses}</span>
                    ) : (
                      <span>0</span>
                    )}
                  </td>
                  <td className="win-rate">
                    {(strategy.win_rate * 100).toFixed(1)}%
                  </td>
                  <td className="profit-factor">
                    <span className={strategy.profit_factor < 1.0 ? 'warning' : ''}>
                      {strategy.profit_factor.toFixed(2)}
                    </span>
                  </td>
                  <td className="trades">
                    {strategy.trades_count || '--'}
                  </td>
                  <td className="updated">
                    <small>
                      {new Date(strategy.updated_at).toLocaleTimeString()}
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default StrategyMonitor;
