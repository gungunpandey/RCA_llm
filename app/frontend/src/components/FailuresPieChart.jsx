import React, { useState } from 'react';
import {
    PieChart,
    Pie,
    Cell,
    Tooltip,
    ResponsiveContainer,
} from 'recharts';

/* ── Gradient colour pairs [start, end] ─────────────────────── */
const GRADIENTS = [
    ['#7c6bff', '#a78bfa'],
    ['#06b6d4', '#38bdf8'],
    ['#10b981', '#4ade80'],
    ['#f59e0b', '#ffd93d'],
    ['#ef4444', '#ff6b6b'],
    ['#8b5cf6', '#d946ef'],
    ['#f97316', '#fb923c'],
    ['#0ea5e9', '#67e8f9'],
];

/* ── Custom tooltip ──────────────────────────────────────────── */
const CustomTooltip = ({ active, payload, total }) => {
    if (!active || !payload?.length) return null;
    const item = payload[0];
    const pct = total > 0 ? ((item.value / total) * 100).toFixed(1) : '0.0';
    const gradIndex = item.payload?.gradIndex ?? 0;
    const accent = GRADIENTS[gradIndex % GRADIENTS.length][1];
    return (
        <div style={{
            background: 'rgba(12,12,28,0.94)',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 12,
            padding: '10px 16px',
            backdropFilter: 'blur(14px)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            minWidth: 160,
        }}>
            <p style={{ margin: '0 0 5px', fontSize: '0.73rem', color: 'rgba(200,200,220,0.6)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                {item.name}
            </p>
            <p style={{ margin: 0, fontWeight: 700, fontSize: '1.1rem', color: '#fff' }}>
                {item.value}
                <span style={{ fontSize: '0.78rem', fontWeight: 400, color: 'rgba(200,200,220,0.55)', marginLeft: 6 }}>
                    breakdowns
                </span>
            </p>
            <p style={{ margin: '4px 0 0', fontWeight: 600, fontSize: '0.84rem', color: accent }}>
                {pct}% of total
            </p>
        </div>
    );
};

/* ── Center label ────────────────────────────────────────────── */
const CenterText = ({ width, height, total }) => {
    const cx = (width ?? 400) / 2;
    const cy = (height ?? 260) * 0.5;
    return (
        <>
            <text x={cx} y={cy - 9} textAnchor="middle" dominantBaseline="middle"
                fill="#ffffff" fontSize={28} fontWeight={800} fontFamily="inherit" letterSpacing="-0.5">
                {total}
            </text>
            <text x={cx} y={cy + 15} textAnchor="middle" dominantBaseline="middle"
                fill="rgba(200,200,220,0.5)" fontSize={10} fontWeight={500} fontFamily="inherit" letterSpacing="1.5">
                TOTAL
            </text>
        </>
    );
};

/* ── Inner depth ─────────────────────────────────────────────── */
const InnerDepth = ({ width, height }) => {
    const cx = (width ?? 400) / 2;
    const cy = (height ?? 260) * 0.5;
    return <circle cx={cx} cy={cy} r={67} fill="url(#innerDepth)" />;
};

/* ── Active segment ──────────────────────────────────────────── */
const ActiveShape = ({ cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill, gradIndex }) => {
    const RADIAN = Math.PI / 180;
    const r = outerRadius + 10;
    const ir = innerRadius;
    const sweep = Math.abs(endAngle - startAngle) > 180 ? 1 : 0;
    const x1 = cx + r * Math.cos(-startAngle * RADIAN);
    const y1 = cy + r * Math.sin(-startAngle * RADIAN);
    const x2 = cx + r * Math.cos(-endAngle * RADIAN);
    const y2 = cy + r * Math.sin(-endAngle * RADIAN);
    const ix1 = cx + ir * Math.cos(-startAngle * RADIAN);
    const iy1 = cy + ir * Math.sin(-startAngle * RADIAN);
    const ix2 = cx + ir * Math.cos(-endAngle * RADIAN);
    const iy2 = cy + ir * Math.sin(-endAngle * RADIAN);
    const d = `M ${x1} ${y1} A ${r} ${r} 0 ${sweep} 0 ${x2} ${y2} L ${ix2} ${iy2} A ${ir} ${ir} 0 ${sweep} 1 ${ix1} ${iy1} Z`;
    return (
        <path
            d={d}
            fill={`url(#grad${gradIndex % GRADIENTS.length})`}
            filter={`url(#glow${gradIndex % GRADIENTS.length})`}
            opacity={0.92}
        />
    );
};

/* ── Main ────────────────────────────────────────────────────── */
const FailuresPieChart = ({ data }) => {
    const [activeIndex, setActiveIndex] = useState(null);

    if (!data || data.length === 0) {
        return <div className="chart-empty">No failure data available.</div>;
    }

    const chartData = data.map((d, i) => ({
        name: d.category,
        value: d.count,
        gradIndex: i,
    }));
    const total = chartData.reduce((s, d) => s + d.value, 0);

    return (
        <div style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* SVG defs */}
            <svg width={0} height={0} style={{ position: 'absolute', pointerEvents: 'none' }}>
                <defs>
                    {GRADIENTS.map(([start, end], i) => (
                        <linearGradient key={`g${i}`} id={`grad${i}`} x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%"   stopColor={start} />
                            <stop offset="100%" stopColor={end} />
                        </linearGradient>
                    ))}
                    {GRADIENTS.map(([, end], i) => (
                        <filter key={`f${i}`} id={`glow${i}`} x="-30%" y="-30%" width="160%" height="160%">
                            <feGaussianBlur stdDeviation="5" result="blur" />
                            <feColorMatrix in="blur" type="matrix"
                                values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.8 0" result="coloredBlur" />
                            <feMerge>
                                <feMergeNode in="coloredBlur" />
                                <feMergeNode in="SourceGraphic" />
                            </feMerge>
                        </filter>
                    ))}
                    <filter id="spec3d" x="-15%" y="-15%" width="130%" height="130%">
                        <feGaussianBlur in="SourceAlpha" stdDeviation="4" result="specBlur" />
                        <feSpecularLighting in="specBlur" surfaceScale="6" specularConstant="1.4"
                            specularExponent="32" lightingColor="rgba(255,255,255,0.65)" result="specLight">
                            <fePointLight x="160" y="-220" z="380" />
                        </feSpecularLighting>
                        <feComposite in="specLight" in2="SourceAlpha" operator="in" result="specClipped" />
                        <feMerge>
                            <feMergeNode in="SourceGraphic" />
                            <feMergeNode in="specClipped" />
                        </feMerge>
                    </filter>
                    <radialGradient id="innerDepth" cx="38%" cy="30%" r="72%">
                        <stop offset="0%"   stopColor="rgba(0,0,0,0)" />
                        <stop offset="75%"  stopColor="rgba(0,0,0,0.18)" />
                        <stop offset="100%" stopColor="rgba(0,0,0,0.5)" />
                    </radialGradient>
                </defs>
            </svg>

            {/* ── Donut (left, ~60%) ───────────────────────── */}
            <div style={{ flex: '0 0 58%', filter: 'drop-shadow(0 16px 12px rgba(0,0,0,0.42))' }}>
                <ResponsiveContainer width="100%" height={260}>
                    <PieChart
                        customized={[
                            (props) => <InnerDepth key="inner" {...props} />,
                            (props) => <CenterText key="center" {...props} total={total} />,
                        ]}
                    >
                        <Pie
                            data={chartData}
                            cx="50%"
                            cy="50%"
                            innerRadius={70}
                            outerRadius={110}
                            paddingAngle={3}
                            dataKey="value"
                            labelLine={false}
                            isAnimationActive
                            animationBegin={100}
                            animationDuration={950}
                            animationEasing="ease-out"
                            onMouseEnter={(_, index) => setActiveIndex(index)}
                            onMouseLeave={() => setActiveIndex(null)}
                            activeIndex={activeIndex ?? undefined}
                            activeShape={(props) => (
                                <ActiveShape
                                    {...props}
                                    gradIndex={chartData[props.index ?? activeIndex]?.gradIndex ?? 0}
                                />
                            )}
                        >
                            {chartData.map((entry, i) => (
                                <Cell
                                    key={`cell-${i}`}
                                    fill={`url(#grad${i % GRADIENTS.length})`}
                                    stroke="rgba(255,255,255,0.08)"
                                    strokeWidth={2}
                                    filter="url(#spec3d)"
                                    opacity={activeIndex === null || activeIndex === i ? 1 : 0.4}
                                    style={{ cursor: 'pointer', transition: 'opacity 0.2s ease' }}
                                />
                            ))}
                        </Pie>
                        <Tooltip
                            content={<CustomTooltip total={total} />}
                            wrapperStyle={{ outline: 'none', zIndex: 10 }}
                        />
                    </PieChart>
                </ResponsiveContainer>
            </div>

            {/* ── Legend (right, ~40%, vertical) ──────────── */}
            <div style={{
                flex: '0 0 38%',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
                paddingLeft: 4,
            }}>
                {chartData.map((entry, i) => {
                    const [start, end] = GRADIENTS[i % GRADIENTS.length];
                    const isActive = activeIndex === i;
                    const pct = total > 0 ? ((entry.value / total) * 100).toFixed(0) : '0';
                    return (
                        <div
                            key={entry.name}
                            onMouseEnter={() => setActiveIndex(i)}
                            onMouseLeave={() => setActiveIndex(null)}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 8,
                                cursor: 'pointer',
                                opacity: activeIndex === null || isActive ? 1 : 0.45,
                                transition: 'all 0.2s ease',
                                padding: '5px 10px',
                                borderRadius: 8,
                                background: isActive ? 'rgba(255,255,255,0.06)' : 'transparent',
                                border: isActive ? `1px solid ${end}55` : '1px solid transparent',
                            }}
                        >
                            <span style={{
                                width: 10,
                                height: 10,
                                borderRadius: '50%',
                                background: `linear-gradient(135deg, ${start}, ${end})`,
                                boxShadow: isActive ? `0 0 7px ${end}` : 'none',
                                flexShrink: 0,
                                transition: 'box-shadow 0.2s',
                            }} />
                            <span style={{
                                flex: 1,
                                fontSize: '0.78rem',
                                color: 'var(--text-primary)',
                                fontWeight: isActive ? 600 : 400,
                                transition: 'color 0.2s',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                            }}>
                                {entry.name}
                            </span>
                            <span style={{
                                fontSize: '0.72rem',
                                fontWeight: 700,
                                color: isActive ? end : 'var(--text-secondary)',
                                transition: 'color 0.2s',
                                flexShrink: 0,
                            }}>
                                {pct}%
                            </span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default FailuresPieChart;
