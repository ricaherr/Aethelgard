import React from 'react';

/**
 * BlueprintBackground: Technical schematics-style watermark
 * 
 * - SVG-based grid pattern with technical annotations
 * - Subtle opacity (0.03-0.05) so it doesn't obscure content
 * - Provides "engineering blueprint" aesthetic
 * - Responsive: scales with viewport
 */
export const BlueprintBackground: React.FC = () => {
  return (
    <div className="absolute inset-0 overflow-hidden opacity-5">
      <svg
        className="w-full h-full"
        viewBox="0 0 1920 1080"
        preserveAspectRatio="xMidYMid slice"
        style={{ pointerEvents: 'none' }}
      >
        <defs>
          <pattern
            id="smallGrid"
            width="40"
            height="40"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 40 0 L 0 0 0 40"
              fill="none"
              stroke="currentColor"
              strokeWidth="0.5"
              opacity="0.5"
            />
          </pattern>
          <pattern
            id="grid"
            width="200"
            height="200"
            patternUnits="userSpaceOnUse"
          >
            <rect width="200" height="200" fill="url(#smallGrid)" />
            <path
              d="M 200 0 L 0 0 0 200"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              opacity="0.3"
            />
          </pattern>
        </defs>

        {/* Grid Background */}
        <rect width="1920" height="1080" fill="url(#grid)" />

        {/* Technical Annotations */}
        <g opacity="0.6" stroke="currentColor" strokeWidth="1">
          {/* Horizontal + Vertical Centerlines */}
          <line x1="960" y1="0" x2="960" y2="1080" strokeDasharray="5,5" />
          <line x1="0" y1="540" x2="1920" y2="540" strokeDasharray="5,5" />

          {/* Quadrants Markers */}
          <circle cx="480" cy="270" r="3" fill="none" />
          <circle cx="1440" cy="270" r="3" fill="none" />
          <circle cx="480" cy="810" r="3" fill="none" />
          <circle cx="1440" cy="810" r="3" fill="none" />

          {/* Role + Dimension Labels */}
          <text
            x="20"
            y="30"
            fontSize="12"
            fontFamily="monospace"
            opacity="0.4"
          >
            SCHEMATIC-01
          </text>
          <text
            x="1800"
            y="30"
            fontSize="12"
            fontFamily="monospace"
            opacity="0.4"
            textAnchor="end"
          >
            1920x1080
          </text>

          {/* Corner Registration Marks */}
          <g>
            {/* Top-Left */}
            <line x1="10" y1="10" x2="30" y2="10" strokeWidth="0.5" />
            <line x1="10" y1="10" x2="10" y2="30" strokeWidth="0.5" />
            {/* Top-Right */}
            <line x1="1910" y1="10" x2="1890" y2="10" strokeWidth="0.5" />
            <line x1="1910" y1="10" x2="1910" y2="30" strokeWidth="0.5" />
            {/* Bottom-Left */}
            <line x1="10" y1="1070" x2="30" y2="1070" strokeWidth="0.5" />
            <line x1="10" y1="1070" x2="10" y2="1050" strokeWidth="0.5" />
            {/* Bottom-Right */}
            <line x1="1910" y1="1070" x2="1890" y2="1070" strokeWidth="0.5" />
            <line x1="1910" y1="1070" x2="1910" y2="1050" strokeWidth="0.5" />
          </g>
        </g>

        {/* Isometric perspective lines (subtle) */}
        <g stroke="currentColor" strokeWidth="0.5" opacity="0.3">
          {Array.from({ length: 6 }).map((_, i) => {
            const startX = 300 + i * 300;
            const startY = 200;
            const angle = 30; // Isometric angle
            const length = 500;
            const endX = startX + Math.cos((angle * Math.PI) / 180) * length;
            const endY = startY + Math.sin((angle * Math.PI) / 180) * length;
            return (
              <line
                key={`iso-h-${i}`}
                x1={startX}
                y1={startY}
                x2={endX}
                y2={endY}
                strokeDasharray="3,3"
              />
            );
          })}
        </g>

        {/* Depth markers */}
        <g fill="none" stroke="currentColor" strokeWidth="1" opacity="0.2">
          <rect x="600" y="300" width="600" height="400" />
        </g>
      </svg>
    </div>
  );
};
