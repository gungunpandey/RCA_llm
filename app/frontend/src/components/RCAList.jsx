import React from 'react';

const formatDate = (dt) => {
    if (!dt) return '—';
    return new Date(dt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
};

const RCAList = ({ data }) => {
    if (!data || data.length === 0) {
        return <div className="chart-empty">No RCA reports filed yet.</div>;
    }

    return (
        <div className="rca-list">
            {data.map((report) => (
                <div key={report.id} className="rca-card glass-card fade-in">
                    <div className="rca-header">
                        <div className="rca-equip">
                            <span className="rca-icon">🔍</span>
                            <span className="rca-equip-name">{report.equipment_name}</span>
                        </div>
                        <span className="rca-date">{formatDate(report.created_at)}</span>
                    </div>

                    {/* Root Cause section */}
                    <div className="rca-section rca-section-cause">
                        <span className="rca-section-label">Root Cause</span>
                        <p className="rca-cause">{report.root_cause}</p>
                    </div>

                    {/* Corrective Action section */}
                    {report.corrective_action && (
                        <div className="rca-section rca-section-action">
                            <span className="rca-section-label">Action</span>
                            <p className="rca-action">{report.corrective_action}</p>
                        </div>
                    )}

                    <p className="rca-author">Filed by: {report.author_email}</p>
                </div>
            ))}
        </div>
    );
};

export default RCAList;
