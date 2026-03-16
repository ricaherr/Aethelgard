import { describe, it, expect } from 'vitest';
import { getWsUrl } from '../../utils/wsUrl';

describe('getWsUrl', () => {
    it('AC-5: does not hardcode port 8000 — uses provided host', () => {
        const url = getWsUrl('/ws/v3/synapse', { protocol: 'http:', host: 'localhost:3000' });
        expect(url).not.toContain(':8000');
        expect(url).toContain('localhost:3000');
    });

    it('uses ws: protocol for http: pages', () => {
        const url = getWsUrl('/ws/test', { protocol: 'http:', host: 'localhost:3000' });
        expect(url.startsWith('ws://')).toBe(true);
    });

    it('uses wss: protocol for https: pages', () => {
        const url = getWsUrl('/ws/test', { protocol: 'https:', host: 'app.aethelgard.com' });
        expect(url.startsWith('wss://')).toBe(true);
    });

    it('appends path without double slashes', () => {
        const url = getWsUrl('/ws/strategy/monitor', { protocol: 'http:', host: 'localhost:3000' });
        const withoutProtocol = url.replace(/^wss?:\/\//, '');
        expect(withoutProtocol).not.toContain('//');
    });

    it('preserves full nested path', () => {
        const url = getWsUrl('/ws/strategy/monitor', { protocol: 'http:', host: 'localhost:3000' });
        expect(url).toContain('/ws/strategy/monitor');
    });

    it('builds correct full URL', () => {
        const url = getWsUrl('/ws/v3/synapse', { protocol: 'http:', host: 'localhost:3000' });
        expect(url).toBe('ws://localhost:3000/ws/v3/synapse');
    });
});
