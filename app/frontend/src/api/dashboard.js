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

const buildQueryString = (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.plant) params.append('plant', filters.plant);
    if (filters.equipType) params.append('equip_type', filters.equipType);
    if (filters.dateRange) params.append('date_range', filters.dateRange);
    const str = params.toString();
    return str ? `?${str}` : '';
};

export const fetchSummary = (filters) => authFetch(`${BASE}/summary${buildQueryString(filters)}`);
export const fetchTopEquipment = (filters) => authFetch(`${BASE}/top-equipment${buildQueryString(filters)}`);
export const fetchBreakdowns = (filters) => authFetch(`${BASE}/breakdowns${buildQueryString(filters)}`);
export const fetchFailuresByAsset = (filters) => authFetch(`${BASE}/failures-by-asset${buildQueryString(filters)}`);
export const fetchRCAReports = (filters) => authFetch(`${BASE}/rca-reports${buildQueryString(filters)}`);

