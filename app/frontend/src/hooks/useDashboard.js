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
const useDashboard = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        let cancelled = false;

        Promise.all([
            fetchSummary(),
            fetchTopEquipment(),
            fetchBreakdowns(),
            fetchFailuresByAsset(),
            fetchRCAReports(),
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
    }, []);

    return { data, loading, error };
};

export default useDashboard;
