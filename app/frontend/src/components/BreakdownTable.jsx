import React from 'react';

const STATUS_COLORS = {
    'Open': { color: '#ff6b6b', bg: 'rgba(255,107,107,0.15)' },
    'In Progress': { color: '#ffd93d', bg: 'rgba(255,217,61,0.15)' },
    'Resolved': { color: '#4ade80', bg: 'rgba(74,222,128,0.15)' },
    'Completed': { color: '#4ade80', bg: 'rgba(74,222,128,0.15)' },
    'Closed': { color: '#4ade80', bg: 'rgba(74,222,128,0.15)' },
};

const formatDate = (dt) => {
    if (!dt) return '—';
    return new Date(dt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
};

const BreakdownTable = ({ data }) => {
    if (!data || data.length === 0) {
        return <div className="chart-empty">No breakdown records found.</div>;
    }

    return (
        <div className="bd-table-wrapper">
            <table className="bd-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Equipment</th>
                        <th>Asset Tag</th>
                        <th>Description</th>
                        <th>Status</th>
                        <th>Reported</th>
                        <th>MTTR (hrs)</th>
                    </tr>
                </thead>
                <tbody>
                    {data.map((row, i) => {
                        const sc = STATUS_COLORS[row.status] ?? { color: '#f0f0f0', bg: 'rgba(255,255,255,0.1)' };
                        return (
                            <tr key={row.id} className="bd-row">
                                <td style={{ color: 'var(--text-secondary)', width: 32 }}>{i + 1}</td>
                                <td style={{ fontWeight: 600 }}>{row.equipment_name}</td>
                                <td>
                                    <span className="tag">{row.asset_tag}</span>
                                </td>
                                <td style={{ color: 'var(--text-secondary)', maxWidth: 220 }}>
                                    <span className="ellipsis">{row.description || '—'}</span>
                                </td>
                                <td>
                                    <span
                                        className="status-badge"
                                        style={{ color: sc.color, background: sc.bg }}
                                    >
                                        {row.status}
                                    </span>
                                </td>
                                <td style={{ color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                                    {formatDate(row.reported_at)}
                                </td>
                                <td style={{ fontWeight: 600, textAlign: 'center' }}>
                                    {row.mttr_hours != null ? Number(row.mttr_hours).toFixed(1) : '—'}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
};

export default BreakdownTable;
