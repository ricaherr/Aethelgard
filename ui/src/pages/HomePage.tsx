import React, { useEffect, useState, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { useAuth } from '../hooks/useAuth';
import { useApi } from '../hooks/useApi';
import { StrategyMatrix } from '../components/institutional/StrategyMatrix';
import { OperationalCore } from '../components/institutional/OperationalCore';
import { SignalStream } from '../components/institutional/SignalStream';

interface TelemetryData {
  timestamp: string;
  cpu_percent: number;
  memory_mb: number;
  satellites: any[];
  strategy_array: any[];
  risk_buffer: any;
  anomalies: any;
  health_pct: number;
}

interface SignalData {
  signal_id: string;
  strategy_id: string;
  quality_grade: 'A+' | 'A' | 'B' | 'C' | 'F';
  quality_score: number;
  symbol: string;
  direction: 'BUY' | 'SELL';
  timestamp: string;
}

/**
 * HomePage V3: Satellite Link Institutional Glass Cockpit
 * 
 * Architecture:
 * - Viewport lock (100vh × 100vw, overflow: hidden)
 * - Dynamic scaling (0.7–1.0 based on breakpoints)
 * - Blueprint grid background (registration marks, grid pattern)
 * - 4-row grid: Header | Content (3-col) | Telemetry | Footer
 * 
 * Components:
 * - Strategy Matrix (left): 2×3 grid of 6 strategies
 * - Operational Core (center): Central nucleus + 6 orbiting micro-indicators
 * - Signal Stream (right): Horizontal radar with sweep + signal points
 * 
 * Styling: Monospace, 0.5px lines, glassmorphism, NO SCROLL
 */
export const HomePage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const { apiFetch } = useApi();

  const [telemetry, setTelemetry] = useState<TelemetryData | null>(null);
  const [signals, setSignals] = useState<SignalData[]>([]);
  const [scaleFactor, setScaleFactor] = useState(1.0);
  const resizeTimeoutRef = useRef<number | null>(null);

  // ============ RESPONSIVE SCALE CALCULATION ============
  const calculateScaleFactor = useCallback(() => {
    const width = window.innerWidth;
    let scale = 1.0;

    if (width <= 375) {
      scale = 0.7;
    } else if (width <= 768) {
      scale = 0.85;
    } else if (width <= 1400) {
      scale = 0.95;
    }

    return scale;
  }, []);

  // ============ DEBOUNCED RESIZE LISTENER ============
  const handleResize = useCallback(() => {
    if (resizeTimeoutRef.current !== null) {
      clearTimeout(resizeTimeoutRef.current);
    }
    resizeTimeoutRef.current = window.setTimeout(() => {
      setScaleFactor(calculateScaleFactor());
    }, 150); // 150ms debounce
  }, [calculateScaleFactor]);

  // ============ FETCH TELEMETRY & SIGNALS ============
  const fetchTelemetry = useCallback(async () => {
    try {
      const res = await apiFetch('/api/system/telemetry');
      if (res.ok) {
        const data = await res.json();
        setTelemetry(data);
      }
    } catch (err) {
      console.error('[TELEMETRY] Fetch error:', err);
    }
  }, [apiFetch]);

  const fetchSignals = useCallback(async () => {
    try {
      const res = await apiFetch('/api/signals?limit=50&sort=timestamp');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setSignals(data.slice(0, 20)); // Limit to 20 for radar
        }
      }
    } catch (err) {
      console.error('[SIGNALS] Fetch error:', err);
    }
  }, [apiFetch]);

  // ============ INITIALIZATION & INTERVALS ============
  useEffect(() => {
    if (!isAuthenticated) return;

    // Initial fetch
    fetchTelemetry();
    fetchSignals();
    setScaleFactor(calculateScaleFactor());

    // Polling intervals
    const telemetryInterval = setInterval(fetchTelemetry, 30000); // 30s
    const signalsInterval = setInterval(fetchSignals, 2000); // 2s

    // Resize listener
    window.addEventListener('resize', handleResize);

    return () => {
      clearInterval(telemetryInterval);
      clearInterval(signalsInterval);
      window.removeEventListener('resize', handleResize);
      if (resizeTimeoutRef.current !== null) {
        clearTimeout(resizeTimeoutRef.current);
      }
    };
  }, [isAuthenticated, fetchTelemetry, fetchSignals, calculateScaleFactor, handleResize]);

  if (!isAuthenticated) {
    return <AuthRequiredScreen />;
  }

  if (!telemetry) {
    return <LoadingScreen />;
  }

  // Defensive arrays
  const strategyArray = Array.isArray(telemetry.strategy_array) ? telemetry.strategy_array : [];
  const satellites = Array.isArray(telemetry.satellites) ? telemetry.satellites : [];
  const anomalies = typeof telemetry.anomalies === 'object' 
    ? telemetry.anomalies?.count_last_5m || 0 
    : (telemetry.anomalies || 0);

  return (
    <div
      style={{
        height: '100vh',
        width: '100vw',
        overflow: 'hidden',
        background: '#020202',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
      }}
    >
      {/* BLUEPRINT BACKGROUND (Watermark) */}
      <BlueprintBackground />

      {/* MAIN LAYOUT CONTAINER (Scales with window) */}
      <motion.div
        style={{
          transform: `scale(${scaleFactor})`,
          transformOrigin: 'top center',
          width: '100vw',
          height: '100vh',
          overflow: 'hidden',
        }}
        animate={{ transform: `scale(${scaleFactor})` }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateRows: '40px 1fr 40px 24px',
            gridTemplateColumns: '1fr',
            height: '100vh',
            width: '100vw',
            gap: 0,
            padding: 0,
          }}
        >
          {/* ========== HEADER ========== */}
          <header
            style={{
              gridArea: '1 / 1',
              background: 'rgba(2, 2, 2, 0.8)',
              borderBottom: '0.5px solid rgba(0, 180, 220, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              paddingLeft: '16px',
              paddingRight: '16px',
              fontFamily: 'monospace',
              fontSize: '10px',
              color: '#00D4FF',
              textTransform: 'uppercase',
              letterSpacing: '2px',
            }}
          >
            <span>⬢ AETHELGARD SYNAPSE</span>
            <span
              style={{
                display: 'flex',
                gap: '12px',
                alignItems: 'center',
              }}
            >
              <span
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background: '#00FF41',
                  animation: 'pulse 2s ease-in-out infinite',
                }}
              />
              <span>OPERATIONAL</span>
            </span>
          </header>

          {/* ========== CONTENT AREA (3-COLUMN GRID) ========== */}
          <div
            style={{
              gridArea: '2 / 1',
              display: 'grid',
              gridTemplateColumns: '1fr 1fr 1fr',
              gap: '16px',
              padding: '16px',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
            }}
          >
            {/* LEFT: STRATEGY MATRIX */}
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.6, delay: 0.0 }}
              style={{ overflow: 'hidden' }}
            >
              <StrategyMatrix strategies={strategyArray} anomalies={anomalies} />
            </motion.div>

            {/* CENTER: OPERATIONAL CORE */}
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.8, delay: 0.0 }}
              style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
              }}
            >
              <OperationalCore
                strategies={strategyArray}
                satellites={satellites}
                health={telemetry.health_pct || 75}
                risk={telemetry.risk_buffer?.exposure_pct || 30}
              />
            </motion.div>

            {/* RIGHT: SIGNAL STREAM */}
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.6, delay: 0.0 }}
              style={{ overflow: 'hidden' }}
            >
              <SignalStream signals={signals} />
            </motion.div>
          </div>

          {/* ========== TELEMETRY FOOTER ========== */}
          <div
            style={{
              gridArea: '3 / 1',
              background: 'rgba(2, 2, 2, 0.8)',
              borderTop: '0.5px solid rgba(0, 180, 220, 0.2)',
              borderBottom: '0.5px solid rgba(0, 180, 220, 0.2)',
              display: 'flex',
              justifyContent: 'flex-start',
              alignItems: 'center',
              paddingLeft: '16px',
              paddingRight: '16px',
              gap: '32px',
              fontFamily: 'monospace',
              fontSize: '8px',
              color: '#00D4FF',
              textTransform: 'uppercase',
              letterSpacing: '1px',
            }}
          >
            <span>CPU: {Math.round(telemetry.cpu_percent)}%</span>
            <span>MEM: {Math.round(telemetry.memory_mb / 1024)}G</span>
            <span>SATS: {satellites.filter((s: any) => s.status === 'CONNECTED').length}/{satellites.length}</span>
            <span>STRATS: {strategyArray.filter((s: any) => s.status === 'LIVE').length}/{strategyArray.length}</span>
            <span style={{ color: anomalies > 0 ? '#FF0066' : '#666666' }}>
              ANOMALIES: {anomalies}
            </span>
          </div>

          {/* ========== FOOTER ========== */}
          <footer
            style={{
              gridArea: '4 / 1',
              background: 'rgba(2, 2, 2, 0.8)',
              borderTop: '0.5px solid rgba(0, 180, 220, 0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              paddingLeft: '16px',
              paddingRight: '16px',
              fontFamily: 'monospace',
              fontSize: '7px',
              color: '#666666',
            }}
          >
            <span>©2026 Aethelgard Trading Systems</span>
            <span>v4.3.1-beta</span>
          </footer>
        </div>
      </motion.div>

      {/* GLOBAL STYLES */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
};

// ============ HELPER COMPONENTS ============

function BlueprintBackground() {
  return (
    <svg
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        opacity: 0.02,
        pointerEvents: 'none',
        zIndex: 0,
      }}
      viewBox="0 0 1920 1080"
    >
      <defs>
        <pattern id="small-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#00D4FF" strokeWidth="0.5" />
        </pattern>
        <pattern id="large-grid" width="100" height="100" patternUnits="userSpaceOnUse">
          <rect width="100" height="100" fill="url(#small-grid)" />
          <path d="M 100 0 L 0 0 0 100" fill="none" stroke="#00D4FF" strokeWidth="0.5" />
        </pattern>
      </defs>

      {/* Background grids */}
      <rect width="1920" height="1080" fill="url(#large-grid)" />

      {/* Centerlines */}
      <line x1="960" y1="0" x2="960" y2="1080" stroke="#00D4FF" strokeWidth="0.5" strokeDasharray="5,5" />
      <line x1="0" y1="540" x2="1920" y2="540" stroke="#00D4FF" strokeWidth="0.5" strokeDasharray="5,5" />

      {/* Corner registration marks */}
      <g stroke="#00D4FF" strokeWidth="0.5">
        {/* Top-left */}
        <line x1="10" y1="0" x2="10" y2="20" />
        <line x1="0" y1="10" x2="20" y2="10" />
        {/* Top-right */}
        <line x1="1910" y1="0" x2="1910" y2="20" />
        <line x1="1900" y1="10" x2="1920" y2="10" />
        {/* Bottom-left */}
        <line x1="10" y1="1060" x2="10" y2="1080" />
        <line x1="0" y1="1070" x2="20" y2="1070" />
        {/* Bottom-right */}
        <line x1="1910" y1="1060" x2="1910" y2="1080" />
        <line x1="1900" y1="1070" x2="1920" y2="1070" />
      </g>

      {/* Schema annotation */}
      <text x="30" y="1060" fontSize="8" fill="#00D4FF" fontFamily="monospace">
        SCHEMATIC-01
      </text>
      <text x="1820" y="1060" fontSize="8" fill="#00D4FF" fontFamily="monospace">
        1920x1080
      </text>
    </svg>
  );
}

function AuthRequiredScreen() {
  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#020202',
        color: '#00D4FF',
        fontFamily: 'monospace',
      }}
    >
      <div style={{ fontSize: '48px', marginBottom: '20px' }}>⚠️</div>
      <h2 style={{ margin: 0, textTransform: 'uppercase', letterSpacing: '2px' }}>
        Authentication Required
      </h2>
      <p style={{ color: '#666666', marginTop: '10px' }}>
        Please authenticate to access the Glass Cockpit
      </p>
    </div>
  );
}

function LoadingScreen() {
  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#020202',
        color: '#00D4FF',
        fontFamily: 'monospace',
      }}
    >
      <motion.div
        style={{
          width: '40px',
          height: '40px',
          border: '2px solid #00D4FF',
          borderTopColor: 'transparent',
          borderRadius: '50%',
          marginBottom: '20px',
        }}
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
      />
      <h2 style={{ margin: 0, textTransform: 'uppercase', letterSpacing: '2px' }}>
        Initializing Synapse
      </h2>
      <p style={{ color: '#666666', marginTop: '10px', fontSize: '10px' }}>
        Establishing connection to core systems
      </p>
    </div>
  );
}
