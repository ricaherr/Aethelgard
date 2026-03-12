import React, { useEffect, useRef, useState, useCallback } from 'react';
import { motion } from 'framer-motion';

/**
 * NeuralLinkMap Component — The Glass Cockpit Protocol
 * Strategy Consensus Graph with Affinity-based Glow
 *
 * Visual: Canvas 2D node graph with dynamic connections
 * Encoding: Node glow ∝ current asset affinity score
 * Color: Node color reflects PnL (green=profit, red=loss, yellow=neutral)
 * Connection: Lines show risk correlation between strategies
 * Update: Synced with 2-second telemetry polling
 */

export interface StrategyNode {
  strategy_id: string;
  status: 'LIVE' | 'SHADOW' | 'IDLE' | 'BLOCKED';
  affinity_scores: Record<string, number>; // { symbol: affinity_0_to_1 }
  current_symbol: string;
  pnl: number; // Profit/Loss in units
}

export interface NeuralLinkMapProps {
  strategies: StrategyNode[];
  updateInterval?: number; // milliseconds (default 2000)
  onStrategyClick?: (strategyId: string) => void;
  size?: number; // canvas size in px (default 600)
}

interface NodePosition {
  x: number;
  y: number;
  strategy: StrategyNode;
}

export const NeuralLinkMap: React.FC<NeuralLinkMapProps> = ({
  strategies,
  updateInterval = 2000,
  onStrategyClick,
  size = 600,
}) => {
  // Defensive check: ensure strategies is an array
  const safeStrategies = Array.isArray(strategies) ? strategies : [];
  
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const animationFrameRef = useRef<number>();
  const nodePositionsRef = useRef<NodePosition[]>([]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [time, setTime] = useState(0);

  // ============ NODE POSITION CALCULATION (circular arrangement) ============
  const calculateNodePositions = useCallback(
    (strats: StrategyNode[]): NodePosition[] => {
      const centerX = size / 2;
      const centerY = size / 2;
      const radius = size / 3;

      return strats.map((strategy, index) => {
        const angle = (index / strats.length) * Math.PI * 2;
        const x = centerX + Math.cos(angle) * radius;
        const y = centerY + Math.sin(angle) * radius;

        return { x, y, strategy };
      });
    },
    [size]
  );

  // ============ AFFINITY GLOW CALCULATION ============
  const getAffinityGlow = useCallback((strategy: StrategyNode): number => {
    const affinity = strategy.affinity_scores[strategy.current_symbol];
    if (!affinity) return 1; // Default glow if no affinity data
    return 0.4 + affinity * 0.6; // Range: 0.4-1.0
  }, []);

  // ============ NODE COLOR BY PnL ============
  const getNodeColor = useCallback((pnl: number): string => {
    if (pnl > 100) return '#00FF41'; // Acid green for strong profit
    if (pnl > 0) return '#00F2FF'; // Cyan for small profit
    if (pnl > -100) return '#FFD700'; // Gold for small loss
    return '#FF0066'; // Magenta for significant loss
  }, []);

  // ============ RISK CORRELATION (dummy for now, can be enhanced) ============
  const getRiskCorrelation = useCallback((strat1: StrategyNode, strat2: StrategyNode): number => {
    // Simple heuristic: strategies on same symbol have higher correlation
    if (strat1.current_symbol === strat2.current_symbol) return 0.8;

    // Check if they share any symbols with both having affinity > 0.6
    const sharedSymbols = Object.keys(strat1.affinity_scores).filter(
      (sym) =>
        strat2.affinity_scores[sym] &&
        strat1.affinity_scores[sym] > 0.6 &&
        strat2.affinity_scores[sym] > 0.6
    );

    return Math.min(0.7, sharedSymbols.length * 0.3);
  }, []);

  // ============ CANVAS DRAWING LOGIC ============
  const drawGraph = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Update node positions
    nodePositionsRef.current = calculateNodePositions(safeStrategies);

    // Clear canvas
    ctx.fillStyle = 'rgba(2, 2, 2, 0.8)';
    ctx.fillRect(0, 0, size, size);

    const nodes = nodePositionsRef.current;

    // ---- DRAW CONNECTIONS FIRST (so they appear under nodes) ----
    ctx.lineWidth = 1.5;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const node1 = nodes[i];
        const node2 = nodes[j];

        const correlation = getRiskCorrelation(node1.strategy, node2.strategy);
        const opacity = correlation * 0.5;

        ctx.strokeStyle = `rgba(0, 242, 255, ${opacity})`;
        ctx.beginPath();
        ctx.moveTo(node1.x, node1.y);
        ctx.lineTo(node2.x, node2.y);
        ctx.stroke();
      }
    }

    // ---- DRAW NODES ----
    nodes.forEach((node, index) => {
      const { x, y, strategy } = node;
      const nodeRadius = 20 + (getAffinityGlow(strategy) - 0.4) * 20; // 20-32 px
      const color = getNodeColor(strategy.pnl);
      const glow = getAffinityGlow(strategy);

      // Glow effect (multiple rings)
      for (let r = 1; r <= 3; r++) {
        ctx.fillStyle = `${color}${Math.round((0.3 - r * 0.08) * 255)
          .toString(16)
          .padStart(2, '0')}`;
        ctx.beginPath();
        ctx.arc(x, y, nodeRadius + r * 8, 0, Math.PI * 2);
        ctx.fill();
      }

      // Main node circle
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, nodeRadius, 0, Math.PI * 2);
      ctx.fill();

      // Highlight if selected
      if (selectedNode === strategy.strategy_id) {
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(x, y, nodeRadius + 6, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Node border (status indicator)
      ctx.strokeStyle = strategy.status === 'LIVE' ? '#00FF41' : '#666666';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, nodeRadius, 0, Math.PI * 2);
      ctx.stroke();

      // Label: strategy ID abbreviation
      const label = strategy.strategy_id.substring(0, 3).toUpperCase();
      ctx.fillStyle = '#FFFFFF';
      ctx.font = 'bold 10px JetBrains Mono';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, x, y);

      // Affinity badge (small indicator near node)
      const affinity = strategy.affinity_scores[strategy.current_symbol] || 0;
      const affinityText = (affinity * 100).toFixed(0) + '%';
      ctx.fillStyle = 'rgba(0, 255, 65, 0.8)';
      ctx.font = '8px JetBrains Mono';
      ctx.fillText(affinityText, x, y + nodeRadius + 12);
    });

    // ---- DRAW TIME-BASED ANIMATION (pulsing effect) ----
    const pulseValue = 0.7 + 0.3 * Math.sin(time * 0.05);
    nodes.forEach((node) => {
      const { x, y } = node;
      ctx.strokeStyle = `rgba(0, 242, 255, ${pulseValue * 0.2})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(x, y, 50 * pulseValue, 0, Math.PI * 2);
      ctx.stroke();
    });
  }, [size, strategies, selectedNode, time, calculateNodePositions, getAffinityGlow, getNodeColor, getRiskCorrelation]);

  // ============ ANIMATION LOOP ============
  useEffect(() => {
    let frameCount = 0;

    const animate = () => {
      frameCount++;
      setTime(frameCount);
      drawGraph();
      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animationFrameRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [drawGraph]);

  // ============ CLICK HANDLER (node detection) ============
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    // Check if click is within any node
    for (const node of nodePositionsRef.current) {
      const distance = Math.sqrt(
        Math.pow(clickX - node.x, 2) + Math.pow(clickY - node.y, 2)
      );

      if (distance < 35) {
        // Node radius + some padding
        setSelectedNode(node.strategy.strategy_id);
        onStrategyClick?.(node.strategy.strategy_id);
        return;
      }
    }

    setSelectedNode(null);
  };

  // ============ LEGEND RENDERING ============
  const legendItems = safeStrategies.map((strategy) => ({
    id: strategy.strategy_id,
    color: getNodeColor(strategy.pnl),
    affinity: strategy.affinity_scores[strategy.current_symbol] || 0,
    pnl: strategy.pnl,
  }));

  return (
    <motion.div
      ref={containerRef}
      className="neural-link-map-container glass-morphism"
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      style={neuralLinkMapStyles.container}
    >
      <div style={neuralLinkMapStyles.header}>
        <h2>NEURAL LINK MAP</h2>
        <span style={neuralLinkMapStyles.subtitle}>Strategy Consensus Graph</span>
      </div>

      {/* CANVAS */}
      <canvas
        ref={canvasRef}
        width={size}
        height={size}
        onClick={handleCanvasClick}
        aria-label="Neural Link Map: Strategy Consensus Graph with Affinity-based Glow"
        role="img"
        style={neuralLinkMapStyles.canvas}
      />

      {/* LEGEND */}
      <div style={neuralLinkMapStyles.legend}>
        {legendItems.map((item) => (
          <div
            key={item.id}
            style={{
              ...neuralLinkMapStyles.legendItem,
              borderLeftColor: item.color,
            }}
            onClick={() => {
              setSelectedNode(item.id);
              onStrategyClick?.(item.id);
            }}
          >
            <span style={{ ...neuralLinkMapStyles.legendDot, backgroundColor: item.color }} />
            <div style={neuralLinkMapStyles.legendContent}>
              <div style={neuralLinkMapStyles.legendStrategyId}>{item.id}</div>
              <div style={neuralLinkMapStyles.legendAffinity}>
                Affinity: {(item.affinity * 100).toFixed(0)}% | P&L: {item.pnl > 0 ? '+' : ''}
                {item.pnl.toFixed(2)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
};

// ============ STYLES ============
const neuralLinkMapStyles = {
  container: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: '16px',
    padding: '24px',
    background: 'rgba(10, 15, 35, 0.4)',
    backdropFilter: 'blur(10px)',
    border: '1px solid rgba(0, 242, 255, 0.2)',
    borderRadius: '12px',
    boxShadow: '0 0 20px rgba(0, 242, 255, 0.08), inset 0 0 20px rgba(0, 242, 255, 0.04)',
    minWidth: '700px',
  },

  header: {
    textAlign: 'center' as const,
    width: '100%',
  },

  subtitle: {
    display: 'block',
    fontSize: '11px',
    color: '#666666',
    fontFamily: 'JetBrains Mono, monospace',
    letterSpacing: '1px',
  },

  canvas: {
    display: 'block',
    cursor: 'pointer',
    filter: 'drop-shadow(0 0 10px rgba(0, 242, 255, 0.2))',
    borderRadius: '8px',
    border: '1px solid rgba(0, 242, 255, 0.1)',
  },

  legend: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '8px',
    width: '100%',
    maxHeight: '200px',
    overflowY: 'auto' as const,
  },

  legendItem: {
    display: 'flex',
    gap: '8px',
    padding: '8px 12px',
    background: 'rgba(0, 242, 255, 0.05)',
    border: '1px solid rgba(0, 242, 255, 0.1)',
    borderLeft: '3px solid transparent',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '11px',
    fontFamily: 'JetBrains Mono, monospace',
    transition: 'all 0.2s ease',
  },

  legendDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    flexShrink: 0,
    marginTop: '2px',
  },

  legendContent: {
    display: 'flex' as const,
    flexDirection: 'column' as const,
    gap: '2px',
  },

  legendStrategyId: {
    color: '#CCCCCC',
    fontWeight: 600 as const,
  },

  legendAffinity: {
    color: '#999999',
    fontSize: '9px',
  },
};
