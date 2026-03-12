import React, { useEffect, useRef, useState, useCallback } from 'react';
import { motion } from 'framer-motion';

/**
 * CoreOrb Component — The Glass Cockpit Protocol
 * Central Intelligence Vitality Visualization
 *
 * Visual: Canvas 2D circular gauge + SVG filaments with glassmorphism
 * Animation: Framer Motion pulse synchronized with health/risk metrics
 * Interaction: Drop zone for drag-drop strategy assignment
 * Heartbeat: Syncs with SYSTEM_HEARTBEAT every 5 seconds
 */

export interface Satellite {
  provider_id: string;
  status: 'CONNECTED' | 'DISCONNECTED' | 'DEGRADED';
  latency_ms?: number;
}

export interface Strategy {
  strategy_id: string;
  status: 'LIVE' | 'SHADOW' | 'IDLE' | 'BLOCKED';
  dd_pct?: number;
  pnl?: number;
}

export interface DragPayload {
  strategy_id: string;
  current_pnl?: number;
  risk_units?: number;
}

export interface CoreOrbProps {
  health: number;                    // 0-100, health percentage
  riskExposure: number;              // 0-100, risk percentage
  anomalyCount: number;              // number of active anomalies
  satellites: Satellite[];           // connected data providers
  strategies: Strategy[];            // active strategies
  onZoomTo?: (level: 'meso', target: string) => void;
  onDropZone?: (payload: DragPayload) => void;
  size?: number;                     // canvas size in px (default 400)
  updateInterval?: number;           // polling interval in ms (default 5000)
}

export const CoreOrb: React.FC<CoreOrbProps> = ({
  health,
  riskExposure,
  anomalyCount,
  satellites,
  strategies,
  onZoomTo,
  onDropZone,
  size = 400,
  updateInterval = 5000,
}) => {
  // Defensive checks: ensure arrays are always iterable
  const safeSatellites = Array.isArray(satellites) ? satellites : [];
  const safeStrategies = Array.isArray(strategies) ? strategies : [];
  
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const animationFrameRef = useRef<number>();
  const [dragOver, setDragOver] = useState(false);
  const [pulseIntensity, setPulseIntensity] = useState(1);

  // ============ CANVAS DRAWING LOGIC ============
  const drawOrb = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const centerX = size / 2;
    const centerY = size / 2;
    const radius = size / 2.5;

    // Clear canvas
    ctx.fillStyle = 'rgba(2, 2, 2, 0.8)';
    ctx.fillRect(0, 0, size, size);

    // ---- GRADIENT CIRCLE (health based - INSTITUTIONAL PALETTE) ----
    const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius);
    
    // Health-based color mapping: INSTITUTIONAL PALETTE (No Magenta, No Bright Yellow)
    let colorStart = '#00D4FF';    // Cyan institutional
    let colorEnd = '#00D4FF';
    let colorStroke = '#00D4FF';

    if (health < 40) {
      // Critical: Deep institutional blue
      colorStart = '#2BA0D0';
      colorEnd = '#2BA0D0';
      colorStroke = '#2BA0D0';
    } else if (health < 70) {
      // Caution: Mid-range blue
      colorStart = '#00A8D8';
      colorEnd = '#00A8D8';
      colorStroke = '#00A8D8';
    }

    gradient.addColorStop(0, `${colorStart}22`);     // 13% opacity at center
    gradient.addColorStop(0.7, `${colorStart}08`);   // 3% opacity
    gradient.addColorStop(1, `${colorEnd}00`);       // Transparent at edge

    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.fill();

    // ---- STROKE CIRCLE (risk based, thicker if risk > exposure) ----
    const strokeWidth = 3 + (riskExposure / 100) * 4;
    let riskStrokeMod = '#00F2FF';
    
    if (riskExposure > 80) {
      riskStrokeMod = '#FF0066';
    } else if (riskExposure > 60) {
      riskStrokeMod = '#FFD700';
    } else if (riskExposure > 40) {
      riskStrokeMod = '#00FF41';
    }

    ctx.strokeStyle = riskStrokeMod;
    ctx.lineWidth = strokeWidth;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.stroke();

    // ---- GLOW EFFECTS ----
    ctx.shadowBlur = 20 + pulseIntensity * 10;
    ctx.shadowColor = colorStroke;
    ctx.strokeStyle = colorStroke;
    ctx.lineWidth = 2;
    ctx.globalAlpha = 0.4 * pulseIntensity;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius + 5, 0, Math.PI * 2);
    ctx.stroke();

    ctx.globalAlpha = 1;
    ctx.shadowBlur = 0;

    // ---- INNER GAUGE (health percentage) ----
    const healthAngle = (health / 100) * Math.PI * 2 - Math.PI / 2;
    const innerRadius = radius * 0.5;

    ctx.strokeStyle = colorStroke;
    ctx.lineWidth = 8;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.arc(centerX, centerY, innerRadius, -Math.PI / 2, healthAngle);
    ctx.stroke();

    // ---- HEARTBEAT NEEDLE (animated) ----
    const needleAngle = (pulseIntensity * 0.5) * Math.PI * 2;
    const needleLength = radius * 0.7;
    
    const needleX = centerX + Math.cos(needleAngle - Math.PI / 2) * needleLength;
    const needleY = centerY + Math.sin(needleAngle - Math.PI / 2) * needleLength;

    ctx.strokeStyle = colorStroke;
    ctx.lineWidth = 3;
    ctx.globalAlpha = 0.8;
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(needleX, needleY);
    ctx.stroke();

    ctx.globalAlpha = 1;

    // ---- CENTER DOT (pulsing) ----
    const dotRadius = 4 + pulseIntensity * 3;
    ctx.fillStyle = colorStroke;
    ctx.beginPath();
    ctx.arc(centerX, centerY, dotRadius, 0, Math.PI * 2);
    ctx.fill();

    // ---- ANOMALY INDICATOR (if anomalies present) ----
    if (anomalyCount > 0) {
      const anomalyX = centerX - radius * 0.6;
      const anomalyY = centerY - radius * 0.6;
      
      ctx.fillStyle = `rgba(255, 0, 102, ${0.5 * pulseIntensity})`;
      ctx.beginPath();
      ctx.arc(anomalyX, anomalyY, 8 + pulseIntensity * 4, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = '#FF0066';
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.7;
      ctx.beginPath();
      ctx.arc(anomalyX, anomalyY, 8 + pulseIntensity * 4, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }, [size, health, riskExposure, anomalyCount, pulseIntensity]);

  // ============ ANIMATION LOOP ============
  useEffect(() => {
    let time = 0;
    const animate = () => {
      time += 1 / 60; // 60 FPS
      const pulse = 0.7 + 0.3 * Math.sin(time * Math.PI * 2); // 0.7-1.0 range
      setPulseIntensity(pulse);
      drawOrb();
      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animationFrameRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [drawOrb]);

  // ============ DRAG & DROP HANDLERS ============
  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);

    try {
      const jsonData = e.dataTransfer.getData('application/json');
      if (jsonData) {
        const payload: DragPayload = JSON.parse(jsonData);
        onDropZone?.(payload);
      }
    } catch (error) {
      console.error('Drop payload parse error:', error);
    }
  };

  // ============ SATELLITE & STRATEGY INDICATORS ============
  const activeSatellites = safeSatellites.filter(s => s.status === 'CONNECTED').length;
  const liveStrategies = safeStrategies.filter(s => s.status === 'LIVE').length;

  return (
    <motion.div
      ref={containerRef}
      className="core-orb-container glass-morphism"
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      style={coreOrbStyles.container}
      data-health={health}
      data-risk={riskExposure}
    >
      {/* CANVAS WRAPPER */}
      <div
        className="core-orb-canvas-wrapper"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={coreOrbStyles.canvasWrapper}
      >
        <canvas
          ref={canvasRef}
          width={size}
          height={size}
          aria-label="Core Orb: Central System Intelligence Vitality Gauge"
          role="img"
          style={coreOrbStyles.canvas}
        />

        {/* SVG FILAMENTS OVERLAY */}
        <svg
          width={size}
          height={size}
          style={coreOrbStyles.svgoverlay}
          viewBox={`0 0 ${size} ${size}`}
        >
          <defs>
            <linearGradient id="filament-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#00D4FF" stopOpacity="0.8" />
              <stop offset="50%" stopColor="#2ED573" stopOpacity="0.5" />
              <stop offset="100%" stopColor="#00A8D8" stopOpacity="0.3" />
            </linearGradient>
          </defs>

          {/* Filaments (random paths for organic feel) */}
          <path
            d={`M ${size / 2} ${size / 2} L ${size * 0.3} ${size * 0.4} Q ${size * 0.2} ${size * 0.5} ${size * 0.25} ${size * 0.7}`}
            stroke="url(#filament-gradient)"
            strokeWidth="1"
            fill="none"
            opacity="0.6"
            className="filament"
          />
          <path
            d={`M ${size / 2} ${size / 2} L ${size * 0.7} ${size * 0.3} Q ${size * 0.8} ${size * 0.2} ${size * 0.75} ${size * 0.1}`}
            stroke="url(#filament-gradient)"
            strokeWidth="1"
            fill="none"
            opacity="0.6"
            className="filament"
          />
          <path
            d={`M ${size / 2} ${size / 2} L ${size * 0.6} ${size * 0.8} Q ${size * 0.7} ${size * 0.9} ${size * 0.5} ${size * 0.95}`}
            stroke="url(#filament-gradient)"
            strokeWidth="1"
            fill="none"
            opacity="0.6"
            className="filament"
          />
        </svg>

        {/* DROP ZONE INDICATOR (pulsing when anomalies present) */}
        {anomalyCount > 0 && (
          <motion.div
            className="drop-zone-pulse"
            animate={{ scale: [1, 1.05, 1], opacity: [0.3, 0.6, 0.3] }}
            transition={{ duration: 1.5, repeat: Infinity }}
            style={coreOrbStyles.dropZonePulse}
          />
        )}

        {/* DROP ZONE EXPLICIT AREA */}
        <div
          className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
          style={{
            ...coreOrbStyles.dropZone,
            backgroundColor: dragOver ? 'rgba(0, 242, 255, 0.15)' : 'transparent',
          }}
        >
          {dragOver && (
            <div style={coreOrbStyles.dropHint}>
              📥 Drop Strategy
            </div>
          )}
        </div>
      </div>

      {/* LEGEND: SATELLITES & STRATEGIES */}
        <div style={coreOrbStyles.legend}>
        <div className="legend-item satellites">
          <span className="legend-label">SATELLITES:</span>
          <span className="legend-value" data-testid="satellite-count">
            {activeSatellites}/{safeSatellites.length}
          </span>
          <span className="status-dot" style={{ backgroundColor: activeSatellites === safeSatellites.length ? '#2ED573' : '#00A8D8' }} />
        </div>
        <div className="legend-item strategies">
          <span className="legend-label">STRATEGIES:</span>
          <span className="legend-value" data-testid="strategy-count">
            {liveStrategies}/{safeStrategies.length}
          </span>
          <span className="status-dot" style={{ backgroundColor: liveStrategies > 0 ? '#00D4FF' : '#666666' }} />
        </div>
        <div className="legend-item anomalies">
          <span className="legend-label">ANOMALIES:</span>
          <span className="legend-value" style={{ color: anomalyCount > 0 ? '#2BA0D0' : '#666666' }}>
            {anomalyCount}
          </span>
        </div>
      </div>

      {/* PULSE ANIMATION INDICATOR */}
      {anomalyCount > 0 && (
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
          style={coreOrbStyles.pulseRing}
        />
      )}
    </motion.div>
  );
};

// ============ STYLES ============
const coreOrbStyles = {
  container: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    gap: '20px',
    padding: '24px',
    background: 'rgba(0, 10, 25, 0.3)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(0, 180, 220, 0.15)',
    borderRadius: '16px',
    boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.1), 0 20px 50px rgba(0, 0, 0, 0.4)',
    position: 'relative' as const,
    perspective: '1200px',
    transform: 'rotateX(5deg) rotateY(2deg)',
  },

  canvasWrapper: {
    position: 'relative' as const,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'crosshair' as const,
  },

  canvas: {
    display: 'block',
    filter: 'drop-shadow(0 0 10px rgba(0, 180, 220, 0.3))',
  },

  svgoverlay: {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    pointerEvents: 'none' as const,
  },

  dropZone: {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    borderRadius: '50%',
    border: '2px dashed rgba(0, 180, 220, 0.2)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'all 0.3s ease',
    cursor: 'grab' as const,
  },

  dropZonePulse: {
    position: 'absolute' as const,
    top: '50%',
    left: '50%',
    transform: 'translate(-50%, -50%)',
    width: '100%',
    height: '100%',
    borderRadius: '50%',
    border: '2px solid rgba(0, 180, 220, 0.4)',
    pointerEvents: 'none' as const,
  },

  dropHint: {
    color: '#00D4FF',
    fontFamily: 'JetBrains Mono, monospace',
    fontSize: '14px',
    fontWeight: 600,
    textAlign: 'center' as const,
    letterSpacing: '1px',
  },

  legend: {
    display: 'flex',
    gap: '24px',
    width: '100%',
    justifyContent: 'center',
    flexWrap: 'wrap' as const,
    fontSize: '12px',
    fontFamily: 'JetBrains Mono, monospace',
    color: '#CCCCCC',
  },

  pulseRing: {
    position: 'absolute' as const,
    width: '120%',
    height: '120%',
    border: '1px solid rgba(0, 180, 220, 0.2)',
    borderRadius: '50%',
    top: '50%',
    left: '50%',
    transform: 'translate(-50%, -50%)',
    pointerEvents: 'none' as const,
  },
};
