/**
 * Breakdown Logging API helpers — uses HttpOnly cookie auth.
 */

const authFetch = (url, options = {}) => {
    return fetch(url, {
        ...options,
        credentials: 'include',
        headers: {
            ...(options.headers ?? {}),
        },
    }).then(async (res) => {
        if (!res.ok) {
            const err = await res.json().catch(() => ({ message: res.statusText }));
            throw new Error(err.message || 'API error');
        }
        return res.json();
    });
};

/** GET /api/breakdowns/equipment — equipment list for dropdown */
export const fetchBreakdownEquipment = () =>
    authFetch('/api/breakdowns/equipment');

/**
 * POST /api/breakdowns — submit a new breakdown.
 * @param {FormData} formData — includes fields + optional file[] under key "attachments"
 */
export const submitBreakdown = (formData) =>
    authFetch('/api/breakdowns', {
        method: 'POST',
        body: formData,
    });
