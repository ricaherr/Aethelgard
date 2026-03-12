import React, { useEffect, useRef, useState, useCallback } from 'react';
import { motion } from 'framer-motion';

/**
 * SignalDNARadar Component (V2 - INSTITUTIONAL RADAR)
 * 
 * Military-Grade Radar Scanner with Sweep Lines
 * - Rotating sweep line (CRT-style radar)
 * - Precision signal points (no chaotic particles)
 * - Institutional palette: Cyan/Blue/Green (NO magenta, NO yellow)
 * - Quality-based radial positioning:
 *   - A+/A: Inner ring (strong signals)
 *   - B: Mid ring (neutral)
 *   - C/F: Outer ring (weak signals)
 */

export interface RadarSignal {
  signal_id: string;
  strategy_id: string;
  quality_grade: 'A+' | 'A' | 'B' | 'C' | 'F';
  quality_score: number; // 0-100
  symbol: string;
  direction: 'BUY' | 'SELL';
}

export interface SignalDNARadarProps {
  signals: RadarSignal[];
  updateInterval?: number;
  onSignalClick?: (signalId: string) => void;
  size?: number; // canvas size in px (default 500)
}

interface RadarPoint {
  signal: RadarSignal;
  angle: number; // Position on radar (0-360)
  radius: number; // Distance from center (relative to ring)
  intensity: number; // Glow brightness (0-1)
}

// INSTITUTIONAL PALETTE (No Magenta, No Bright Yellow)
const QUALITY_GRADE_CONFIG = {
  'A+': { color: '#00D4FF', ring: 0.25, intensity: 1.0, label: 'CRITICAL' },
  'A': { color: '#00B8E6', ring: 0.35, intensity: 0.95, label: 'STRONG' },
  'B': { color: '#00A8D8', ring: 0.50, intensity: 0.80, label: 'NEUTRAL' },
  'C': { color: '#4DB8E6', ring: 0.65, intensity: 0.65, label: 'WEAK' },
  'F': { color: '#2BA0D0', ring: 0.80, intensity: 0.50, label: 'FAILED' },
};

export const SignalDNARadar: React.FC<SignalDNARadarProps> = ({
  signals,
  updateInterval = 1000,
  onSignalClick,
  size = 500,
}) => {
  const safeSignals = Array.isArray(signals) ? signals : [];
  
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const radarPointsRef = useRef<RadarPoint[]>([]);
  const animationFrameRef = useRef<number>();
  const [sweepAngle, setSweepAngle] = useState(0);
  const [time, setTime] = useState(0);
  const [hoveredSignalId, setHoveredSignalId] = useState<string | null>(null);

  // Build radar points from signals
  const buildRadarPoints = useCallback((): RadarPoint[] => {
    return safeSignals.map((signal, index) => {
      const config = QUALITY_GRADE_CONFIG[signal.quality_grade];
      const angleStep = 360 / Math.max(safeSignals.length, 1);
      const angle = (index * angleStep) % 360;
      
      return {
        signal,
        angle,
        radius: (size / 2) * config.ring,
        intensity: config.intensity,
      };
    });
  }, [safeSignals, size]);

  // Update radar points when signals change
  useEffect(() => {
    radarPointsRef.current = buildRadarPoints();
  }, [buildRadarPoints]);

  // Draw radar canvas with sweep line
  const drawRadar = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const centerX = size / 2;
    const centerY = size / 2;

    // Clear canvas with dark background
    ctx.fillStyle = 'rgba(0, 10, 25, 0.95)';
    ctx.fillRect(0, 0, size, size);

    // ---- DRAW CONCENTRIC RINGS (Radar Grid) ----
    ctx.strokeStyle = 'rgba(0, 180, 220, 0.15)';
    ctx.lineWidth = 1;
    const rings = 4;
    for (let i = 1; i <= rings; i++) {
      const radius = (size / 2) * (i / rings);
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.stroke();
    }

    // ---- DRAW CROSSHAIRS (Cardinal Directions) ----
    ctx.strokeStyle = 'rgba(0, 180, 220, 0.1)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(centerX, 0);
    ctx.lineTo(centerX, size);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, centerY);
    ctx.lineTo(size, centerY);
    ctx.stroke();
    ctx.setLineDash([]);

    // ---- DRAW SWEEP LINE (Rotating scan) ----
    const sweepRadians = (sweepAngle % 360) * (Math.PI / 180);
    const sweepEndX = centerX + Math.cos(sweepRadians) * (size / 2);
    const sweepEndY = centerY + Math.sin(sweepRadians) * (size / 2);

    // Gradient sweep for visual interest
    const sweepGradient = ctx.createLinearGradient(centerX, centerY, sweepEndX, sweepEndY);
    sweepGradient.addColorStop(0, 'rgba(0, 212, 255, 0.6)');
    sweepGradient.addColorStop(0.7, 'rgba(0, 180, 220, 0.2)');
    sweepGradient.addColorStop(1, 'rgba(0, 180, 220, 0)');

    ctx.strokeStyle = sweepGradient;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(sweepEndX, sweepEndY);
    ctx.stroke();

    // ---- DRAW SIGNAL POINTS ----
    radarPointsRef.current.forEach((point) => {
      const config = QUALITY_GRADE_CONFIG[point.signal.quality_grade];
      const angleRad = (point.angle * Math.PI) / 180;
      
      const x = centerX + Math.cos(angleRad) * point.radius;
      const y = centerY + Math.sin(angleRad) * point.radius;
      
      const isHovered = hoveredSignalId === point.signal.signal_id;
      const pointSize = 6 + (point.signal.quality_score / 100) * 6;
      
      // Outer glow
      ctx.fillStyle = config.color;
      ctx.globalAlpha = 0.15 * point.intensity;
      ctx.beginPath();
      ctx.arc(x, y, pointSize * 2.5, 0, Math.PI * 2);
      ctx.fill();
      
      // Mid glow
      ctx.globalAlpha = 0.3 * point.intensity;
      ctx.beginPath();
      ctx.arc(x, y, pointSize * 1.5, 0, Math.PI * 2);
      ctx.fill();
      
      // Core point
      ctx.fillStyle = config.color;
      ctx.globalAlpha = point.intensity;
      ctx.beginPath();
      ctx.arc(x, y, pointSize, 0, Math.PI * 2);
      ctx.fill();
      
      // Hover highlight
      if (isHovered) {
        ctx.strokeStyle = config.color;
        ctx.lineWidth = 2;
        ctx.globalAlpha = 1;
        ctx.beginPath();
        ctx.arc(x, y, pointSize + 6, 0, Math.PI * 2);
        ctx.stroke();
      }
      
      ctx.globalAlpha = 1;
    });

    // ---- CENTER NUCLEUS (Acceptance point) ----
    ctx.fillStyle = '#00D4FF';
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.arc(centerX, centerY, 4, 0, Math.PI * 2);
    ctx.fill();

    // Pulsing center halo
    const pulse = 0.5 + 0.5 * Math.sin(time * 0.012);
    ctx.strokeStyle = '#00D4FF';
    ctx.lineWidth = 1;
    ctx.globalAlpha = pulse * 0.2;
    ctx.beginPath();
    ctx.arc(centerX, centerY, 25 + pulse * 8, 0, Math.PI * 2);
    ctx.stroke();

    ctx.globalAlpha = 1;
  }, [size, sweepAngle, time, hoveredSignalId]);

  // Animation loop
  useEffect(() => {
    let frameCount = 0;

    const animate = () => {
      frameCount++;
      setTime(frameCount);
      setSweepAngle((frameCount * 0.5) % 360); // Smooth rotation

      drawRadar();
      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animationFrameRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [drawRadar]);

  // Click handler
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    const centerX = size / 2;
    const centerY = size / 2;

    // Find closest signal point to click
    let closest: RadarPoint | null = null;
    let closestDist = 15;

    for (const point of radarPointsRef.current) {
      const angleRad = (point.angle * Math.PI) / 180;
      const x = centerX + Math.cos(angleRad) * point.radius;
      const y = centerY + Math.sin(angleRad) * point.radius;
      
      const dist = Math.sqrt((clickX - x) ** 2 + (clickY - y) ** 2);
      if (dist < closestDist) {
        closestDist = dist;
        closest = point;
      }
    }

    if (closest) {
      onSignalClick?.(closest.signal.signal_id);
    }
  };

  // Hover handler
  const handleCanvasMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const moveX = e.clientX - rect.left;
    const moveY = e.clientY - rect.top;
    const centerX = size / 2;
    const centerY = size / 2;

    let hovered: string | null = null;

    for (const point of radarPointsRef.current) {
      const angleRad = (point.angle * Math.PI) / 180;
      const x = centerX + Math.cos(angleRad) * point.radius;
      const y = centerY + Math.sin(angleRad) * point.radius;
      
      const dist = Math.sqrt((moveX - x) ** 2 + (moveY - y) ** 2);
      if (dist < 15) {
        hovered = point.signal.signal_id;
        break;
      }
    }

    setHoveredSignalId(hovered);
  };

  // Build legend
  const sortedSignals = [...safeSignals].sort(
    (a, b) => b.quality_score - a.quality_score
  );

  return (
    <motion.div
      ref={containerRef}
      className="flex flex-col gap-4 p-6 rounded-2xl"
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.6 }}
      style={{
        background: 'rgba(0, 10, 25, 0.25)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(0, 180, 220, 0.15)',
      }}
    >
      {/* HEADER */}
      <div className="flex items-center justify-between pb-3 border-b border-white/5">
        <div>
          <h3 className="text-sm font-black uppercase tracking-widest text-white" style={{ fontFamily: '"Outfit", sans-serif' }}>
            Radar Scan
          </h3>
          <p className="text-xs text-white/40 font-mono tracking-tighter">Military-Grade Signal Detection</p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1 rounded-lg" style={{ background: 'rgba(0, 212, 255, 0.1)', border: '1px solid rgba(0, 212, 255, 0.2)' }}>
          <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: '#00D4FF' }} />
          <span className="text-xs text-white/60 font-mono">ACTIVE</span>
        </div>
      </div>

      {/* CANVAS */}
      <div className="flex justify-center">
        <canvas
          ref={canvasRef}
          width={size}
          height={size}
          onClick={handleCanvasClick}
          onMouseMove={handleCanvasMove}
          className="rounded-lg border cursor-crosshair"
          style={{
            border: '1px solid rgba(0, 180, 220, 0.2)',
            boxShadow: '0 0 20px rgba(0, 212, 255, 0.15)',
            background: 'rgba(0, 5, 15, 0.8)',
          }}
        />
      </div>

      {/* LEGEND */}
      <div className="pt-2 border-t border-white/5">
        <div className="text-xs font-black text-white/50 uppercase tracking-widest mb-2">Quality Rings:</div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 max-h-32 overflow-y-auto">
          {sortedSignals.map((signal) => {
            const config = QUALITY_GRADE_CONFIG[signal.quality_grade];
            const isHovered = hoveredSignalId === signal.signal_id;
            return (
              <div
                key={signal.signal_id}
                className="text-xs p-2 rounded-lg cursor-pointer transition-all"
                onClick={() => onSignalClick?.(signal.signal_id)}
                style={{
                  background: isHovered ? `${config.color}15` : 'rgba(0, 180, 220, 0.05)',
                  border: `1px solid ${isHovered ? config.color : 'rgba(0, 180, 220, 0.1)'}`,
                  color: config.color,
                }}
              >
                <div className="font-mono font-bold">{signal.quality_grade}</div>
                <div className="text-white/50 text-[10px]">{signal.symbol} {signal.direction.charAt(0)}</div>
                <div className="text-white/30 text-[9px]">{signal.quality_score}% | {config.label}</div>
              </div>
            );
          })}
        </div>
      </div>
    </motion.div>
  );
};