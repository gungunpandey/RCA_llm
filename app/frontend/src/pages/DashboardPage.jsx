import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import useDashboard from '../hooks/useDashboard';
import KPICard from '../components/KPICard';
import BDHoursChart from '../components/MTTRChart';
import FailuresPieChart from '../components/FailuresPieChart';
import BreakdownTable from '../components/BreakdownTable';
import TopEquipment from '../components/TopEquipment';
import NavBar from '../components/NavBar';

// ── Loading skeleton ──────────────────────────────────────────
const Skeleton = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {[1, 2, 3].map(i => (
            <div key={i} className="skeleton" style={{ height: 80, borderRadius: 'var(--radius)' }} />
        ))}
    </div>
);

// ── Section header ─────────────────────────────────────────────
const SectionTitle = ({ children, style }) => (
    <h2 className="section-title" style={style}>{children}</h2>
);

// ── Expanded AI Insights builder ───────────────────────────────
const buildInsights = (data) => {
    const insights = [];

    // Top failing plant
    const topCat = data?.failuresByAsset?.[0];
    if (topCat) {
        const total = (data.failuresByAsset || []).reduce((s, d) => s + d.count, 0);
        const pct = total > 0 ? Math.round((topCat.count / total) * 100) : 0;
        insights.push({
            icon: '🏭',
            text: `<strong>${topCat.category}</strong> accounts for <strong>${pct}%</strong> of all failures — highest among all plants.`,
            type: 'warning',
        });
    }

    // MTTR / BD Hours trend
    const mttrTrend = data?.summary?.mttrTrend ?? [];
    const mttrLatest = mttrTrend.slice(-1)[0]?.avgMttr ?? null;
    const mttrPrev   = mttrTrend.slice(-2)[0]?.avgMttr ?? null;
    if (mttrLatest != null && mttrPrev != null) {
        const diff = (Number(mttrLatest) - Number(mttrPrev)).toFixed(1);
        const dir  = diff > 0 ? '↑' : '↓';
        const color = diff > 0 ? 'danger' : 'success';
        insights.push({
            icon: diff > 0 ? '⚠️' : '✅',
            text: `BD Hours ${dir} <strong>${Math.abs(diff)} h</strong> vs last month — currently at <strong>${mttrLatest} h</strong>.`,
            type: color,
        });
    } else if (mttrLatest != null) {
        insights.push({ icon: '⏱️', text: `Current average BD Hours: <strong>${mttrLatest} h</strong>.`, type: 'info' });
    }

    // CAPA overdue
    const capaOverdue = data?.summary?.capaOverdue ?? 0;
    if (capaOverdue > 0) {
        insights.push({
            icon: '🔴',
            text: `<strong>${capaOverdue} CAPA action${capaOverdue > 1 ? 's' : ''}</strong> are overdue — immediate follow-up required.`,
            type: 'danger',
        });
    } else if (capaOverdue === 0) {
        insights.push({ icon: '✅', text: 'All CAPA actions are within due date — no overdue items.', type: 'success' });
    }

    // Open breakdowns
    const open = data?.summary?.openBreakdowns ?? 0;
    if (open > 0) {
        insights.push({
            icon: '🔧',
            text: `<strong>${open}</strong> breakdown${open > 1 ? 's' : ''} currently open or in-progress — check equipment status.`,
            type: open > 5 ? 'danger' : 'warning',
        });
    }

    // Top failing equipment
    const topEq = data?.topEquipment?.[0];
    if (topEq) {
        insights.push({
            icon: '📍',
            text: `Top failing equipment: <strong>${topEq.equipment_name}</strong> (${topEq.breakdown_count} failures) — consider preventive maintenance.`,
            type: 'info',
        });
    }

    return insights;
};

const INSIGHT_STYLES = {
    danger:  { bg: 'rgba(255,94,94,0.08)',  border: 'rgba(255,94,94,0.22)',  dot: '#ff5e5e' },
    warning: { bg: 'rgba(255,179,0,0.08)',  border: 'rgba(255,179,0,0.22)',  dot: '#ffd93d' },
    success: { bg: 'rgba(74,222,128,0.08)', border: 'rgba(74,222,128,0.22)', dot: '#4ade80' },
    info:    { bg: 'rgba(51,177,176,0.08)', border: 'rgba(51,177,176,0.22)', dot: '#33B1B0' },
};

// ── Dashboard Page ─────────────────────────────────────────────
const DashboardPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();
    
    // Top-level filters
    const [filters, setFilters] = useState(() => ({
        plant: (user && user.role !== 'Admin') ? user.role : '',
        equipType: '',
        dateRange: ''
    }));
    const { data, loading, error } = useDashboard(filters);

    // Sync plant filter if user loads asynchronously
    useEffect(() => {
        if (user && user.role !== 'Admin') {
            setFilters(f => ({ ...f, plant: user.role }));
        }
    }, [user]);

    // AI Insights state
    const [insights, setInsights] = useState([]);
    const [insightsLoading, setInsightsLoading] = useState(false);
    const [insightsError, setInsightsError] = useState(null);
    const [insightsSource, setInsightsSource] = useState(null);   // 'ai' | 'rule_based'
    const [execSummary, setExecSummary] = useState(null);          // executive summary rollup
    const [showExec, setShowExec] = useState(false);               // executive summary dropdown open?

    useEffect(() => {
        if (!loading && data) {
            setInsights(buildInsights(data));
        }
    }, [data, loading]);

    // ── BD Hours time-range filter ─────────────────────────────
    const [bdRange, setBdRange] = useState('12');
    const allMttrData    = data?.summary?.mttrTrend ?? [];
    const specificMonths = allMttrData.map(d => d.month);
    const [weeklyData, setWeeklyData] = useState(null);

    useEffect(() => {
        if (['3', '6', '12'].includes(bdRange)) { setWeeklyData(null); return; }
        const params = new URLSearchParams({ month: bdRange });
        if (filters.plant) params.append('plant', filters.plant);
        if (filters.equipType) params.append('equip_type', filters.equipType);
        fetch(`/api/dashboard/mttr-weekly?${params.toString()}`, { credentials: 'include' })
            .then(r => r.json())
            .then(rows => setWeeklyData(Array.isArray(rows) ? rows : null))
            .catch(() => setWeeklyData([]));
    }, [bdRange, filters.plant, filters.equipType]);

    const refreshAIInsights = async () => {
        setInsightsLoading(true);
        setInsightsError(null);
        try {
            const params = new URLSearchParams();
            if (filters.plant) params.append('plant', filters.plant);
            if (filters.equipType) params.append('equip_type', filters.equipType);
            if (filters.dateRange) params.append('date_range', filters.dateRange);
            
            const resp = await fetch(`/api/dashboard-insights?${params.toString()}`, {
                method: 'POST',
                credentials: 'include'
            });
            if (!resp.ok) {
                throw new Error(`Failed to generate ProdAI insights: ${resp.statusText}`);
            }
            const result = await resp.json();
            if (result.status === 'success' && Array.isArray(result.insights)) {
                setInsights(result.insights);
                setInsightsSource(result.source || null);
                setExecSummary(result.executive_summary || null);
                setShowExec(!!result.executive_summary);   // reveal the summary once generated
            } else {
                throw new Error("Invalid insights response format");
            }
        } catch (err) {
            console.error(err);
            setInsightsError(err.message || "Failed to load dynamic ProdAI insights");
        } finally {
            setInsightsLoading(false);
        }
    };

    const filteredBdData = (() => {
        if (bdRange === '3')  return allMttrData.slice(-3);
        if (bdRange === '6')  return allMttrData.slice(-6);
        if (bdRange === '12') return allMttrData.slice(-12);
        return weeklyData ?? [];
    })();

    const bdTitle = (() => {
        if (bdRange === '3')  return 'BD Hours Trend — Last 3 Months';
        if (bdRange === '6')  return 'BD Hours Trend — Last 6 Months';
        if (bdRange === '12') return 'BD Hours Trend — Last 12 Months';
        return `BD Hours Trend — ${bdRange}`;
    })();

    const equipmentFailuresData = useMemo(() => {
        if (!data?.topEquipment) return [];
        return data.topEquipment.map(item => ({
            category: item.equipment_name,
            count: item.breakdown_count
        }));
    }, [data?.topEquipment]);

    if (!user) return null;

    const mttrLatest   = allMttrData.slice(-1)[0]?.avgMttr ?? null;
    const totalFailures = data?.breakdowns?.length ?? null;

    return (
        <div className="db-page">
            <div className="db-blob db-blob-1" />
            <div className="db-blob db-blob-2" />

            <NavBar activePage="dashboard" />

            {/* ── Page title ── */}
            <div style={{ textAlign: 'center', padding: '0 0 4px', marginTop: '-16px', position: 'relative', zIndex: 1 }}>
                <h1 style={{ margin: 0, fontSize: '1.85rem', fontWeight: 800, color: '#1a1a1a', letterSpacing: '-0.01em' }}>
                    Maintenance Dashboard
                </h1>
            </div>

            <main className="db-main">

                {error && (
                    <div className="alert-error fade-in" style={{ padding: '14px 20px', borderRadius: 'var(--radius)' }}>
                        ⚠️ {error} — Check that the backend server is running.
                    </div>
                )}

                {/* ── Filter Bar ── */}
                <section className="db-filter-bar glass-card">
                    <span className="db-filter-label">🔽 Filters</span>
                    {user.role === 'Admin' ? (
                        <select className="db-filter-select" value={filters.plant}
                            onChange={e => setFilters(f => ({ ...f, plant: e.target.value }))}>
                            <option value="">All Plants</option>
                            <option value="BNFC">BNFC</option>
                            <option value="Pellet 1">Pellet 1</option>
                            <option value="Pellet 2">Pellet 2</option>
                            <option value="SMS 1">SMS 1</option>
                            <option value="SMS 2">SMS 2</option>
                            <option value="DRI 1">DRI 1</option>
                            <option value="DRI 2">DRI 2</option>
                            <option value="CPP">CPP</option>
                            <option value="CPP 2">CPP 2</option>
                            <option value="PGP">PGP</option>
                            <option value="Fire Service">Fire Service</option>
                        </select>
                    ) : (
                        <div style={{
                            padding: '6px 14px',
                            background: 'rgba(51, 177, 176, 0.08)',
                            border: '1.5px solid rgba(51, 177, 176, 0.25)',
                            borderRadius: 10,
                            fontSize: '0.82rem',
                            fontWeight: 700,
                            color: '#33B1B0',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            height: 38,
                            boxSizing: 'border-box'
                        }}>
                            🏭 {user.role}
                        </div>
                    )}
                    <select className="db-filter-select" value={filters.equipType}
                        onChange={e => setFilters(f => ({ ...f, equipType: e.target.value }))}>
                        <option value="">All Equipment Types</option>
                        <option value="Pump">Pump</option>
                        <option value="Boiler">Boiler</option>
                        <option value="Compressor">Compressor</option>
                        <option value="Motor">Motor</option>
                        <option value="Conveyor">Conveyor</option>
                    </select>
                    <select className="db-filter-select" value={filters.dateRange}
                        onChange={e => setFilters(f => ({ ...f, dateRange: e.target.value }))}>
                        <option value="">All Time</option>
                        <option value="7d">Last 7 Days</option>
                        <option value="30d">Last 30 Days</option>
                        <option value="90d">Last 90 Days</option>
                        <option value="1y">Last 12 Months</option>
                    </select>
                    {filters.plant === 'BNFC' && (
                        <button
                            type="button"
                            className="btn"
                            style={{
                                marginLeft: 'auto',
                                padding: '6px 14px',
                                fontSize: '0.82rem',
                                background: 'rgba(51, 177, 176, 0.15)',
                                color: '#33B1B0',
                                border: '1px solid rgba(51, 177, 176, 0.35)',
                                fontWeight: 700,
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 6,
                                borderRadius: 8,
                                cursor: 'pointer',
                                height: 36,
                                alignSelf: 'center',
                                transition: 'all 0.2s ease-in-out'
                            }}
                            onClick={() => navigate('/beneficiation-pfd')}
                            onMouseEnter={e => {
                                e.currentTarget.style.background = '#33B1B0';
                                e.currentTarget.style.color = '#0B0F19';
                            }}
                            onMouseLeave={e => {
                                e.currentTarget.style.background = 'rgba(51, 177, 176, 0.15)';
                                e.currentTarget.style.color = '#33B1B0';
                            }}
                        >
                            🖥️ View Mimic PFD
                        </button>
                    )}
                </section>

                {/* ── KPI Row ── */}
                <section>
                    <SectionTitle>Key Performance Indicators</SectionTitle>
                    {loading ? <Skeleton /> : (
                        <div className="kpi-row kpi-row-4">
                            <KPICard
                                icon="📊" label="All Breakdowns"
                                value={data?.summary?.totalBreakdowns ?? '—'}
                                sub="During the time period"
                                accentColor="#33B1B0" trendLabel="total logged" trendUp={false}
                            />
                            <KPICard
                                icon="🔧" label="Open Breakdowns"
                                value={data?.summary?.openBreakdowns ?? '—'}
                                sub="Active & In-Progress"
                                accentColor="#ff6b6b" trendLabel="active now" trendUp={false}
                            />
                            <KPICard
                                icon="⚠️" label="CAPA Overdue"
                                value={data?.summary?.capaOverdue ?? '—'}
                                sub="Past due date"
                                accentColor="#ffd93d" trendLabel="need attention" trendUp={false}
                            />
                            <KPICard
                                icon="⏱️" label="Avg. BD Hours"
                                value={data?.summary?.avgBdHoursClosed != null ? `${data.summary.avgBdHoursClosed}h` : '—'}
                                sub="For closed breakdowns"
                                accentColor="#f97316" trendLabel="closed BDs average"
                                trendUp={data?.summary?.avgBdHoursClosed != null && Number(data.summary.avgBdHoursClosed) < 5}
                            />
                        </div>
                    )}
                </section>

                {/* ── Expanded AI Insights ── */}
                {(insights.length > 0 || insightsLoading || insightsError) && (
                    <section className="glass-card db-panel fade-in" style={{ padding: '20px 24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <span style={{ fontSize: '1.1rem', display: 'inline-flex', alignItems: 'center' }}>🤖</span>
                                <SectionTitle style={{ margin: 0 }}>ProdAI Insights</SectionTitle>
                                {insightsSource && (
                                    <span
                                        title={insightsSource === 'ai'
                                            ? 'AI-narrated from verified plant data'
                                            : 'Computed directly from plant data (rule-based)'}
                                        style={{
                                            fontSize: '0.62rem', fontWeight: 700, letterSpacing: '0.03em',
                                            textTransform: 'uppercase', padding: '2px 8px', borderRadius: 999,
                                            border: `1px solid ${insightsSource === 'ai' ? 'rgba(51,177,176,0.4)' : 'rgba(148,163,184,0.4)'}`,
                                            color: insightsSource === 'ai' ? '#2b8c8b' : '#64748b',
                                            background: insightsSource === 'ai' ? 'rgba(51,177,176,0.10)' : 'rgba(148,163,184,0.10)',
                                        }}
                                    >
                                        {insightsSource === 'ai' ? '🤖 AI' : '📊 Computed'}
                                    </span>
                                )}
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                {execSummary && (
                                    <button
                                        onClick={() => setShowExec(v => !v)}
                                        className="btn btn-ghost"
                                        style={{
                                            padding: '6px 12px', fontSize: '0.8rem', display: 'flex',
                                            alignItems: 'center', gap: 6, borderRadius: '8px',
                                            cursor: 'pointer', fontWeight: 600, transition: 'var(--transition)',
                                        }}
                                    >
                                        📋 Executive Summary
                                        <span style={{ transform: showExec ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▾</span>
                                    </button>
                                )}
                                <button
                                    onClick={refreshAIInsights}
                                    disabled={insightsLoading}
                                    className="btn btn-ghost"
                                    style={{
                                        padding: '6px 12px', fontSize: '0.8rem', display: 'flex',
                                        alignItems: 'center', gap: 6, borderRadius: '8px',
                                        cursor: 'pointer', fontWeight: 600, transition: 'var(--transition)',
                                    }}
                                >
                                    {insightsLoading ? (
                                        <>
                                            <span className="spinner" style={{ width: '12px', height: '12px', borderWidth: '1.5px', borderTopColor: '#33B1B0', borderLeftColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
                                            Generating...
                                        </>
                                    ) : (
                                        <>🔄 Refresh with ProdAI</>
                                    )}
                                </button>
                            </div>
                        </div>
                        
                        {showExec && execSummary && Array.isArray(execSummary.metrics) && execSummary.metrics.length > 0 && (
                            <div style={{
                                marginBottom: 14, borderRadius: 14, overflow: 'hidden',
                                border: '1px solid rgba(51,177,176,0.25)',
                                boxShadow: '0 6px 20px rgba(51,177,176,0.10)',
                                animation: 'fadeInUp 0.35s ease both',
                            }}>
                                {/* Header band */}
                                <div style={{
                                    padding: '14px 18px',
                                    background: 'linear-gradient(135deg, rgba(51,177,176,0.16), rgba(51,177,176,0.06))',
                                    borderBottom: '1px solid rgba(51,177,176,0.18)',
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                        <span style={{ fontSize: '1.05rem' }}>📋</span>
                                        <strong style={{ fontSize: '0.98rem', color: 'var(--text-primary)' }}>
                                            {execSummary.headline}
                                        </strong>
                                        {/* Filter context chips */}
                                        {[
                                            filters.plant || 'All Plants',
                                            filters.equipType || 'All Equipment',
                                            ({ '': 'All Time', '7d': 'Last 7 Days', '30d': 'Last 30 Days', '90d': 'Last 90 Days', '180d': 'Last 180 Days', '1y': 'Last 1 Year' }[filters.dateRange] || execSummary.period),
                                        ].map((chip, i) => (
                                            <span key={i} style={{
                                                fontSize: '0.68rem', fontWeight: 600, padding: '2px 9px', borderRadius: 999,
                                                background: 'rgba(255,255,255,0.55)', border: '1px solid rgba(51,177,176,0.3)',
                                                color: '#2b8c8b',
                                            }}>{chip}</span>
                                        ))}
                                    </div>
                                </div>
                                {/* Metric tiles */}
                                <div style={{ padding: '16px 18px', background: 'rgba(255,255,255,0.4)' }}>
                                    <div style={{
                                        display: 'grid', gap: 10,
                                        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                                        marginBottom: execSummary.recommended_focus?.length ? 16 : 0,
                                    }}>
                                        {execSummary.metrics.map((m, i) => (
                                            <div key={i} style={{
                                                padding: '12px 14px', borderRadius: 11,
                                                background: '#fff',
                                                border: `1px solid ${m.good === false ? 'rgba(220,38,38,0.22)' : 'rgba(22,163,74,0.20)'}`,
                                                borderLeft: `3px solid ${m.good === false ? '#dc2626' : '#16a34a'}`,
                                            }}>
                                                <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.02em' }}>
                                                    {m.label}
                                                </div>
                                                <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
                                                    <span style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1 }}>
                                                        {m.value}
                                                    </span>
                                                    {m.trend && (
                                                        <span style={{ fontSize: '0.72rem', fontWeight: 700, color: m.good ? '#16a34a' : '#dc2626' }}>
                                                            {m.direction === 'up' ? '▲' : m.direction === 'down' ? '▼' : ''} {m.trend}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                    {execSummary.recommended_focus?.length > 0 && (
                                        <div style={{
                                            padding: '12px 14px', borderRadius: 11,
                                            background: 'rgba(51,177,176,0.07)', border: '1px solid rgba(51,177,176,0.18)',
                                        }}>
                                            <div style={{ fontSize: '0.7rem', fontWeight: 800, color: '#2b8c8b', marginBottom: 7, letterSpacing: '0.04em' }}>
                                                🎯 RECOMMENDED FOCUS
                                            </div>
                                            <ol style={{ margin: 0, paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 5 }}>
                                                {execSummary.recommended_focus.map((f, i) => (
                                                    <li key={i} style={{ fontSize: '0.82rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                                                        {f}
                                                    </li>
                                                ))}
                                            </ol>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {insightsError && (
                            <div className="alert-error" style={{ marginBottom: 10, padding: '8px 12px', borderRadius: '8px', fontSize: '0.8rem' }}>
                                ⚠️ {insightsError}
                            </div>
                        )}

                        {insightsLoading ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {[1, 2, 3].map(i => (
                                    <div key={i} className="skeleton" style={{ height: 44, borderRadius: '8px' }} />
                                ))}
                            </div>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {insights.map((ins, i) => {
                                    const s = INSIGHT_STYLES[ins.type] || INSIGHT_STYLES.info;
                                    return (
                                        <div key={i} style={{
                                            display: 'flex', alignItems: 'flex-start', gap: 12,
                                            padding: '10px 14px', borderRadius: 10,
                                            background: s.bg, border: `1px solid ${s.border}`,
                                            animation: `fadeInUp 0.4s ease ${i * 0.08}s both`,
                                        }}>
                                            <span style={{
                                                width: 8, height: 8, borderRadius: '50%',
                                                background: s.dot, flexShrink: 0, marginTop: 5,
                                            }} />
                                            <span style={{ fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.5 }}
                                                dangerouslySetInnerHTML={{ __html: `${ins.icon} ${ins.text}` }}
                                            />
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </section>
                )}

                {/* ── Recent Breakdowns Table (top 5, expandable) ── */}
                <section className="glass-card db-panel">
                    <SectionTitle>Recent Breakdowns</SectionTitle>
                    {loading ? <Skeleton /> : <BreakdownTable data={data?.breakdowns} />}
                </section>

                {/* ── Middle row: Top Equipment + Pie Chart ── */}
                <div className="db-mid-row">
                    <section className="glass-card db-panel">
                        <SectionTitle>Top 5 Failing Equipment</SectionTitle>
                        {loading ? <Skeleton /> : <TopEquipment data={data?.topEquipment} />}
                    </section>

                    <section className="glass-card db-panel" style={{ position: 'relative' }}>
                        <SectionTitle>{user.role === 'Admin' ? 'Failures by Plant' : 'Failures by Equipment'}</SectionTitle>
                        {loading ? <Skeleton /> : (
                            <FailuresPieChart data={user.role === 'Admin' ? data?.failuresByAsset : equipmentFailuresData} />
                        )}
                    </section>
                </div>

                {/* ── BD Hours Trend Chart ── */}
                <section className="glass-card db-panel">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                        <SectionTitle style={{ margin: 0 }}>{bdTitle}</SectionTitle>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <select
                                className="db-filter-select"
                                style={{ fontSize: '0.78rem', padding: '4px 8px' }}
                                value={['3','6','12'].includes(bdRange) ? bdRange : 'month'}
                                onChange={e => { if (e.target.value !== 'month') setBdRange(e.target.value); }}
                            >
                                <option value="3">Last 3 Months</option>
                                <option value="6">Last 6 Months</option>
                                <option value="12">Last 12 Months</option>
                                <option value="month" disabled={['3','6','12'].includes(bdRange)}>Specific Month ▾</option>
                            </select>
                            {(!['3','6','12'].includes(bdRange) || specificMonths.length > 0) ? (
                                <select
                                    className="db-filter-select"
                                    style={{ fontSize: '0.78rem', padding: '4px 8px' }}
                                    value={!['3','6','12'].includes(bdRange) ? bdRange : ''}
                                    onChange={e => { if (e.target.value) setBdRange(e.target.value); }}
                                >
                                    <option value="">— Pick month —</option>
                                    {specificMonths.map(m => <option key={m} value={m}>{m}</option>)}
                                </select>
                            ) : null}
                        </div>
                    </div>
                    {loading ? <Skeleton /> : <BDHoursChart data={filteredBdData} />}
                </section>

                {/* RCA Reports section REMOVED */}

            </main>
        </div>
    );
};

export default DashboardPage;
