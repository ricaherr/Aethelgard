import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const SOURCE_PATH = resolve(__dirname, '../../hooks/useStrategyMonitor.ts');

describe('useStrategyMonitor — Source Compliance', () => {
    const source = readFileSync(SOURCE_PATH, 'utf-8');

    it('AC-4: does not use localStorage for WS auth', () => {
        expect(source).not.toContain("localStorage.getItem('access_token')");
    });

    it('AC-5: does not hardcode port 8000 in WebSocket URL', () => {
        expect(source).not.toContain('localhost:8000');
    });

    it('uses isAuthenticated from useAuth to guard the connection', () => {
        expect(source).toContain('isAuthenticated');
    });

    it('uses getWsUrl utility instead of manual URL construction', () => {
        expect(source).toContain('getWsUrl');
    });

    it('does not pass token as query param in the WS URL', () => {
        // Old bug: /ws/strategy/monitor?token=${...}
        expect(source).not.toContain('?token=');
    });
});
