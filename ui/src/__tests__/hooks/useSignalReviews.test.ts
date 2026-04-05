import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const srcRoot = path.resolve(__dirname, '../..');
const hookPath = path.join(srcRoot, 'hooks', 'useSignalReviews.ts');
const contextPath = path.join(srcRoot, 'contexts', 'AethelgardContext.tsx');

describe('useSignalReviews — WS Push Integration', () => {
  it('listens to signal review push event and triggers refresh', () => {
    const source = readFileSync(hookPath, 'utf-8');

    expect(source).toContain("window.addEventListener('aethelgard:signal-review-pending'");
    expect(source).toContain('void refreshPending();');
  });

  it('keeps polling only as low-frequency fallback', () => {
    const source = readFileSync(hookPath, 'utf-8');

    expect(source).toContain('60000');
    expect(source).not.toContain('10000');
  });

  it('context bridges SIGNAL_REVIEW_PENDING WS message to hook event bus', () => {
    const source = readFileSync(contextPath, 'utf-8');

    expect(source).toContain("case 'SIGNAL_REVIEW_PENDING'");
    expect(source).toContain("window.dispatchEvent(new CustomEvent('aethelgard:signal-review-pending'");
  });
});
