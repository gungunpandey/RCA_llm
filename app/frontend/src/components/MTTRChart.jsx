import React from 'react';
import {
    XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, Area, AreaChart, ReferenceLine,
} from 'recharts';

const ACCENT = '#f97316'; // orange — distinct from purple/teal elsewhere

const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="chart-tooltip">
            <p style={{ color: 'var(--text-secondary)', marginBottom: 4, fontSize: '0.78rem', fontWeight: 600 }}>{label}</p>
            <p style={{ color: ACCENT, fontWeight: 700, margin: 0 }}>
                BD Hours: <strong>{Number(payload[0].value).toFixed(1)} h</strong>
            </p>
        </div>
    );
};

const BDHoursChart = ({ data }) => {
    if (!data || data.length === 0) {
        return <div className="chart-empty">No BD Hours data available.</div>;
    }

    const chartData = data.map(d => ({ ...d, avgMttr: Number(d.avgMttr) }));
    const avg = chartData.reduce((s, d) => s + d.avgMttr, 0) / chartData.length;

    return (
        <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <defs>
                    <linearGradient id="bdGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor={ACCENT} stopOpacity={0.28} />
                        <stop offset="95%" stopColor={ACCENT} stopOpacity={0.02} />
                    </linearGradient>
                </defs>

                <CartesianGrid strokeDasharray="4 4" stroke="rgba(60,61,63,0.10)" vertical={false} />

                {/* Average reference line */}
                <ReferenceLine
                    y={avg}
                    stroke="rgba(249,115,22,0.45)"
                    strokeDasharray="6 3"
                    label={{ value: `Avg ${avg.toFixed(1)}h`, position: 'right', fontSize: 10, fill: ACCENT }}
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
                    width={44}
                />
                <Tooltip
                    content={<CustomTooltip />}
                    cursor={{ stroke: `${ACCENT}40`, strokeWidth: 1 }}
                />
                <Area
                    type="monotone"
                    dataKey="avgMttr"
                    name="BD Hours"
                    stroke={ACCENT}
                    strokeWidth={2.5}
                    fill="url(#bdGradient)"
                    dot={{ r: 4, fill: ACCENT, strokeWidth: 0 }}
                    activeDot={{ r: 6, fill: '#fb923c' }}
                />
            </AreaChart>
        </ResponsiveContainer>
    );
};

export default BDHoursChart;
