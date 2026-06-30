/**
 * Analytics API helper — uses HttpOnly cookie auth (credentials: 'include').
 */

const authFetch = (url) => {
    return fetch(url, {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
    }).then(async (res) => {
        if (!res.ok) {
            const err = await res.json().catch(() => ({ message: res.statusText }));
            throw new Error(err.message || err.detail || 'API error');
        }
        return res.json();
    });
};

export const fetchAnalytics = ({ range = '3m', month = '', plant = '' } = {}) => {
    const p = new URLSearchParams({ range });
    if (month) p.append('month', month);
    if (plant) p.append('plant', plant);
    return authFetch(`/api/analytics?${p}`);
};

export const fetchDrillDown = ({ tag, range = '3m', month = '', plant = '' } = {}) => {
    const p = new URLSearchParams({ range });
    if (tag) p.append('tag', tag);
    if (month) p.append('month', month);
    if (plant) p.append('plant', plant);
    return authFetch(`/api/analytics/drilldown?${p}`);
};

export const fetchProdaiIntelligence = ({ range = '3m', month = '' } = {}) => {
    const p = new URLSearchParams({ range });
    if (month) p.append('month', month);
    return authFetch(`/api/prodai-intelligence?${p}`);
};
