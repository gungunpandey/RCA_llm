/**
 * Equipment API helper — uses HttpOnly cookie auth (credentials: 'include').
 */

const authFetch = (url, options = {}) => {
    return fetch(url, {
        credentials: 'include',
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...(options.headers ?? {}),
        },
    }).then(async (res) => {
        if (!res.ok) {
            const err = await res.json().catch(() => ({ message: res.statusText }));
            throw new Error(err.message || err.detail || 'API error');
        }
        return res.json();
    });
};

export const fetchEquipmentList = ({ search = '', criticality = '' } = {}) => {
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    if (criticality) params.append('criticality', criticality);
    return authFetch(`/api/equipment?${params.toString()}`);
};

export const fetchEquipmentDetail = (id) =>
    authFetch(`/api/equipment/${id}`);

export const createEquipment = (data) =>
    authFetch('/api/equipment', {
        method: 'POST',
        body: JSON.stringify(data),
    });

export const addEquipmentComponent = (equipmentId, name) =>
    authFetch(`/api/equipment/${equipmentId}/components`, {
        method: 'POST',
        body: JSON.stringify({ name }),
    });

export const deleteEquipmentComponent = (componentId) =>
    authFetch(`/api/equipment/components/${componentId}`, {
        method: 'DELETE',
    });
