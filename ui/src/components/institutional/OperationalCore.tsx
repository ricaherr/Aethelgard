import React, { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

interface Strategy {
  id?: string;
  strategy_id?: string;
  status?: string;
  pnl?: number;
}

interface Satellite {
  provider_id?: string;
  status?: string;
  latency_ms?: number;
}

interface OperationalCoreProps {
  strategies: Strategy[];
  satellites: Satellite[];
  health: number; // 0-100
  risk: number; // 0-100
}

/**
 * OperationalCore: Central isometric nucleus with 6 orbiting micro-indicators
 * - Central gauge: Health (0-100%) + Risk (0-100%)
 * - 6 micro-indicators: Orbiting strategy nodes (NW, N, NE, SE, S, SW positions)
 * - Real-time WebSocket updates: Color transition on status change (0.3s)
 * - Telemetry: Health bar visualization
 */
export const OperationalCore: React.FC<OperationalCoreProps> = ({
  strategies,
  satellites,
  health,
  risk,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationFrameRef = useRef<number>();
  const rotationRef = useRef(0);

  // ============ CANVAS ANIMATION ============
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw = () => {
      const w = canvas.width;
      const h = canvas.height;
      const cx = w / 2;
      const cy = h / 2;

      // Clear
      ctx.fillStyle = 'rgba(2, 2, 2, 0.7)';
      ctx.fillRect(0, 0, w, h);

      // Central circle (health gauge background)
      ctx.fillStyle = 'rgba(0, 180, 220, 0.1)';
      ctx.beginPath();
      ctx.arc(cx, cy, 45, 0, Math.PI * 2);
      ctx.fill();

      // Health gauge arc (outer ring)
      const healthAngle = (health / 100) * Math.PI * 2;
      ctx.strokeStyle = health > 60 ? '#00D4FF' : health > 30 ? '#FFD700' : '#FF0066';
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.arc(cx, cy, 50, -Math.PI / 2, -Math.PI / 2 + healthAngle);
      ctx.stroke();

      // Risk gauge arc (inner ring)
      const riskAngle = (risk / 100) * Math.PI * 2;
      ctx.strokeStyle = risk < 40 ? '#00FF41' : risk < 70 ? '#FFD700' : '#FF0066';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(cx, cy, 40, Math.PI / 2, Math.PI / 2 + riskAngle);
      ctx.stroke();

      // Center nucleus (pulsing)
      const pulse = Math.sin(Date.now() / 500) * 5 + 12;
      ctx.fillStyle = 'rgba(0, 212, 255, 0.6)';
      ctx.beginPath();
      ctx.arc(cx, cy, pulse, 0, Math.PI * 2);
      ctx.fill();

      // Rotate for visual effect
      rotationRef.current += 0.5;

      animationFrameRef.current = requestAnimationFrame(draw);
    };

    canvas.width = 280;
    canvas.height = 280;
    draw();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [health, risk]);

  // ============ MICRO-INDICATORS (6 Positions) ============
  const positions = [
    { position: 'N', angle: -Math.PI / 2, label: 'Top' },
    { position: 'NE', angle: -Math.PI / 6, label: 'Top-Right' },
    { position: 'SE', angle: Math.PI / 6, label: 'Bottom-Right' },
    { position: 'S', angle: Math.PI / 2, label: 'Bottom' },
    { position: 'SW', angle: (5 * Math.PI) / 6, label: 'Bottom-Left' },
    { position: 'NW', angle: (-5 * Math.PI) / 6, label: 'Top-Left' },
  ];

  const getStrategyColor = (status: string | undefined) => {
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

  const microIndicators = positions.slice(0, 6).map((pos, idx) => {
    const strat = strategies[idx];
    const stratId = strat?.strategy_id || strat?.id || `—`;
    const stratStatus = strat?.status || 'IDLE';
    const statusColor = getStrategyColor(stratStatus);

    // Position on orbit (140px from center)
    const radius = 140;
    const x = Math.cos(pos.angle) * radius;
    const y = Math.sin(pos.angle) * radius;

    return (
      <motion.div
        key={`micro-${idx}`}
        initial={{ opacity: 0, scale: 0 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, delay: idx * 0.08 }}
        style={{
          position: 'absolute',
          left: `calc(50% + ${x}px)`,
          top: `calc(50% + ${y}px)`,
          transform: 'translate(-50%, -50%)',
          width: '20px',
          height: '20px',
        }}
      >
        <div
          style={{
            width: '100%',
            height: '100%',
            borderRadius: '50%',
            border: `2px solid ${statusColor}`,
            background: 'rgba(10, 15, 35, 0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '7px',
            fontFamily: 'monospace',
            color: statusColor,
            fontWeight: 'bold',
            textTransform: 'uppercase',
            boxShadow: `0 0 8px ${statusColor}60`,
            transition: 'all 0.3s ease',
            cursor: 'pointer',
          }}
          title={`${stratId}: ${stratStatus}`}
          onMouseOver={(e) => {
            e.currentTarget.style.boxShadow = `0 0 15px ${statusColor}`;
            e.currentTarget.style.transform = 'scale(1.2)';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.boxShadow = `0 0 8px ${statusColor}60`;
            e.currentTarget.style.transform = 'scale(1)';
          }}
        >
          {stratId.substring(0, 2)}
        </div>
      </motion.div>
    );
  });

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
        padding: '16px',
        background: 'rgba(10, 15, 35, 0.3)',
        border: '0.5px solid rgba(0, 180, 220, 0.2)',
        borderRadius: '4px',
        backdropFilter: 'blur(8px)',
        boxShadow: 'inset 0 0 10px rgba(0, 180, 220, 0.05)',
      }}
    >
      {/* TITLE */}
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
        ◆ Operational Core
      </span>

      {/* CANVAS (Nucleus visualization) */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
        }}
      >
        <canvas
          ref={canvasRef}
          style={{
            display: 'block',
            borderRadius: '4px',
            background: 'rgba(2, 2, 2, 0.5)',
            border: '0.5px solid rgba(0, 180, 220, 0.1)',
          }}
        />

        {/* ORBITING MICRO-INDICATORS (Overlay on canvas) */}
        <div
          style={{
            position: 'absolute',
            width: 'min(280px, 100%)',
            aspectRatio: '1',
            pointerEvents: 'none',
          }}
        >
          {microIndicators}
        </div>
      </div>

      {/* TELEMETRY METRICS */}
      <div
        style={{
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          fontSize: '7px',
          fontFamily: 'monospace',
        }}
      >
        {/* HEALTH BAR */}
        <div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              marginBottom: '2px',
            }}
          >
            <span style={{ color: '#999999' }}>HEALTH</span>
            <span
              style={{
                color: health > 60 ? '#00D4FF' : health > 30 ? '#FFD700' : '#FF0066',
                fontWeight: 'bold',
              }}
            >
              {Math.round(health)}%
            </span>
          </div>
          <div
            style={{
              width: '100%',
              height: '4px',
              background: 'rgba(50, 50, 70, 0.5)',
              borderRadius: '2px',
              border: '0.5px solid rgba(0, 180, 220, 0.1)',
              overflow: 'hidden',
            }}
          >
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${health}%` }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
              style={{
                height: '100%',
                background: health > 60 ? '#00D4FF' : health > 30 ? '#FFD700' : '#FF0066',
                boxShadow: `0 0 4px ${health > 60 ? '#00D4FF' : health > 30 ? '#FFD700' : '#FF0066'}`,
              }}
            />
          </div>
        </div>

        {/* RISK BAR */}
        <div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              marginBottom: '2px',
            }}
          >
            <span style={{ color: '#999999' }}>RISK</span>
            <span
              style={{
                color: risk < 40 ? '#00FF41' : risk < 70 ? '#FFD700' : '#FF0066',
                fontWeight: 'bold',
              }}
            >
              {Math.round(risk)}%
            </span>
          </div>
          <div
            style={{
              width: '100%',
              height: '4px',
              background: 'rgba(50, 50, 70, 0.5)',
              borderRadius: '2px',
              border: '0.5px solid rgba(0, 180, 220, 0.1)',
              overflow: 'hidden',
            }}
          >
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${risk}%` }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
              style={{
                height: '100%',
                background: risk < 40 ? '#00FF41' : risk < 70 ? '#FFD700' : '#FF0066',
                boxShadow: `0 0 4px ${risk < 40 ? '#00FF41' : risk < 70 ? '#FFD700' : '#FF0066'}`,
              }}
            />
          </div>
        </div>

        {/* SATELLITES CONNECTION */}
        <div style={{ marginTop: '4px', paddingTop: '4px', borderTop: '0.5px solid rgba(0, 180, 220, 0.1)' }}>
          <span style={{ color: '#999999' }}>
            SATS: {satellites.filter((s) => s.status === 'CONNECTED').length}/{satellites.length}
          </span>
        </div>
      </div>
    </div>
  );
};
