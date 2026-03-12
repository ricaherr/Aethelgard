import React, { useEffect, useRef, useState } from 'react';

interface Signal {
  signal_id: string;
  strategy_id: string;
  quality_grade: 'A+' | 'A' | 'B' | 'C' | 'F';
  quality_score: number;
  symbol: string;
  direction: 'BUY' | 'SELL';
  timestamp: string;
}

interface SignalStreamProps {
  signals: Signal[];
}

interface AnimatedSignal extends Signal {
  canvasX: number;
  canvasY: number;
  lifespan: number; // 0-1, decreases over time
}

/**
 * SignalStream: Horizontal radar with rotating sweep line
 * - Sweep line: Rotates continuously (1 cycle per 3 seconds)
 * - Signal points: Positioned by quality grade (vertical stacking)
 *   - A+/A: Center (y=90px)
 *   - B: Mid (y=110px)
 *   - C/F: Bottom (y=130px)
 * - Point appearance: Pop animation + glow
 * - Point lifespan: 5 seconds, then fade out
 */
export const SignalStream: React.FC<SignalStreamProps> = ({ signals }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationFrameRef = useRef<number>();
  const signalTimestampsRef = useRef<Map<string, number>>(new Map());
  const [animatedSignals, setAnimatedSignals] = useState<AnimatedSignal[]>([]);

  // ============ SIGNAL LIFESPAN MANAGEMENT ============
  useEffect(() => {
    const now = Date.now();
    const newAnimatedSignals: AnimatedSignal[] = [];

    // Update existing signals and add new ones
    const seenSignalIds = new Set<string>();

    signals.forEach((signal, idx) => {
      const signalId = signal.signal_id || `SIG_${idx}`;
      seenSignalIds.add(signalId);

      let timestamp = signalTimestampsRef.current.get(signalId);
      if (!timestamp) {
        timestamp = now;
        signalTimestampsRef.current.set(signalId, timestamp);
      }

      const age = (now - timestamp) / 1000; // seconds
      const lifespan = Math.max(0, 1 - age / 5); // 5 second decay

      if (lifespan > 0) {
        // Position based on quality grade
        const qualityY = {
          'A+': 90,
          A: 90,
          B: 110,
          C: 130,
          F: 130,
        }[signal.quality_grade] || 110;

        newAnimatedSignals.push({
          ...signal,
          canvasX: Math.random() * 600, // Random X position (width varies)
          canvasY: qualityY,
          lifespan,
        });
      }
    });

    // Cleanup old timestamps
    for (const [id] of signalTimestampsRef.current) {
      if (!seenSignalIds.has(id)) {
        signalTimestampsRef.current.delete(id);
      }
    }

    setAnimatedSignals(newAnimatedSignals);
  }, [signals]);

  // ============ CANVAS DRAWING ============
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let sweepAngle = 0;
    let startTime = Date.now();

    const draw = () => {
      const now = Date.now();
      const elapsed = (now - startTime) / 1000; // seconds
      sweepAngle = (elapsed / 3) * Math.PI * 2; // Full rotation every 3 seconds

      const w = canvas.width;
      const h = canvas.height;

      // ========== BACKGROUND ==========
      ctx.fillStyle = 'rgba(2, 2, 2, 0.8)';
      ctx.fillRect(0, 0, w, h);

      // ========== BASELINE & GRID ==========
      ctx.strokeStyle = 'rgba(0, 180, 220, 0.1)';
      ctx.lineWidth = 0.5;

      // Horizontal baselines (3 quality levels)
      [90, 110, 130].forEach((y) => {
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      });
      ctx.setLineDash([]);

      // Quality grade labels (left side)
      ctx.font = 'bold 7px monospace';
      ctx.fillStyle = 'rgba(150, 150, 150, 0.6)';
      ctx.textAlign = 'right';
      ctx.fillText('A+/A', 30, 93);
      ctx.fillText('B', 30, 113);
      ctx.fillText('C/F', 30, 133);

      // ========== SWEEP LINE (Rotating) ==========
      ctx.strokeStyle = 'rgba(0, 212, 255, 0.6)';
      ctx.lineWidth = 2;
      ctx.lineCap = 'round';

      const sweepX = w / 2 + Math.cos(sweepAngle - Math.PI / 2) * 400;
      const sweepY = 110;

      // Main sweep line
      ctx.beginPath();
      ctx.moveTo(w / 2, sweepY);
      ctx.lineTo(sweepX, sweepY - 50);
      ctx.stroke();

      // Sweep glow fade
      const gradient = ctx.createLinearGradient(w / 2, sweepY, sweepX, sweepY - 50);
      gradient.addColorStop(0, 'rgba(0, 212, 255, 0.4)');
      gradient.addColorStop(1, 'rgba(0, 212, 255, 0)');
      ctx.strokeStyle = gradient;
      ctx.lineWidth = 8;
      ctx.stroke();

      // ========== SIGNAL POINTS ==========
      animatedSignals.forEach((signal) => {
        const x = 40 + signal.canvasX; // Offset from left
        const y = signal.canvasY;
        const size = signal.lifespan > 0.5 ? 4 : 2; // Shrink as it fades

        // Outer glow
        ctx.fillStyle = `rgba(0, 212, 255, ${signal.lifespan * 0.3})`;
        ctx.beginPath();
        ctx.arc(x, y, size + 3, 0, Math.PI * 2);
        ctx.fill();

        // Middle glow
        ctx.fillStyle = `rgba(0, 212, 255, ${signal.lifespan * 0.5})`;
        ctx.beginPath();
        ctx.arc(x, y, size + 1, 0, Math.PI * 2);
        ctx.fill();

        // Core point (color by quality)
        const colorMap: Record<string, string> = {
          'A+': '#00D4FF',
          A: '#00B8E6',
          B: '#00A8D8',
          C: '#4DB8E6',
          F: '#2BA0D0',
        };
        ctx.fillStyle = colorMap[signal.quality_grade] || '#00A8D8';
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fill();

        // Quality label (hover-tooltip visible on hover, not here)
      });

      // ========== CENTER NUCLEUS (Pulsing dot at baseline center) ==========
      const pulse = Math.sin(Date.now() / 400) * 2 + 4;
      ctx.fillStyle = 'rgba(0, 212, 255, 0.8)';
      ctx.beginPath();
      ctx.arc(w / 2, 110, pulse, 0, Math.PI * 2);
      ctx.fill();

      animationFrameRef.current = requestAnimationFrame(draw);
    };

    canvas.width = canvas.offsetWidth;
    canvas.height = 160;

    draw();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [animatedSignals]);

  // ============ TOOLTIP HANDLER ============
  const getTooltipText = (signal: AnimatedSignal) => {
    return `${signal.symbol} | ${signal.direction} | Grade: ${signal.quality_grade} (${signal.quality_score}%)`;
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
      {/* HEADER */}
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
        ◆ Signal Stream
      </span>

      {/* CANVAS */}
      <canvas
        ref={canvasRef}
        style={{
          width: '100%',
          height: '160px',
          background: 'rgba(2, 2, 2, 0.5)',
          border: '0.5px solid rgba(0, 180, 220, 0.1)',
          borderRadius: '3px',
          display: 'block',
        }}
      />

      {/* QUALITY LEGEND */}
      <div
        style={{
          fontSize: '7px',
          fontFamily: 'monospace',
          color: '#666666',
          display: 'flex',
          justifyContent: 'flex-start',
          gap: '12px',
          borderTop: '0.5px solid rgba(0, 180, 220, 0.1)',
          paddingTop: '6px',
        }}
      >
        <span style={{ color: '#00D4FF' }}>● A+</span>
        <span style={{ color: '#00B8E6' }}>● A</span>
        <span style={{ color: '#00A8D8' }}>● B</span>
        <span style={{ color: '#4DB8E6' }}>● C</span>
        <span style={{ color: '#2BA0D0' }}>● F</span>
      </div>

      {/* SIGNAL COUNT */}
      <div
        style={{
          fontSize: '7px',
          fontFamily: 'monospace',
          color: '#999999',
          textTransform: 'uppercase',
        }}
      >
        Signals in stream: {animatedSignals.length}/20
      </div>
    </div>
  );
};
