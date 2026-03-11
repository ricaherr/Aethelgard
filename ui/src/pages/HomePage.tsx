/**
 * HOME PAGE - FRACTAL V3 GLASS BOX
 * Mockup Técnico: Layout con HUD circular central y 4 widgets orbitales
 * 
 * TRACE_ID: UI-EXEC-FRACTAL-v3-HOME
 * Estética: Sci-Fi Funcional - Transparencias, bordes de neón sutiles, glow effects
 * Performance: 60 FPS, <10% CPU (Canvas para renderizado pesado)
 * 
 * ARQUITECTURA VISUAL:
 * ┌─────────────────────────────────────────┐
 * │        FRACTAL V3 GLASS BOX             │
 * │                                          │
 * │   ┌──────────────────────────────────┐  │
 * │   │   [SATELLITE STATUS WIDGET]      │  │
 * │   │   Left-Top: Satellites orbitales │  │
 * │   └──────────────────────────────────┘  │
 * │                                          │
 * │  ┌────────────────────────────────────┐ │
 * │  │        HUD CIRCULAR CENTRAL        │ │
 * │  │   • Salud del sistema (0-100%)     │ │
 * │  │   • Exposición de riesgo (R units) │ │
 * │  │   • Status de estrategias          │ │
 * │  │   • Anomalías críticas             │ │
 * │  └────────────────────────────────────┘ │
 * │                                          │
 * │   ┌──────────────────────────────────┐  │
 * │   │  [RISK BUFFER WIDGET]            │  │
 * │   │  Right-Top: Exposición actual    │  │
 * │   └──────────────────────────────────┘  │
 * │                                          │
 * │   ┌──────────────────────────────────┐  │
 * │   │ [SCANNER & ANOMALIES]            │  │
 * │   │ Bottom: Timeline de eventos      │  │
 * │   └──────────────────────────────────┘  │
 * │                                          │
 * └─────────────────────────────────────────┘
 */

import React, { useEffect, useRef, useCallback } from 'react';
import { useSynapseTelemetry } from '../hooks/useSynapseTelemetry';
import { useAuth } from '../hooks/useAuth';

interface HomePageProps {
  token?: string;
}

/**
 * Component: Central HUD Renderer
 * Renderiza el HUD circular central usando Canvas para máxima performance
 */
const CentralHUD: React.FC<{
  health: number;
  riskExposure: number;
  strategiesStatus: any[];
  anomalyCount: number;
}> = ({ health, riskExposure, strategiesStatus, anomalyCount }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = 80;

    // Clear canvas
    ctx.fillStyle = 'rgba(10, 10, 15, 0.9)';
    ctx.fillRect(0, 0, width, height);

    // Draw circular HUD background
    ctx.strokeStyle = '#00ffff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.stroke();

    // Draw inner circle (glow effect)
    ctx.strokeStyle = 'rgba(0, 255, 255, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius - 5, 0, Math.PI * 2);
    ctx.stroke();

    // Draw health arc (top segment)
    const healthAngle = (health / 100) * Math.PI;
    ctx.strokeStyle = health > 75 ? '#00ff00' : health > 50 ? '#ffaa00' : '#ff0000';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius - 10, -Math.PI / 2, -Math.PI / 2 + healthAngle);
    ctx.stroke();

    // Draw risk exposure arc (bottom segment)
    const riskAngle = (riskExposure / 100) * Math.PI;
    ctx.strokeStyle = riskExposure > 75 ? '#ff0000' : riskExposure > 50 ? '#ffaa00' : '#00ff00';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius - 20, Math.PI / 2, Math.PI / 2 + riskAngle);
    ctx.stroke();

    // Draw strategy indicators (6 positions alrededor del círculo)
    strategiesStatus.forEach((strategy, idx) => {
      const angle = (idx / strategiesStatus.length) * Math.PI * 2;
      const dotX = centerX + Math.cos(angle) * (radius + 20);
      const dotY = centerY + Math.sin(angle) * (radius + 20);

      const dotColor = strategy.status === 'LIVE' ? '#00ff00' : 
                      strategy.status === 'QUARANTINE' ? '#ffaa00' : '#888888';
      
      ctx.fillStyle = dotColor;
      ctx.beginPath();
      ctx.arc(dotX, dotY, 4, 0, Math.PI * 2);
      ctx.fill();

      // Glow
      ctx.strokeStyle = 'rgba(' + (dotColor === '#00ff00' ? '0, 255, 0' : 
                                   dotColor === '#ffaa00' ? '255, 170, 0' : '136, 136, 136') + ', 0.3)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(dotX, dotY, 6, 0, Math.PI * 2);
      ctx.stroke();
    });

    // Draw text labels
    ctx.fillStyle = '#00ffff';
    ctx.font = 'bold 12px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(`HEALTH: ${Math.round(health)}%`, centerX, centerY - 40);
    ctx.fillText(`RISK: ${Math.round(riskExposure)}%`, centerX, centerY + 40);
    
    if (anomalyCount > 0) {
      ctx.fillStyle = '#ff0000';
      ctx.fillText(`⚠ ${anomalyCount} ANOMALIES`, centerX, centerY + 60);
    }

  }, [health, riskExposure, strategiesStatus, anomalyCount]);

  return (
    <canvas
      ref={canvasRef}
      width={300}
      height={300}
      style={{
        border: '1px solid #00ffff',
        borderRadius: '8px',
        background: 'rgba(10, 10, 15, 0.95)',
        boxShadow: '0 0 20px rgba(0, 255, 255, 0.3)'
      }}
    />
  );
};

/**
 * Component: Mini Widgets (4 esquinas)
 */
const SatelliteWidget: React.FC<{ satellites: any[] }> = ({ satellites }) => (
  <div style={{
    position: 'absolute',
    top: '16px',
    left: '16px',
    padding: '12px',
    border: '1px solid #00ffff',
    borderRadius: '6px',
    background: 'rgba(10, 10, 15, 0.85)',
    fontSize: '12px',
    fontFamily: 'monospace',
    color: '#00ffff',
    maxWidth: '200px',
    boxShadow: '0 0 10px rgba(0, 255, 255, 0.2)'
  }}>
    <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>SATELLITES</div>
    {satellites.map((sat) => (
      <div key={sat.provider_id} style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginBottom: '4px',
        color: sat.status === 'CONNECTED' ? '#00ff00' : '#ff0000'
      }}>
        <span>{sat.provider_id}</span>
        <span>{sat.is_primary ? '⭐' : '•'}</span>
      </div>
    ))}
  </div>
);

const RiskWidget: React.FC<{ risk: any }> = ({ risk }) => (
  <div style={{
    position: 'absolute',
    top: '16px',
    right: '16px',
    padding: '12px',
    border: '1px solid #ffaa00',
    borderRadius: '6px',
    background: 'rgba(10, 10, 15, 0.85)',
    fontSize: '12px',
    fontFamily: 'monospace',
    color: '#ffaa00',
    maxWidth: '200px',
    boxShadow: '0 0 10px rgba(255, 170, 0, 0.2)'
  }}>
    <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>RISK BUFFER</div>
    <div style={{ marginBottom: '4px' }}>
      Total: <span style={{ color: '#ffffff' }}>{risk.total_units_r} R</span>
    </div>
    <div style={{ marginBottom: '4px' }}>
      Available: <span style={{ color: '#ffffff' }}>{risk.available_units_r} R</span>
    </div>
    <div style={{ marginBottom: '4px' }}>
      Exposure: <span style={{ color: '#ffffff' }}>{risk.exposure_pct.toFixed(1)}%</span>
    </div>
    <div style={{
      color: risk.risk_mode === 'DEFENSIVE' ? '#ff0000' : risk.risk_mode === 'AGGRESSIVE' ? '#00ff00' : '#ffaa00'
    }}>
      Mode: {risk.risk_mode}
    </div>
  </div>
);

const ScannerWidget: React.FC<{ scanner: any; anomalies: any }> = ({ scanner, anomalies }) => (
  <div style={{
    position: 'absolute',
    bottom: '16px',
    left: '16px',
    padding: '12px',
    border: '1px solid #00ff00',
    borderRadius: '6px',
    background: 'rgba(10, 10, 15, 0.85)',
    fontSize: '12px',
    fontFamily: 'monospace',
    color: '#00ff00',
    maxWidth: '250px',
    maxHeight: '200px',
    overflowY: 'auto',
    boxShadow: '0 0 10px rgba(0, 255, 0, 0.2)'
  }}>
    <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>SCANNER</div>
    <div style={{ marginBottom: '4px' }}>
      Status: <span style={{ color: '#ffffff' }}>{scanner.status}</span>
    </div>
    <div style={{ marginBottom: '4px' }}>
      Assets: <span style={{ color: '#ffffff' }}>{scanner.assets.length}</span>
    </div>
    <div style={{
      marginBottom: '8px',
      color: scanner.cpu_limit_exceeded ? '#ff0000' : '#00ff00'
    }}>
      CPU: {scanner.cpu_percent.toFixed(1)}%
    </div>
    <div style={{ fontWeight: 'bold', marginTop: '8px', color: '#ff0000' }}>
      ANOMALIES: {anomalies.count_last_5m}
    </div>
  </div>
);

const TimelineWidget: React.FC<{ anomalies: any[] }> = ({ anomalies }) => (
  <div style={{
    position: 'absolute',
    bottom: '16px',
    right: '16px',
    padding: '12px',
    border: '1px solid #ff00ff',
    borderRadius: '6px',
    background: 'rgba(10, 10, 15, 0.85)',
    fontSize: '11px',
    fontFamily: 'monospace',
    color: '#ff00ff',
    maxWidth: '250px',
    maxHeight: '200px',
    overflowY: 'auto',
    boxShadow: '0 0 10px rgba(255, 0, 255, 0.2)'
  }}>
    <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>TIMELINE</div>
    {anomalies.length === 0 ? (
      <div style={{ color: '#888888' }}>No recent events</div>
    ) : (
      anomalies.map((anomaly, idx) => (
        <div key={idx} style={{
          marginBottom: '4px',
          borderLeft: '2px solid #ff00ff',
          paddingLeft: '6px',
          color: anomaly.severity === 'CRITICAL' ? '#ff0000' : '#ffaa00'
        }}>
          <div>{anomaly.type}</div>
          <div style={{ fontSize: '10px', color: '#888888' }}>
            {new Date(anomaly.timestamp).toLocaleTimeString()}
          </div>
        </div>
      ))
    )}
  </div>
);

/**
 * HOME PAGE COMPONENT
 */
export const HomePage: React.FC<HomePageProps> = ({ token: externalToken }) => {
  const { userId, tenantId, isAuthenticated, isLoading: authLoading } = useAuth();
  
  // Use external token if provided, otherwise derive from auth context
  // In production, this would fetch a JWT from /api/auth/token
  const finalToken = externalToken || (isAuthenticated ? `${tenantId}:${userId}` : null);
  const { telemetry, loading, error, isConnected } = useSynapseTelemetry(finalToken || undefined);

  if (!isAuthenticated && !externalToken) {
    return <div style={{ color: '#ff0000', padding: '20px' }}>Authentication required</div>;
  }
  
  if (authLoading) {
    return <div style={{ color: '#00ffff', padding: '20px' }}>Loading authentication...</div>;
  }

  if (loading) {
    return <div style={{ color: '#00ffff', padding: '20px' }}>Initializing Synapse...</div>;
  }

  if (error) {
    return <div style={{ color: '#ff0000', padding: '20px' }}>Error: {error}</div>;
  }

  if (!telemetry) {
    return <div style={{ color: '#ffaa00', padding: '20px' }}>Waiting for telemetry...</div>;
  }

  // Calculate health score (0-100)
  const health = Math.max(
    0,
    100 - telemetry.risk_buffer.exposure_pct - 
    (telemetry.anomalies.count_last_5m * 5)
  );

  return (
    <div style={{
      width: '100%',
      height: '100vh',
      background: 'linear-gradient(135deg, rgba(10, 10, 15, 1) 0%, rgba(20, 10, 30, 1) 100%)',
      display: 'flex',
      flexDirection: 'column',
      boxSizing: 'border-box',
      fontFamily: 'monospace',
      color: '#00ffff',
      overflow: 'hidden'
    }}>
      {/* HEADER */}
      <div style={{
        padding: '16px 24px',
        borderBottom: '1px solid #00ffff',
        background: 'rgba(10, 10, 15, 0.95)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{ fontWeight: 'bold', fontSize: '18px' }}>
          ▓▓▓ AETHELGARD FRACTAL V3 GLASS BOX ▓▓▓
        </div>
        <div style={{ fontSize: '12px', color: isConnected ? '#00ff00' : '#ff0000' }}>
          {isConnected ? '✓ ONLINE' : '✗ OFFLINE'} | {telemetry.trace_id}
        </div>
      </div>

      {/* MAIN LAYOUT */}
      <div style={{
        position: 'relative',
        flex: 1,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        padding: '24px'
      }}>
        {/* Widgets posicionados absolutamente alrededor del HUD central */}
        <SatelliteWidget satellites={telemetry.system_heartbeat.satellites} />
        <RiskWidget risk={telemetry.risk_buffer} />
        <ScannerWidget 
          scanner={telemetry.active_scanners} 
          anomalies={telemetry.anomalies}
        />
        <TimelineWidget anomalies={telemetry.anomalies.latest.slice(0, 5)} />

        {/* HUD CENTRAL */}
        <CentralHUD
          health={health}
          riskExposure={telemetry.risk_buffer.exposure_pct}
          strategiesStatus={telemetry.strategy_array}
          anomalyCount={telemetry.anomalies.count_last_5m}
        />
      </div>

      {/* FOOTER */}
      <div style={{
        padding: '16px 24px',
        borderTop: '1px solid #00ffff',
        background: 'rgba(10, 10, 15, 0.95)',
        fontSize: '11px',
        color: '#888888',
        display: 'flex',
        justifyContent: 'space-between'
      }}>
        <div>
          Last Update: {telemetry.timestamp}
        </div>
        <div>
          Frame Rate: 60 FPS | CPU: &lt;10%
        </div>
        <div>
          Strategies: {telemetry.strategy_array.length} | 
          {' '}Status: {telemetry.strategy_array.filter(s => s.status === 'LIVE').length} LIVE
        </div>
      </div>
    </div>
  );
};

export default HomePage;
