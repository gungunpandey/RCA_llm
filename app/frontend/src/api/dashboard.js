/**
 * Dashboard API helper — uses HttpOnly cookie auth (credentials: 'include').
 */

const BASE = '/api/dashboard';

const authFetch = (url) => {
    return fetch(url, {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
    }).then(async (res) => {
        if (!res.ok) {
            const err = await res.json().catch(() => ({ message: res.statusText }));
            throw new Error(err.message || 'API error');
        }
        return res.json();
    });
};

export const fetchSummary = () => authFetch(`${BASE}/summary`);
export const fetchTopEquipment = () => authFetch(`${BASE}/top-equipment`);
export const fetchBreakdowns = () => authFetch(`${BASE}/breakdowns`);
export const fetchFailuresByAsset = () => authFetch(`${BASE}/failures-by-asset`);
export const fetchRCAReports = () => authFetch(`${BASE}/rca-reports`);
