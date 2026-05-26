import React, { useState, useEffect, useMemo } from 'react';
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
const SectionTitle = ({ children }) => (
    <h2 className="section-title">{children}</h2>
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
    const { data, loading, error } = useDashboard();

    // Top-level filters (cosmetic)
    const [filters, setFilters] = useState({ plant: '', equipType: '', dateRange: '' });

    // ── BD Hours time-range filter ─────────────────────────────
    const [bdRange, setBdRange] = useState('12');
    const allMttrData    = data?.summary?.mttrTrend ?? [];
    const specificMonths = allMttrData.map(d => d.month);
    const [weeklyData, setWeeklyData] = useState(null);

    useEffect(() => {
        if (['3', '6', '12'].includes(bdRange)) { setWeeklyData(null); return; }
        fetch(`/api/dashboard/mttr-weekly?month=${encodeURIComponent(bdRange)}`, { credentials: 'include' })
            .then(r => r.json())
            .then(rows => setWeeklyData(Array.isArray(rows) ? rows : null))
            .catch(() => setWeeklyData([]));
    }, [bdRange]);

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

    if (!user) return null;

    const mttrLatest   = allMttrData.slice(-1)[0]?.avgMttr ?? null;
    const totalFailures = data?.breakdowns?.length ?? null;
    const insights     = !loading && data ? buildInsights(data) : [];

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
                    <select className="db-filter-select" value={filters.plant}
                        onChange={e => setFilters(f => ({ ...f, plant: e.target.value }))}>
                        <option value="">All Plants</option>
                        <option value="BNFC">BNFC</option>
                        <option value="CPP1">CPP1</option>
                        <option value="CPP2">CPP2</option>
                    </select>
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
                </section>

                {/* ── KPI Row ── */}
                <section>
                    <SectionTitle>Key Performance Indicators</SectionTitle>
                    {loading ? <Skeleton /> : (
                        <div className="kpi-row kpi-row-4">
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
                                icon="⏱️" label="Avg BD Hours"
                                value={mttrLatest != null ? `${mttrLatest}h` : '—'}
                                sub="Mean Breakdown Duration"
                                accentColor="#f97316" trendLabel="this month"
                                trendUp={mttrLatest != null && Number(mttrLatest) < 5}
                            />
                            <KPICard
                                icon="📊" label="Total Failures"
                                value={totalFailures ?? '—'}
                                sub="Recent breakdowns logged"
                                accentColor="#33B1B0" trendLabel="recent records" trendUp={false}
                            />
                        </div>
                    )}
                </section>

                {/* ── Expanded AI Insights ── */}
                {insights.length > 0 && (
                    <section className="glass-card db-panel fade-in" style={{ padding: '20px 24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                            <span style={{ fontSize: '1.1rem' }}>🤖</span>
                            <SectionTitle>AI Insights</SectionTitle>
                        </div>
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
                    </section>
                )}

                {/* ── Middle row: Top Equipment + Pie Chart ── */}
                <div className="db-mid-row">
                    <section className="glass-card db-panel">
                        <SectionTitle>Top 5 Failing Equipment</SectionTitle>
                        {loading ? <Skeleton /> : <TopEquipment data={data?.topEquipment} />}
                    </section>

                    <section className="glass-card db-panel" style={{ position: 'relative' }}>
                        <SectionTitle>Failures by Plant</SectionTitle>
                        {loading ? <Skeleton /> : <FailuresPieChart data={data?.failuresByAsset} />}
                    </section>
                </div>

                {/* ── BD Hours Trend Chart ── */}
                <section className="glass-card db-panel">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                        <SectionTitle>{bdTitle}</SectionTitle>
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

                {/* ── Recent Breakdowns Table (top 5, expandable) ── */}
                <section className="glass-card db-panel">
                    <SectionTitle>Recent Breakdowns</SectionTitle>
                    {loading ? <Skeleton /> : <BreakdownTable data={data?.breakdowns} />}
                </section>

                {/* RCA Reports section REMOVED */}

            </main>
        </div>
    );
};

export default DashboardPage;
