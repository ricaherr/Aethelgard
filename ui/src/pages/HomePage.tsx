import React, { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useApi } from '../hooks/useApi';

interface HomePageProps {
  token?: string;
}

/**
 * HomePage Component: Simple HTTP polling for system telemetry
 * Pattern: Identical to PortfolioView and AnalysisPage (proven working)
 * Data Source: GET /api/system/telemetry (30s polling interval)
 */
export const HomePage: React.FC<HomePageProps> = ({ token: externalToken }) => {
  const { isAuthenticated, userId, tenantId } = useAuth();
  const { apiFetch } = useApi();
  
  const [telemetry, setTelemetry] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  // Fetch telemetry data from HTTP endpoint
  const fetchTelemetry = useCallback(async () => {
    try {
      const res = await apiFetch('/api/system/telemetry');
      if (res.ok) {
        const data = await res.json();
        setTelemetry(data);
        setLoading(false);
      } else {
        console.error('Failed to fetch telemetry:', res.status);
        setLoading(false);
      }
    } catch (err) {
      console.error('Error fetching telemetry:', err);
      setLoading(false);
    }
  }, [apiFetch]);

  // Initial fetch + polling interval (30s)
  useEffect(() => {
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 30000);
    return () => clearInterval(interval);
  }, [fetchTelemetry]);

  if (!isAuthenticated && !externalToken) {
    return <div style={{ color: '#ff0000', padding: '20px' }}>Authentication required</div>;
  }

  if (loading && !telemetry) {
    return <div style={{ color: '#00ffff', padding: '20px' }}>Loading system telemetry...</div>;
  }

  const data = telemetry || {
    timestamp: new Date().toISOString(),
    cpu_percent: 0,
    memory_mb: 0,
    broker_latency_ms: 0,
    satellites: [],
    strategy_array: [],
    risk_buffer: { exposure_pct: 0 },
    anomalies: { count_last_5m: 0, latest: [] }
  };

  return (
    <div style={{
      width: '100%',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, rgba(10, 10, 15, 1) 0%, rgba(20, 10, 30, 1) 100%)',
      padding: '20px',
      fontFamily: 'monospace',
      color: '#00ffff',
      boxSizing: 'border-box'
    }}>
      {/* HEADER */}
      <div style={{
        marginBottom: '20px',
        paddingBottom: '10px',
        borderBottom: '2px solid #00ffff'
      }}>
        <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 'bold' }}>
          ▓▓▓ AETHELGARD V3 - SYSTEM TELEMETRY ▓▓▓
        </h1>
        <div style={{ fontSize: '10px', color: '#888888', marginTop: '5px' }}>
          {new Date().toLocaleTimeString()} • Polling: 30s interval
        </div>
      </div>

      {/* MAIN GRID */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: '15px',
        marginBottom: '20px'
      }}>
        {/* SYSTEM HEALTH */}
        <div style={{
          border: '1px solid #00ffff',
          padding: '15px',
          background: 'rgba(0, 255, 255, 0.05)',
          borderRadius: '4px'
        }}>
          <div style={{ marginBottom: '10px', fontWeight: 'bold', color: '#00ffff' }}>
            💻 SYSTEM HEALTH
          </div>
          <div style={{ marginBottom: '5px', fontSize: '11px' }}>
            CPU: <span style={{ color: '#ffffff', fontWeight: 'bold' }}>
              {data.cpu_percent?.toFixed(1) || 0}%
            </span>
          </div>
          <div style={{ marginBottom: '5px', fontSize: '11px' }}>
            Memory: <span style={{ color: '#ffffff', fontWeight: 'bold' }}>
              {data.memory_mb || 0} MB
            </span>
          </div>
          <div style={{ marginBottom: '5px', fontSize: '11px' }}>
            Broker Latency: <span style={{ color: '#ffffff', fontWeight: 'bold' }}>
              {data.broker_latency_ms || 0} ms
            </span>
          </div>
          <div style={{ fontSize: '11px' }}>
            Heartbeat: <span style={{
              color: data.heartbeat === 'OK' ? '#00ff00' : '#ff0000',
              fontWeight: 'bold'
            }}>
              {data.heartbeat || 'OK'}
            </span>
          </div>
        </div>

        {/* SATELLITES */}
        <div style={{
          border: '1px solid #0099ff',
          padding: '15px',
          background: 'rgba(0, 153, 255, 0.05)',
          borderRadius: '4px'
        }}>
          <div style={{ marginBottom: '10px', fontWeight: 'bold', color: '#0099ff' }}>
            🛰️ SATELLITES ({data.satellites?.length || 0})
          </div>
          {data.satellites && data.satellites.length > 0 ? (
            <div style={{ fontSize: '11px' }}>
              {data.satellites.map((sat: any, idx: number) => (
                <div key={idx} style={{
                  marginBottom: '5px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  color: sat.status === 'CONNECTED' ? '#00ff00' : '#ff0000'
                }}>
                  <span>{sat.provider_id || `Provider-${idx}`}</span>
                  <span>{sat.is_primary ? '⭐ PRIMARY' : 'standby'}</span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: '11px', color: '#888888' }}>
              No satellites connected
            </div>
          )}
        </div>

        {/* RISK BUFFER */}
        <div style={{
          border: '1px solid #ffaa00',
          padding: '15px',
          background: 'rgba(255, 170, 0, 0.05)',
          borderRadius: '4px'
        }}>
          <div style={{ marginBottom: '10px', fontWeight: 'bold', color: '#ffaa00' }}>
            ⚠️ RISK BUFFER
          </div>
          <div style={{ marginBottom: '8px', fontSize: '11px' }}>
            Exposure: <span style={{ color: '#ffffff', fontWeight: 'bold' }}>
              {data.risk_buffer?.exposure_pct?.toFixed(1) || 0}%
            </span>
          </div>
          <div style={{
            width: '100%',
            height: '8px',
            background: '#111111',
            border: '1px solid #ffaa00',
            borderRadius: '2px',
            marginBottom: '8px',
            overflow: 'hidden'
          }}>
            <div style={{
              height: '100%',
              width: `${Math.min(100, (data.risk_buffer?.exposure_pct || 0))}%`,
              background: (data.risk_buffer?.exposure_pct || 0) > 80 ? '#ff0000' : 
                         (data.risk_buffer?.exposure_pct || 0) > 50 ? '#ffaa00' : '#00ff00',
              transition: 'width 0.3s ease'
            }} />
          </div>
          <div style={{ fontSize: '10px', color: '#888888' }}>
            Daily Max: {data.risk_buffer?.daily_max_pct?.toFixed(1) || 0}%
          </div>
        </div>

        {/* STRATEGIES */}
        <div style={{
          border: '1px solid #00ff00',
          padding: '15px',
          background: 'rgba(0, 255, 0, 0.05)',
          borderRadius: '4px'
        }}>
          <div style={{ marginBottom: '10px', fontWeight: 'bold', color: '#00ff00' }}>
            📊 STRATEGIES ({data.strategy_array?.length || 0})
          </div>
          {data.strategy_array && data.strategy_array.length > 0 ? (
            <div style={{ fontSize: '11px' }}>
              {data.strategy_array.map((strat: any, idx: number) => (
                <div key={idx} style={{ marginBottom: '4px', display: 'flex', justifyContent: 'space-between' }}>
                  <span>{strat.id}</span>
                  <span style={{
                    color: strat.status === 'LIVE' ? '#00ff00' : '#ffaa00'
                  }}>
                    [{strat.status}]
                  </span>
                  <span style={{
                    color: strat.pnl > 0 ? '#00ff00' : '#ff0000',
                    fontWeight: 'bold'
                  }}>
                    {strat.pnl > 0 ? '+' : ''}{strat.pnl.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: '11px', color: '#888888' }}>
              No active strategies
            </div>
          )}
        </div>

        {/* ANOMALIES */}
        <div style={{
          border: '1px solid #ff00ff',
          padding: '15px',
          background: 'rgba(255, 0, 255, 0.05)',
          borderRadius: '4px',
          gridColumn: 'span 2'
        }}>
          <div style={{ marginBottom: '10px', fontWeight: 'bold', color: '#ff00ff' }}>
            🔴 ANOMALIES ({data.anomalies?.count_last_5m || 0})
          </div>
          {data.anomalies?.latest && data.anomalies.latest.length > 0 ? (
            <div style={{ fontSize: '11px' }}>
              {data.anomalies.latest.map((anomaly: string, idx: number) => (
                <div key={idx} style={{ marginBottom: '3px', color: '#ffaa00' }}>
                  • {anomaly}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: '11px', color: '#888888' }}>
              System operating normally
            </div>
          )}
        </div>
      </div>

      {/* FOOTER */}
      <div style={{
        fontSize: '10px',
        color: '#666666',
        borderTop: '1px solid #333333',
        paddingTop: '10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          Last Update: {new Date(data.timestamp).toLocaleTimeString()}
        </div>
        <div>
          Polling: 30s interval
        </div>
        <div
          onClick={fetchTelemetry}
          style={{
            cursor: 'pointer',
            color: '#00ffff',
            padding: '4px 8px',
            border: '1px solid #00ffff',
            borderRadius: '3px',
            transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(0, 255, 255, 0.1)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
          }}
        >
          [REFRESH]
        </div>
      </div>
    </div>
  );
};
