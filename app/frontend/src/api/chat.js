/**
 * Chat API helper — uses HttpOnly cookie auth (credentials: 'include').
 */

const json = async (res) => {
    if (!res.ok) {
        const err = await res.json().catch(() => ({ message: res.statusText }));
        throw new Error(err.message || err.detail || 'Chat API error');
    }
    return res.json();
};

const authFetch = (url, opts = {}) =>
    fetch(url, {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        ...opts,
    }).then(json);

// ── Stateless (legacy) ───────────────────────────────────────────────────────
export const sendChatMessage = (messages) =>
    authFetch('/api/chat', { method: 'POST', body: JSON.stringify({ messages }) });

// ── Conversation library (server-side persistence) ───────────────────────────
export const listConversations = () => authFetch('/api/conversations');

export const createConversation = () =>
    authFetch('/api/conversations', { method: 'POST' });

export const getConversation = (id) => authFetch(`/api/conversations/${id}`);

export const deleteConversation = (id) =>
    authFetch(`/api/conversations/${id}`, { method: 'DELETE' });

// Send a message within a conversation. `attachments` is optional (Phase 2).
export const sendConversationMessage = (id, content, attachments) =>
    authFetch(`/api/conversations/${id}/chat`, {
        method: 'POST',
        body: JSON.stringify({ content, attachments: attachments || null }),
    });
