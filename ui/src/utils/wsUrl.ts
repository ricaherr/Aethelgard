/**
 * Utility for building WebSocket URLs.
 *
 * Always uses `window.location.host` (includes port when present) so that in
 * development the Vite proxy at localhost:3000 is respected and the browser
 * sends the HttpOnly `a_token` cookie on the WS handshake.
 *
 * @param path - Absolute path starting with `/ws/...`
 * @param location - Override for testing; defaults to `window.location`
 */
export function getWsUrl(
    path: string,
    location: { protocol: string; host: string } = window.location
): string {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${location.host}${path}`;
}
