import React from 'react';
import {
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Area,
    AreaChart,
} from 'recharts';

const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
        return (
            <div className="chart-tooltip">
                <p style={{ color: 'var(--text-secondary)', marginBottom: 4, fontSize: '0.78rem', fontWeight: 600 }}>{label}</p>
                <p style={{ color: '#7c6bff', fontWeight: 700, margin: 0 }}>
                    MTTR: {payload[0].value} hrs
                </p>
            </div>
        );
    }
    return null;
};

const MTTRChart = ({ data }) => {
    if (!data || data.length === 0) {
        return (
            <div className="chart-empty">No MTTR data available for the last 12 months.</div>
        );
    }

    const chartData = data.map(d => ({ ...d, avgMttr: Number(d.avgMttr) }));

    return (
        <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <defs>
                    <linearGradient id="mttrGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#7c6bff" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#7c6bff" stopOpacity={0.02} />
                    </linearGradient>
                </defs>

                {/* Subtle horizontal grid lines — readable on light theme */}
                <CartesianGrid
                    strokeDasharray="4 4"
                    stroke="rgba(60,61,63,0.10)"
                    vertical={false}
                />

                <XAxis
                    dataKey="month"
                    tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                />
                <YAxis
                    tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    unit=" h"
                    width={40}
                />
                <Tooltip
                    content={<CustomTooltip />}
                    cursor={{ stroke: 'rgba(124,107,255,0.25)', strokeWidth: 1 }}
                />
                <Area
                    type="monotone"
                    dataKey="avgMttr"
                    stroke="#7c6bff"
                    strokeWidth={2.5}
                    fill="url(#mttrGradient)"
                    dot={{ r: 4, fill: '#7c6bff', strokeWidth: 0 }}
                    activeDot={{ r: 6, fill: '#a78bfa' }}
                />
            </AreaChart>
        </ResponsiveContainer>
    );
};

export default MTTRChart;
