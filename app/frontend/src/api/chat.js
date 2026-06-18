/**
 * Chat API helper — uses HttpOnly cookie auth (credentials: 'include').
 */

const BASE = '/api/chat';

export const sendChatMessage = (messages) => {
    return fetch(BASE, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages }),
    }).then(async (res) => {
        if (!res.ok) {
            const err = await res.json().catch(() => ({ message: res.statusText }));
            throw new Error(err.message || err.detail || 'Chat API error');
        }
        return res.json();
    });
};
