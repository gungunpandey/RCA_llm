import React from 'react';

/* Same gradient palette as FailuresPieChart for consistent colors by position */
const GRADIENTS = [
    ['#7c6bff', '#a78bfa'],
    ['#06b6d4', '#38bdf8'],
    ['#10b981', '#4ade80'],
    ['#f59e0b', '#ffd93d'],
    ['#ef4444', '#ff6b6b'],
];

const TopEquipment = ({ data }) => {
    if (!data || data.length === 0) {
        return <div className="chart-empty">No equipment data available.</div>;
    }

    const max = data[0]?.breakdown_count || 1;
    const total = data.reduce((s, d) => s + (d.breakdown_count || 0), 0) || 1;

    return (
        <div className="top-equip-list">
            {data.map((item, i) => {
                const pct = Math.round((item.breakdown_count / max) * 100);
                const pctOfTotal = total > 0 ? Math.round((item.breakdown_count / total) * 100) : 0;
                const [gradStart, gradEnd] = GRADIENTS[i % GRADIENTS.length];
                return (
                    <div key={item.asset_tag} className="top-equip-row">
                        <div className="top-equip-rank">{i + 1}</div>
                        <div className="top-equip-info">
                            <div className="top-equip-header">
                                <span className="top-equip-name">{item.equipment_name}</span>
                                <span className="top-equip-count">
                                    {item.breakdown_count} {item.breakdown_count === 1 ? 'failure' : 'failures'}
                                    <span className="top-equip-pct"> ({pctOfTotal}%)</span>
                                </span>
                            </div>
                            <div className="top-equip-meta">
                                <span className="tag">{item.asset_tag}</span>
                                <span className="category-tag">{item.category}</span>
                            </div>
                            <div className="progress-bar-track">
                                <div
                                    className="progress-bar-fill"
                                    style={{
                                        width: `${pct}%`,
                                        background: `linear-gradient(90deg, ${gradStart}, ${gradEnd})`,
                                    }}
                                />
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
};

export default TopEquipment;
