import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import NavBar from '../components/NavBar';
import { fetchAnalytics, fetchDrillDown, fetchProdaiIntelligence } from '../api/analytics';
import {
    ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
    AreaChart, Area, Cell,
} from 'recharts';

const ACCENT = '#33B1B0';
const ACCENT2 = '#7c6bff';
const BAR_COLORS = ['#33B1B0','#7c6bff','#f59e0b','#ef4444','#10b981','#f97316','#8b5cf6','#06b6d4','#fb923c','#4ade80'];

const RANGES = [
    { label: '30D', value: '30d' },
    { label: '3M',  value: '3m'  },
    { label: '6M',  value: '6m'  },
    { label: '1Y',  value: '1y'  },
];

const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' }) : '—';
const fmtMttr = (v) => (v != null && v > 0) ? `${v} h` : '—';

const SectionTitle = ({ children }) => (
    <p className="section-title">{children}</p>
);

const EmptyState = ({ icon = '📭', message = 'No data for this period.' }) => (
    <div style={{ textAlign:'center', padding:'40px 0', color:'var(--text-secondary)' }}>
        <div style={{ fontSize:'2rem', marginBottom:8 }}>{icon}</div>
        <p style={{ fontSize:'0.88rem' }}>{message}</p>
    </div>
);

const ChartTooltipBar = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="chart-tooltip">
            <p style={{ color:'var(--text-secondary)', fontSize:'0.78rem', fontWeight:600, marginBottom:4 }}>{label}</p>
            {payload.map((p, i) => (
                <p key={i} style={{ color: p.color || ACCENT, fontWeight:700, margin:0, fontSize:'0.9rem' }}>
                    {p.name}: {p.value}
                </p>
            ))}
        </div>
    );
};

const TrendTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="chart-tooltip">
            <p style={{ color:'var(--text-secondary)', fontSize:'0.78rem', fontWeight:600, marginBottom:4 }}>{label}</p>
            {payload.map((p, i) => (
                <p key={i} style={{ color: p.color, fontWeight:700, margin:'2px 0', fontSize:'0.88rem' }}>
                    {p.name === 'failures' ? `Failures: ${p.value}` : `MTTR: ${p.value} h`}
                </p>
            ))}
        </div>
    );
};

const SeverityBadge = ({ v }) => {
    const map = { Critical:['#ff5e5e','rgba(255,94,94,0.12)'], High:['#fb923c','rgba(251,146,60,0.12)'], Medium:['#ffd93d','rgba(255,217,61,0.12)'], Low:['#4ade80','rgba(74,222,128,0.12)'] };
    const [color, bg] = map[v] || ['#aaa','rgba(170,170,170,0.12)'];
    return <span style={{ display:'inline-flex', alignItems:'center', padding:'2px 8px', borderRadius:99, fontSize:'0.7rem', fontWeight:700, color, background:bg, whiteSpace:'nowrap' }}>{v || '—'}</span>;
};

const HistoricalAnalyticsPage = () => {
    const { user } = useAuth();
    const [range, setRange] = useState('3m');
    const [specificMonth, setSpecificMonth] = useState('');
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [drillTag, setDrillTag] = useState(null);
    const [drillName, setDrillName] = useState('');
    const [drillData, setDrillData] = useState([]);
    const [drillLoading, setDrillLoading] = useState(false);
    const [genLoading, setGenLoading] = useState(false);
    const [genError, setGenError] = useState('');
    const [intel, setIntel] = useState(null);
    const [intelLoading, setIntelLoading] = useState(true);

    const load = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const res = await fetchAnalytics({ range, month: specificMonth });
            setData(res);
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, [range, specificMonth]);

    useEffect(() => { load(); }, [load]);

    // ProdAI intelligence (reliability score, patterns, prioritized actions)
    useEffect(() => {
        let cancelled = false;
        setIntelLoading(true);
        fetchProdaiIntelligence({ range, month: specificMonth })
            .then(r => { if (!cancelled) setIntel(r); })
            .catch(() => { if (!cancelled) setIntel(null); })
            .finally(() => { if (!cancelled) setIntelLoading(false); });
        return () => { cancelled = true; };
    }, [range, specificMonth]);

    const openDrill = async (tag, name) => {
        setDrillTag(tag);
        setDrillName(name);
        setDrillData([]);
        setDrillLoading(true);
        try {
            const rows = await fetchDrillDown({ tag, range, month: specificMonth });
            setDrillData(rows);
        } catch { setDrillData([]); }
        finally { setDrillLoading(false); }
    };
    const closeDrill = () => setDrillTag(null);

    const generateReview = async () => {
        setGenLoading(true);
        setGenError('');
        try {
            const p = new URLSearchParams({ range });
            if (specificMonth) p.append('month', specificMonth);
            const resp = await fetch(`/api/reliability-review?${p}`, {
                method: 'POST',
                credentials: 'include',
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || `Failed to generate review (${resp.status})`);
            }
            // Extract filename from Content-Disposition, fall back to a default.
            const cd = resp.headers.get('Content-Disposition') || '';
            const match = cd.match(/filename="?([^"]+)"?/);
            const filename = match ? match[1] : 'Reliability_Review.pptx';
            const blob = await resp.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (e) {
            setGenError(e.message || 'Could not generate the reliability review.');
        } finally {
            setGenLoading(false);
        }
    };

    const handleMonthChange = (e) => {
        const val = e.target.value;
        if (val) {
            const d = new Date(val + '-01');
            const label = d.toLocaleDateString('en-US', { month:'short', year:'numeric' });
            setSpecificMonth(label);
        } else {
            setSpecificMonth('');
        }
    };

    if (!user) return null;

    const { freq = [], rootCause = [], repeat = [], trend = [], top = null, direction = null } = data || {};

    const trendPct = direction?.pct;
    const trendUp = direction?.direction === 'up';
    const trendDown = direction?.direction === 'down';

    return (
        <div className="db-page">
            <div className="db-blob db-blob-1" />
            <div className="db-blob db-blob-2" />

            <NavBar activePage="analytics" />

            {/* ── Header ── */}
            <div className="bl-hero fade-in" style={{ maxWidth:'100%' }}>
                <div className="bl-hero-icon">📊</div>
                <div style={{ flex:1 }}>
                    <h1 className="bl-hero-title">Historical Failure Analytics</h1>
                    <p className="bl-hero-sub">Analyze failure patterns, root causes, and trends over time.</p>
                </div>
                {/* Time filters */}
                <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                    <div style={{ display:'flex', gap:4, background:'rgba(51,177,176,0.07)', borderRadius:10, padding:4 }}>
                        {RANGES.map(r => (
                            <button
                                key={r.value}
                                onClick={() => { setRange(r.value); setSpecificMonth(''); }}
                                style={{
                                    padding:'5px 12px', borderRadius:7, border:'none', cursor:'pointer',
                                    fontSize:'0.8rem', fontWeight:700, fontFamily:'inherit',
                                    background: range === r.value && !specificMonth ? ACCENT : 'transparent',
                                    color: range === r.value && !specificMonth ? '#fff' : 'var(--text-secondary)',
                                    transition:'all 0.2s',
                                }}
                            >{r.label}</button>
                        ))}
                    </div>
                    <input
                        type="month"
                        className="form-input"
                        style={{ maxWidth:160, fontSize:'0.82rem', padding:'6px 10px' }}
                        onChange={handleMonthChange}
                        title="Pick a specific month"
                    />
                </div>
            </div>

            {genError && (
                <div className="bl-banner bl-error fade-in" style={{ maxWidth:'100%', position:'relative', zIndex:1 }}>⚠️ {genError}</div>
            )}

            {error && (
                <div className="bl-banner bl-error fade-in" style={{ maxWidth:'100%', position:'relative', zIndex:1 }}>⚠️ {error}</div>
            )}

            {loading ? (
                <div style={{ textAlign:'center', padding:64 }}>
                    <span className="spinner" style={{ display:'inline-block', borderTopColor:ACCENT, borderColor:'rgba(51,177,176,0.2)', width:28, height:28, borderWidth:3 }} />
                    <p style={{ marginTop:14, color:'var(--text-secondary)', fontSize:'0.88rem' }}>Loading analytics…</p>
                </div>
            ) : (
                <div className="db-main fade-in">

                    {/* ════ ProdAI Intelligence (top features) ════ */}
                    {intelLoading && !intel ? (
                        <div className="glass-card db-panel" style={{ textAlign:'center', padding:32, color:'var(--text-secondary)', fontSize:'0.85rem' }}>
                            <span className="spinner" style={{ display:'inline-block', borderTopColor:ACCENT, borderColor:'rgba(51,177,176,0.2)', width:20, height:20, borderWidth:2, marginRight:8, verticalAlign:'middle' }} />
                            Computing ProdAI intelligence…
                        </div>
                    ) : intel && (
                        <>
                            {/* Row A: Reliability Score + Generate PPT */}
                            <div style={{ display:'grid', gridTemplateColumns:'1.3fr 1fr', gap:16 }}>
                                {/* Reliability Score scorecard */}
                                {(() => {
                                    const r = intel.reliability || {};
                                    const sc = r.score ?? 0;
                                    const col = sc >= 85 ? '#16a34a' : sc >= 70 ? ACCENT : sc >= 50 ? '#f59e0b' : '#ef4444';
                                    return (
                                        <div className="glass-card db-panel">
                                            <SectionTitle>🎯 Reliability Score</SectionTitle>
                                            <div style={{ display:'flex', gap:20, alignItems:'center', flexWrap:'wrap' }}>
                                                <div style={{ width:128, height:128, borderRadius:'50%', flexShrink:0,
                                                    display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center',
                                                    background:`conic-gradient(${col} ${sc*3.6}deg, rgba(60,61,63,0.08) 0deg)` }}>
                                                    <div style={{ width:104, height:104, borderRadius:'50%', background:'#fff',
                                                        display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center' }}>
                                                        <span style={{ fontSize:'2.2rem', fontWeight:800, color:col, lineHeight:1 }}>{sc}</span>
                                                        <span style={{ fontSize:'0.7rem', color:'var(--text-secondary)' }}>/ 100</span>
                                                    </div>
                                                </div>
                                                <div style={{ flex:1, minWidth:200 }}>
                                                    <span style={{ display:'inline-block', padding:'3px 12px', borderRadius:99, fontSize:'0.78rem',
                                                        fontWeight:700, color:col, background:`${col}1a`, marginBottom:8 }}>{r.grade}</span>
                                                    <div style={{ fontSize:'0.78rem', color:'var(--text-secondary)', fontWeight:700, margin:'6px 0 3px' }}>KEY DRIVERS</div>
                                                    <ul style={{ margin:0, paddingLeft:16, fontSize:'0.82rem', color:'var(--text-primary)' }}>
                                                        {(r.drivers || []).slice(0,3).map((d,i) => <li key={i}>{d}</li>)}
                                                    </ul>
                                                    <div style={{ fontSize:'0.78rem', color:'var(--text-secondary)', fontWeight:700, margin:'8px 0 3px' }}>💡 IMPROVEMENT OPPORTUNITIES</div>
                                                    <ul style={{ margin:0, paddingLeft:16, fontSize:'0.82rem', color:'var(--text-primary)' }}>
                                                        {(r.opportunities || []).slice(0,3).map((o,i) => <li key={i}>{o}</li>)}
                                                    </ul>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })()}

                                {/* Generate Reliability Review (PPT) — clear dedicated card */}
                                <div className="glass-card db-panel" style={{ display:'flex', flexDirection:'column', justifyContent:'center', textAlign:'center', gap:10 }}>
                                    <div style={{ fontSize:'2.2rem' }}>📑</div>
                                    <h3 style={{ margin:0, fontSize:'1.05rem', fontWeight:800, color:'var(--text-primary)' }}>AI Reliability Review</h3>
                                    <p style={{ margin:0, fontSize:'0.82rem', color:'var(--text-secondary)', lineHeight:1.5 }}>
                                        Generate a ready-to-present <strong>PowerPoint deck</strong> (charts, risks, CAPA effectiveness &amp; recommended actions) for the selected period.
                                    </p>
                                    <button onClick={generateReview} disabled={genLoading} className="btn"
                                        style={{ display:'inline-flex', alignItems:'center', justifyContent:'center', gap:8, alignSelf:'center',
                                            padding:'10px 20px', borderRadius:10, border:'none', cursor: genLoading ? 'default':'pointer',
                                            fontSize:'0.88rem', fontWeight:700, fontFamily:'inherit', color:'#fff', marginTop:4,
                                            background: genLoading ? 'rgba(51,177,176,0.6)' : ACCENT, boxShadow:'0 4px 14px rgba(51,177,176,0.3)' }}>
                                        {genLoading ? (
                                            <><span className="spinner" style={{ width:14, height:14, borderWidth:2, borderTopColor:'#fff', borderColor:'rgba(255,255,255,0.4)' }} /> Generating PPT…</>
                                        ) : (<>⬇ Generate PowerPoint</>)}
                                    </button>
                                    {genError && <p style={{ color:'#ef4444', fontSize:'0.78rem', margin:0 }}>⚠️ {genError}</p>}
                                </div>
                            </div>

                            {/* Row B: AI Action Prioritizer */}
                            <div className="glass-card db-panel">
                                <SectionTitle>⚡ AI Action Prioritizer</SectionTitle>
                                <p style={{ fontSize:'0.75rem', color:'var(--text-secondary)', margin:'-8px 0 12px' }}>What to address first, ranked from failures, RCA &amp; CAPA status.</p>
                                <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                                    {(intel.actions || []).map((a) => {
                                        const pc = { Critical:'#ef4444', High:'#fb923c', Medium:'#f59e0b', Low:'#94a3b8' }[a.priority] || '#94a3b8';
                                        return (
                                            <div key={a.rank} style={{ display:'flex', gap:12, alignItems:'flex-start',
                                                padding:'10px 14px', borderRadius:10, background:'rgba(51,177,176,0.04)', border:'1px solid rgba(51,177,176,0.12)' }}>
                                                <span style={{ width:24, height:24, borderRadius:'50%', flexShrink:0, background:ACCENT, color:'#fff',
                                                    display:'flex', alignItems:'center', justifyContent:'center', fontSize:'0.78rem', fontWeight:800 }}>{a.rank}</span>
                                                <div style={{ flex:1 }}>
                                                    <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                                                        <span style={{ fontWeight:700, fontSize:'0.88rem', color:'var(--text-primary)' }}>{a.title}</span>
                                                        <span style={{ fontSize:'0.66rem', fontWeight:700, color:pc, background:`${pc}1a`, padding:'1px 8px', borderRadius:99 }}>{a.priority}</span>
                                                    </div>
                                                    <p style={{ margin:'2px 0 0', fontSize:'0.8rem', color:'var(--text-secondary)' }}>{a.why}</p>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Row C: Failure Pattern Explorer */}
                            <div className="glass-card db-panel">
                                <SectionTitle>🔍 Failure Pattern Explorer</SectionTitle>
                                <p style={{ fontSize:'0.75rem', color:'var(--text-secondary)', margin:'-8px 0 12px' }}>Hidden patterns surfaced from historical data.</p>
                                <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(240px, 1fr))', gap:12 }}>
                                    {(intel.patterns || []).map((p, i) => {
                                        const col = { danger:'#ef4444', warning:'#f59e0b', info:ACCENT, success:'#16a34a' }[p.type] || ACCENT;
                                        return (
                                            <div key={i} style={{ padding:'12px 14px', borderRadius:11, background:'#fff',
                                                border:'1px solid rgba(148,163,184,0.18)', borderLeft:`3px solid ${col}` }}>
                                                <div style={{ fontWeight:700, fontSize:'0.85rem', color:'var(--text-primary)', marginBottom:3 }}>{p.icon} {p.title}</div>
                                                <p style={{ margin:0, fontSize:'0.8rem', color:'var(--text-secondary)', lineHeight:1.45 }}>{p.text}</p>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        </>
                    )}

                    {/* ── Row 1: Top Problematic + Trend ── */}
                    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
                        {/* Top Problematic */}
                        <div className="glass-card db-panel" style={{ position:'relative' }}>
                            <SectionTitle>🔴 Top Problematic Equipment</SectionTitle>
                            {!top ? <EmptyState icon="✅" message="No failures in this period." /> : (
                                <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
                                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
                                        <div>
                                            <p style={{ fontWeight:800, fontSize:'1.1rem', color:'var(--text-primary)', margin:0 }}>{top.equipment_name || '—'}</p>
                                            <span className="tag" style={{ marginTop:4, display:'inline-block' }}>{top.asset_tag}</span>
                                        </div>
                                        <div style={{ textAlign:'right' }}>
                                            <p style={{ fontWeight:800, fontSize:'1.8rem', color:'#ff5e5e', lineHeight:1, margin:0 }}>{top.failure_count}</p>
                                            <p style={{ fontSize:'0.7rem', color:'var(--text-secondary)', margin:0 }}>failures</p>
                                        </div>
                                    </div>
                                    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8 }}>
                                        {[
                                            { label:'Plant', value: top.category },
                                            { label:'Criticality', value: top.criticality },
                                            { label:'Avg MTTR', value: fmtMttr(top.avg_mttr) },
                                        ].map(({ label, value }) => (
                                            <div key={label} style={{ background:'rgba(51,177,176,0.05)', borderRadius:8, padding:'8px 10px' }}>
                                                <p style={{ fontSize:'0.68rem', color:'var(--text-secondary)', fontWeight:700, textTransform:'uppercase', letterSpacing:'0.06em', margin:'0 0 2px' }}>{label}</p>
                                                <p style={{ fontSize:'0.88rem', fontWeight:600, color:'var(--text-primary)', margin:0 }}>{value || '—'}</p>
                                            </div>
                                        ))}
                                    </div>
                                    <p style={{ fontSize:'0.75rem', color:'var(--text-secondary)', margin:0 }}>Last failure: {fmtDate(top.last_failure)}</p>
                                </div>
                            )}
                        </div>

                        {/* Trend Direction */}
                        <div className="glass-card db-panel">
                            <SectionTitle>📈 Failure Trend</SectionTitle>
                            {!direction ? <EmptyState /> : (
                                <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
                                    <div style={{ display:'flex', alignItems:'center', gap:16 }}>
                                        <span style={{ fontSize:'2.8rem', lineHeight:1 }}>
                                            {trendUp ? '📈' : trendDown ? '📉' : '➡️'}
                                        </span>
                                        <div>
                                            <p style={{ fontSize:'1.6rem', fontWeight:800, margin:0, color: trendUp ? '#ff5e5e' : trendDown ? '#4ade80' : 'var(--text-primary)' }}>
                                                {trendPct === null ? 'N/A' : `${trendUp ? '+' : ''}${trendPct}%`}
                                            </p>
                                            <p style={{ fontSize:'0.8rem', color:'var(--text-secondary)', margin:0 }}>
                                                {trendUp ? 'Failures increasing this period' : trendDown ? 'Failures decreasing this period' : 'Stable failure rate'}
                                            </p>
                                        </div>
                                    </div>
                                    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
                                        {[
                                            { label:'Recent Half', value: direction.recent },
                                            { label:'Prior Half', value: direction.previous },
                                        ].map(({ label, value }) => (
                                            <div key={label} style={{ background:'rgba(51,177,176,0.05)', borderRadius:8, padding:'8px 10px' }}>
                                                <p style={{ fontSize:'0.68rem', color:'var(--text-secondary)', fontWeight:700, textTransform:'uppercase', letterSpacing:'0.06em', margin:'0 0 2px' }}>{label}</p>
                                                <p style={{ fontSize:'1.1rem', fontWeight:800, color:'var(--text-primary)', margin:0 }}>{value}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* ── Row 2: Monthly Trend Chart ── */}
                    <div className="glass-card db-panel">
                        <SectionTitle>📅 Monthly Failure Trend</SectionTitle>
                        {!trend.length ? <EmptyState /> : (
                            <ResponsiveContainer width="100%" height={240}>
                                <AreaChart data={trend} margin={{ top:10, right:20, left:10, bottom:0 }}>
                                    <defs>
                                        <linearGradient id="aGrad1" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%"  stopColor={ACCENT}  stopOpacity={0.22} />
                                            <stop offset="95%" stopColor={ACCENT}  stopOpacity={0.02} />
                                        </linearGradient>
                                        <linearGradient id="aGrad2" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%"  stopColor={ACCENT2} stopOpacity={0.18} />
                                            <stop offset="95%" stopColor={ACCENT2} stopOpacity={0.01} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="4 4" stroke="rgba(60,61,63,0.10)" vertical={false} />
                                    <XAxis dataKey="period" tick={{ fill:'var(--text-secondary)', fontSize:11 }} axisLine={false} tickLine={false} />
                                    <YAxis yAxisId="left"  tick={{ fill:'var(--text-secondary)', fontSize:11 }} axisLine={false} tickLine={false} width={32} />
                                    <YAxis yAxisId="right" orientation="right" tick={{ fill:'var(--text-secondary)', fontSize:11 }} axisLine={false} tickLine={false} width={36} unit=" h" />
                                    <Tooltip content={<TrendTooltip />} cursor={{ stroke:'rgba(51,177,176,0.2)', strokeWidth:1 }} />
                                    <Area yAxisId="left"  type="monotone" dataKey="failures" name="failures" stroke={ACCENT}  strokeWidth={2.5} fill="url(#aGrad1)" dot={{ r:4, fill:ACCENT, strokeWidth:0 }} activeDot={{ r:6 }} />
                                    <Area yAxisId="right" type="monotone" dataKey="avg_mttr" name="avg_mttr" stroke={ACCENT2} strokeWidth={2} fill="url(#aGrad2)" dot={{ r:3, fill:ACCENT2, strokeWidth:0 }} activeDot={{ r:5 }} />
                                </AreaChart>
                            </ResponsiveContainer>
                        )}
                    </div>

                    {/* ── Row 3: Failure Frequency + Root Cause ── */}
                    <div className="db-mid-row">
                        {/* Failure by equipment */}
                        <div className="glass-card db-panel">
                            <SectionTitle>🔧 Failure Frequency by Equipment</SectionTitle>
                            <p style={{ fontSize:'0.75rem', color:'var(--text-secondary)', margin:'-8px 0 12px' }}>Click a bar to drill down</p>
                            {!freq.length ? <EmptyState icon="🟢" message="No failures in this period." /> : (
                                <ResponsiveContainer width="100%" height={260}>
                                    <BarChart data={freq} layout="vertical" margin={{ top:0, right:30, left:0, bottom:0 }}
                                        onClick={(e) => { if (e?.activePayload?.[0]) { const d = e.activePayload[0].payload; openDrill(d.asset_tag, d.equipment_name); } }}>
                                        <CartesianGrid strokeDasharray="4 4" stroke="rgba(60,61,63,0.08)" horizontal={false} />
                                        <XAxis type="number" tick={{ fill:'var(--text-secondary)', fontSize:11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                                        <YAxis type="category" dataKey="equipment_name" width={110} tick={{ fill:'var(--text-primary)', fontSize:11 }} axisLine={false} tickLine={false}
                                            tickFormatter={v => v?.length > 14 ? v.slice(0,13)+'…' : v} />
                                        <Tooltip content={<ChartTooltipBar />} cursor={{ fill:'rgba(51,177,176,0.06)' }} />
                                        <Bar dataKey="failure_count" name="Failures" radius={[0,6,6,0]} cursor="pointer">
                                            {freq.map((_, i) => <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />)}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            )}
                        </div>

                        {/* Root cause chart */}
                        <div className="glass-card db-panel">
                            <SectionTitle>🧠 Root Cause Categories</SectionTitle>
                            <p style={{ fontSize:'0.75rem', color:'var(--text-secondary)', margin:'-8px 0 12px' }}>By failure type</p>
                            {!rootCause.length ? <EmptyState icon="🟢" message="No failures in this period." /> : (
                                <>
                                    <ResponsiveContainer width="100%" height={200}>
                                        <BarChart data={rootCause} margin={{ top:0, right:20, left:10, bottom:20 }}>
                                            <CartesianGrid strokeDasharray="4 4" stroke="rgba(60,61,63,0.08)" vertical={false} />
                                            <XAxis dataKey="category" tick={{ fill:'var(--text-secondary)', fontSize:10 }} axisLine={false} tickLine={false}
                                                angle={-25} textAnchor="end" interval={0} />
                                            <YAxis tick={{ fill:'var(--text-secondary)', fontSize:11 }} axisLine={false} tickLine={false} width={28} allowDecimals={false} />
                                            <Tooltip content={<ChartTooltipBar />} cursor={{ fill:'rgba(51,177,176,0.06)' }} />
                                            <Bar dataKey="count" name="Count" radius={[6,6,0,0]}>
                                                {rootCause.map((_, i) => <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />)}
                                            </Bar>
                                        </BarChart>
                                    </ResponsiveContainer>
                                    <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginTop:8 }}>
                                        {rootCause.map((r, i) => (
                                            <div key={r.category} style={{ display:'flex', alignItems:'center', gap:5, padding:'3px 8px', background:'rgba(51,177,176,0.06)', borderRadius:6 }}>
                                                <span style={{ width:8, height:8, borderRadius:'50%', background:BAR_COLORS[i % BAR_COLORS.length], flexShrink:0 }} />
                                                <span style={{ fontSize:'0.72rem', color:'var(--text-secondary)' }}>{r.category}: <strong style={{ color:'var(--text-primary)' }}>{r.count}</strong></span>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>
                    </div>

                    {/* ── Row 4: Repeat Failures ── */}
                    <div className="glass-card db-panel">
                        <SectionTitle>🔁 Repeat Failure Detection</SectionTitle>
                        {!repeat.length ? (
                            <EmptyState icon="✅" message="No repeat failures detected in this period." />
                        ) : (
                            <div className="bd-table-wrapper">
                                <table className="bd-table">
                                    <thead>
                                        <tr>
                                            <th>Equipment</th>
                                            <th>Asset Tag</th>
                                            <th>Failures</th>
                                            <th>Avg Days Between</th>
                                            <th>Last Failure</th>
                                            <th>Risk</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {repeat.map((r, i) => {
                                            const risk = r.failure_count >= 5 ? ['Critical','#ff5e5e','rgba(255,94,94,0.12)'] :
                                                         r.failure_count >= 3 ? ['High','#fb923c','rgba(251,146,60,0.12)'] :
                                                         ['Moderate','#ffd93d','rgba(255,217,61,0.12)'];
                                            return (
                                                <tr key={i} className="bd-row" style={{ cursor:'pointer' }}
                                                    onClick={() => openDrill(r.asset_tag, r.equipment_name)}>
                                                    <td style={{ fontWeight:600 }}>{r.equipment_name || '—'}</td>
                                                    <td><span className="tag">{r.asset_tag || '—'}</span></td>
                                                    <td style={{ fontWeight:700, color:'#ff5e5e' }}>{r.failure_count}</td>
                                                    <td style={{ color:'var(--text-secondary)' }}>
                                                        {r.avg_days_between != null ? `${r.avg_days_between} days` : '—'}
                                                    </td>
                                                    <td style={{ fontSize:'0.83rem', color:'var(--text-secondary)' }}>{fmtDate(r.last_failure)}</td>
                                                    <td>
                                                        <span style={{ display:'inline-flex', alignItems:'center', padding:'2px 10px', borderRadius:99, fontSize:'0.7rem', fontWeight:700, color:risk[1], background:risk[2] }}>
                                                            {risk[0]}
                                                        </span>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>

                </div>
            )}

            {/* ── Drill-Down Side Panel ── */}
            {drillTag !== null && (
                <>
                    <div onClick={closeDrill} style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.18)', zIndex:100, backdropFilter:'blur(2px)' }} />
                    <div className="glass-card fade-in" style={{
                        position:'fixed', top:0, right:0, bottom:0,
                        width:460, maxWidth:'95vw', zIndex:101,
                        borderRadius:'16px 0 0 16px', overflowY:'auto',
                        display:'flex', flexDirection:'column', padding:'28px 24px',
                    }}>
                        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:20 }}>
                            <div>
                                <span className="tag">{drillTag}</span>
                                <h2 style={{ fontSize:'1.1rem', fontWeight:700, marginTop:6, color:'var(--text-primary)' }}>{drillName || 'Unknown Equipment'}</h2>
                                <p style={{ fontSize:'0.78rem', color:'var(--text-secondary)', margin:0 }}>Breakdown History</p>
                            </div>
                            <button onClick={closeDrill} className="btn btn-ghost" style={{ padding:'6px 12px', minWidth:0, borderRadius:8 }}>✕</button>
                        </div>
                        {drillLoading ? (
                            <div className="skeleton" style={{ height:80, borderRadius:8 }} />
                        ) : !drillData.length ? (
                            <EmptyState message="No records found for this equipment in the selected period." />
                        ) : (
                            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                                {drillData.map((b, i) => (
                                    <div key={b.id || i} className="glass-card" style={{ padding:'12px 14px' }}>
                                        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6 }}>
                                            <SeverityBadge v={b.severity_level} />
                                            <span style={{ fontSize:'0.72rem', color:'var(--text-secondary)' }}>{fmtDate(b.reported_at)}</span>
                                        </div>
                                        <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:4 }}>
                                            {b.failure_type && <span className="category-tag">{b.failure_type}</span>}
                                            <span className="status-badge" style={{
                                                background: b.status === 'Closed' ? 'rgba(74,222,128,0.12)' : b.status === 'Open' ? 'rgba(255,94,94,0.12)' : 'rgba(251,146,60,0.12)',
                                                color: b.status === 'Closed' ? '#4ade80' : b.status === 'Open' ? '#ff5e5e' : '#fb923c',
                                            }}>{b.status}</span>
                                            {b.mttr_hours > 0 && <span style={{ fontSize:'0.72rem', color:'var(--text-secondary)', alignSelf:'center' }}>MTTR: {b.mttr_hours}h</span>}
                                        </div>
                                        {b.description && (
                                            <p className="ellipsis" style={{ fontSize:'0.82rem', color:'var(--text-secondary)', margin:0 }}>{b.description}</p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
};

export default HistoricalAnalyticsPage;
