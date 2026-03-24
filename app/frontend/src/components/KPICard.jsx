import React from 'react';

const KPICard = ({ icon, label, value, sub, accentColor = '#7c6bff', trendLabel, trendUp }) => {
    return (
        <div className="glass-card kpi-card fade-in">
            <div className="kpi-icon" style={{ background: `${accentColor}22`, color: accentColor }}>
                {icon}
            </div>
            <div className="kpi-body">
                <p className="kpi-label">{label}</p>
                <p className="kpi-value" style={{ color: accentColor, fontSize: '2.4rem' }}>
                    {value ?? '—'}
                </p>
                {sub && <p className="kpi-sub">{sub}</p>}
                {trendLabel && (
                    <span className={`kpi-trend-label ${trendUp ? 'trend-label-up' : 'trend-label-down'}`}>
                        {trendUp ? '▲' : '▼'} {trendLabel}
                    </span>
                )}
            </div>
        </div>
    );
};

export default KPICard;
