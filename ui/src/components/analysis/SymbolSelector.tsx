
import React, { useEffect, useState } from 'react';

interface SymbolSelectorProps {
  symbol: string;
  setSymbol: (s: string) => void;
}

const SymbolSelector: React.FC<SymbolSelectorProps> = ({ symbol, setSymbol }) => {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchSymbols = () => {
    setError(null);
    fetch('/api/instruments')
      .then(res => {
        if (!res.ok) throw new Error('No se pudo obtener la lista de instrumentos');
        return res.json();
      })
      .then(data => {
        // Extract symbols from markets structure
        const extractedSymbols: string[] = [];
        if (data.markets && typeof data.markets === 'object') {
          Object.values(data.markets).forEach((market: any) => {
            if (typeof market === 'object') {
              Object.values(market).forEach((category: any) => {
                if (category.instruments && Array.isArray(category.instruments)) {
                  extractedSymbols.push(...category.instruments);
                }
              });
            }
          });
        }

        if (extractedSymbols.length > 0) {
          setSymbols(extractedSymbols);
        } else {
          throw new Error('No se encontraron instrumentos');
        }
      })
      .catch((err) => {
        setError('No se pudo cargar la lista de instrumentos. Intenta nuevamente.');
        setSymbols(['EURUSD', 'GBPUSD', 'USDJPY']); // fallback
        console.error('[SymbolSelector] Error:', err);
      });
  };

  useEffect(() => {
    fetchSymbols();
    // eslint-disable-next-line
  }, []);

  return (
    <div className="symbol-selector">
      <label>Instrumento:</label>
      {error && (
        <div className="bg-red-900/60 text-red-200 p-2 rounded flex items-center gap-2 mb-2">
          <span>⚠️</span> {error}
          <button className="ml-auto px-2 py-1 bg-red-700/40 rounded text-xs" onClick={fetchSymbols}>Reintentar</button>
        </div>
      )}
      <select value={symbol} onChange={e => setSymbol(e.target.value)}>
        {symbols.map(sym => (
          <option key={sym} value={sym}>{sym}</option>
        ))}
      </select>
    </div>
  );
};

export default SymbolSelector;
