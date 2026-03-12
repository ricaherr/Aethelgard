import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { BlueprintBackground } from './BlueprintBackground';

interface IsometricContainerProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
}

/**
 * IsometricContainer: Wrapper with isometric perspective
 * 
 * - Provides 3D isometric perspective using CSS transform
 * - Integrates BlueprintBackground for technical aesthetic
 * - Responsive scaling: entire container scales down on smaller viewports
 * - Glassmorphism: Deep transparency (0.2 / rgba-based)
 * - No horizontal overflow: Uses overflow-hidden + dynamic scale()
 */
export const IsometricContainer: React.FC<IsometricContainerProps> = ({
  children,
  className = '',
  title,
  subtitle
}) => {
  const [viewport, setViewport] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 1920,
    height: typeof window !== 'undefined' ? window.innerHeight : 1080
  });

  useEffect(() => {
    const handleResize = () => {
      setViewport({
        width: window.innerWidth,
        height: window.innerHeight
      });
    };
    
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Calcula escala dinámica para que SIEMPRE quepa sin overflow
  let scale = 1;
  let maxWidth = '100%';
  
  if (viewport.width < 768) {
    scale = 0.75;
    maxWidth = '100%';
  } else if (viewport.width < 1024) {
    scale = 0.85;
    maxWidth = '100%';
  } else if (viewport.width < 1400) {
    scale = 0.90;
    maxWidth = '100%';
  } else {
    scale = 1;
    maxWidth = '1800px';
  }

  return (
    <div className="relative w-full h-full overflow-hidden bg-black">
      {/* Blueprint Background (Watermark Técnico) */}
      <BlueprintBackground />

      {/* Contenedor con perspectiva isométrica */}
      <div
        className={`relative w-full h-full flex flex-col items-center justify-center overflow-hidden ${className}`}
        style={{
          perspective: '1400px',

        }}
      >
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          style={{
            transform: `scaleX(${scale}) scaleY(${scale}) perspective(1200px) rotateX(5deg)`,
            transformOrigin: 'center center',
            maxWidth: maxWidth,
            width: '100%',
          }}
          className="relative w-full"
        >
          {/* Outer Glassmorphism Frame */}
          <div
            className="relative rounded-3xl backdrop-blur-xl border overflow-hidden"
            style={{
              background: 'rgba(0, 0, 0, 0.3)',
              borderColor: 'rgba(255, 255, 255, 0.08)',
              boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.1), 0 20px 60px rgba(0, 0, 0, 0.6)'
            }}
          >
            {/* Header Técnico */}
            {(title || subtitle) && (
              <div className="px-8 py-6 border-b border-white/5 bg-gradient-to-r from-black/40 to-transparent">
                <div className="flex items-end gap-4">
                  {title && (
                    <h1
                      className="text-3xl font-black text-white uppercase tracking-tighter italic"
                      style={{
                        textShadow: '0 0 20px rgba(0, 210, 255, 0.2)',
                        fontFamily: '"Outfit", sans-serif'
                      }}
                    >
                      {title}
                      <span className="text-cyan-400 ml-2">{subtitle}</span>
                    </h1>
                  )}
                  <div
                    className="ml-auto w-1 h-8 rounded-full"
                    style={{
                      background: 'linear-gradient(180deg, rgba(0, 210, 255, 0.5), transparent)',
                      boxShadow: '0 0 15px rgba(0, 210, 255, 0.3)'
                    }}
                  />
                </div>
              </div>
            )}

            {/* Content Area */}
            <div
              className="relative p-6 lg:p-8"
              style={{
                background: 'rgba(0, 0, 0, 0.15)'
              }}
            >
              {children}
            </div>
          </div>
        </motion.div>
      </div>

      {/* Scanlines Effect (Subtle CRT aesthetic) */}
      <div
        className="absolute inset-0 pointer-events-none opacity-5"
        style={{
          backgroundImage: 'linear-gradient(0deg, rgba(255, 255, 255, 0.1) 1px, transparent 1px)',
          backgroundSize: '100% 4px'
        }}
      />
    </div>
  );
};
