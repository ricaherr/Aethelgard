import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const srcRoot = path.resolve(__dirname, '../..');
const componentPath = path.join(srcRoot, 'components', 'diagnostic', 'ResilienceConsole.tsx');

describe('ResilienceConsole — HU 10.17b contract', () => {
  it('usa endpoint de resiliencia v3 para estado detallado', () => {
    const source = readFileSync(componentPath, 'utf-8');

    expect(source).toContain("/api/v3/resilience/status");
    expect(source).toContain("/api/v3/resilience/command");
  });

  it('renderiza narrativa de forma condicional (no bloque cuando está vacía)', () => {
    const source = readFileSync(componentPath, 'utf-8');

    expect(source).toContain('{narrative && (');
    expect(source).toContain('key="narrative"');
  });
});
