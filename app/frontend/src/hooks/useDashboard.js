import { useState, useEffect } from 'react';
import {
    fetchSummary,
    fetchTopEquipment,
    fetchBreakdowns,
    fetchFailuresByAsset,
    fetchRCAReports,
} from '../api/dashboard';

/**
 * Fires all 5 dashboard API requests in parallel.
 * Returns { data, loading, error }.
 */
const useDashboard = (filters) => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);

        Promise.all([
            fetchSummary(filters),
            fetchTopEquipment(filters),
            fetchBreakdowns(filters),
            fetchFailuresByAsset(filters),
            fetchRCAReports(filters),
        ])
            .then(([summary, topEquipment, breakdowns, failuresByAsset, rcaReports]) => {
                if (!cancelled) {
                    setData({ summary, topEquipment, breakdowns, failuresByAsset, rcaReports });
                    setLoading(false);
                }
            })
            .catch((err) => {
                if (!cancelled) {
                    setError(err.message);
                    setLoading(false);
                }
            });

        return () => { cancelled = true; };
    }, [filters?.plant, filters?.equipType, filters?.dateRange]);

    return { data, loading, error };
};

export default useDashboard;
