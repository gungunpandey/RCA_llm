import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import useDashboard from '../hooks/useDashboard';
import KPICard from '../components/KPICard';
import MTTRChart from '../components/MTTRChart';
import FailuresPieChart from '../components/FailuresPieChart';
import BreakdownTable from '../components/BreakdownTable';
import TopEquipment from '../components/TopEquipment';
import RCAList from '../components/RCAList';
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

// ── Insight line helper ────────────────────────────────────────
const buildInsight = (data) => {
    const topCategory = data?.failuresByAsset?.[0];
    const mttrLatest = data?.summary?.mttrTrend?.slice(-1)[0]?.avgMttr ?? null;
    const mttrPrev   = data?.summary?.mttrTrend?.slice(-2)[0]?.avgMttr ?? null;

    const parts = [];
    if (topCategory) {
        const total = (data.failuresByAsset || []).reduce((s, d) => s + d.count, 0);
        const pct = total > 0 ? Math.round((topCategory.count / total) * 100) : 0;
        parts.push(`${topCategory.category} accounts for ${pct}% of all failures`);
    }
    if (mttrLatest != null && mttrPrev != null) {
        const diff = (Number(mttrLatest) - Number(mttrPrev)).toFixed(1);
        const dir  = diff > 0 ? '↑' : '↓';
        parts.push(`MTTR ${dir} ${Math.abs(diff)}h vs last month`);
    } else if (mttrLatest != null) {
        parts.push(`Current MTTR is ${mttrLatest}h`);
    }
    return parts.length ? `💡 ${parts.join(' · ')}` : null;
};

// ── Dashboard Page ─────────────────────────────────────────────
const DashboardPage = () => {
    const { user } = useAuth();
    const { data, loading, error } = useDashboard();

    // Filter state (frontend-only — displayed for UX, no refetch wired yet)
    const [filters, setFilters] = useState({ plant: '', equipType: '', dateRange: '' });

    // ── MTTR time-range filter ────────────────────────────────────
    const [mttrRange, setMttrRange] = useState('12'); // '3' | '6' | '12' | specific month string

    const allMttrData = data?.summary?.mttrTrend ?? [];
    const specificMonths = allMttrData.map(d => d.month); // e.g. ['Aug 2025', ...]

    const [weeklyMttrData, setWeeklyMttrData] = useState(null);

    // Fetch week-grouped data from the backend when a specific month is chosen
    useEffect(() => {
        if (['3', '6', '12'].includes(mttrRange)) {
            setWeeklyMttrData(null);
            return;
        }
        fetch(`/api/dashboard/mttr-weekly?month=${encodeURIComponent(mttrRange)}`, {
            credentials: 'include',
        })
            .then(r => r.json())
            .then(rows => setWeeklyMttrData(Array.isArray(rows) ? rows : null))
            .catch(() => setWeeklyMttrData([]));
    }, [mttrRange]);

    const filteredMttrData = (() => {
        if (mttrRange === '3')  return allMttrData.slice(-3);
        if (mttrRange === '6')  return allMttrData.slice(-6);
        if (mttrRange === '12') return allMttrData.slice(-12);
        // specific month — use backend weekly data, fall back to empty while loading
        return weeklyMttrData ?? [];
    })();

    const mttrTitle = (() => {
        if (mttrRange === '3')  return 'MTTR Trend — Last 3 Months';
        if (mttrRange === '6')  return 'MTTR Trend — Last 6 Months';
        if (mttrRange === '12') return 'MTTR Trend — Last 12 Months';
        return `MTTR Trend — ${mttrRange}`;
    })();

    if (!user) return null;

    const mttrLatest = data?.summary?.mttrTrend?.slice(-1)[0]?.avgMttr ?? null;
    const insightLine = !loading && data ? buildInsight(data) : null;

    // 4th KPI: total breakdowns in the fetched recent set
    const totalFailures = data?.breakdowns?.length ?? null;

    return (
        <div className="db-page">
            {/* Ambient blobs */}
            <div className="db-blob db-blob-1" />
            <div className="db-blob db-blob-2" />

            {/* ── Top nav bar ─────────────────────────────────── */}
            <NavBar activePage="dashboard" />

            {/* ── Page title ───────────────────────────────────── */}
            <div style={{ textAlign: 'center', padding: '0 0 4px', marginTop: '-16px', position: 'relative', zIndex: 1 }}>
                <h1 style={{ margin: 0, fontSize: '1.85rem', fontWeight: 800, color: '#1a1a1a', letterSpacing: '-0.01em' }}>
                    Maintenance Dashboard
                </h1>
            </div>

            {/* ── Main content ─────────────────────────────────── */}
            <main className="db-main">

                {error && (
                    <div className="alert-error fade-in" style={{ padding: '14px 20px', borderRadius: 'var(--radius)' }}>
                        ⚠️ {error} — Check that the backend server is running.
                    </div>
                )}

                {/* ── Filter Bar ────────────────────────────────── */}
                <section className="db-filter-bar glass-card">
                    <span className="db-filter-label">🔽 Filters</span>

                    <select
                        className="db-filter-select"
                        value={filters.plant}
                        onChange={e => setFilters(f => ({ ...f, plant: e.target.value }))}
                    >
                        <option value="">All Plants</option>
                        <option value="BNFC">BNFC</option>
                        <option value="CPP1">CPP1</option>
                        <option value="CPP2">CPP2</option>
                    </select>

                    <select
                        className="db-filter-select"
                        value={filters.equipType}
                        onChange={e => setFilters(f => ({ ...f, equipType: e.target.value }))}
                    >
                        <option value="">All Equipment Types</option>
                        <option value="Pump">Pump</option>
                        <option value="Boiler">Boiler</option>
                        <option value="Compressor">Compressor</option>
                        <option value="Motor">Motor</option>
                        <option value="Conveyor">Conveyor</option>
                    </select>

                    <select
                        className="db-filter-select"
                        value={filters.dateRange}
                        onChange={e => setFilters(f => ({ ...f, dateRange: e.target.value }))}
                    >
                        <option value="">All Time</option>
                        <option value="7d">Last 7 Days</option>
                        <option value="30d">Last 30 Days</option>
                        <option value="90d">Last 90 Days</option>
                        <option value="1y">Last 12 Months</option>
                    </select>
                </section>

                {/* ── KPI Row ───────────────────────────────────── */}
                <section>
                    <SectionTitle>Key Performance Indicators</SectionTitle>
                    {loading ? <Skeleton /> : (
                        <div className="kpi-row kpi-row-4">
                            <KPICard
                                icon="🔧"
                                label="Open Breakdowns"
                                value={data?.summary?.openBreakdowns ?? '—'}
                                sub="Active & In-Progress"
                                accentColor="#ff6b6b"
                                trendLabel="active now"
                                trendUp={false}
                            />
                            <KPICard
                                icon="⚠️"
                                label="CAPA Overdue"
                                value={data?.summary?.capaOverdue ?? '—'}
                                sub="Past due date"
                                accentColor="#ffd93d"
                                trendLabel="need attention"
                                trendUp={false}
                            />
                            <KPICard
                                icon="⏱️"
                                label="Avg MTTR (Latest)"
                                value={mttrLatest != null ? `${mttrLatest}h` : '—'}
                                sub="Mean Time To Repair"
                                accentColor="#7c6bff"
                                trendLabel="this month"
                                trendUp={mttrLatest != null && Number(mttrLatest) < 5}
                            />
                            <KPICard
                                icon="📊"
                                label="Total Failures"
                                value={totalFailures ?? '—'}
                                sub="Recent breakdowns logged"
                                accentColor="#33B1B0"
                                trendLabel="recent records"
                                trendUp={false}
                            />
                        </div>
                    )}
                </section>

                {/* ── Insight Summary Line ───────────────────────── */}
                {insightLine && (
                    <div className="db-insight fade-in">
                        {insightLine}
                    </div>
                )}

                {/* ── Middle row: Top Equipment + Pie Chart ─────── */}
                <div className="db-mid-row">
                    <section className="glass-card db-panel">
                        <SectionTitle>Top 5 Failing Equipment</SectionTitle>
                        {loading ? <Skeleton /> : <TopEquipment data={data?.topEquipment} />}
                    </section>

                    <section className="glass-card db-panel">
                        <SectionTitle>Failures by Asset Category</SectionTitle>
                        {loading ? <Skeleton /> : <FailuresPieChart data={data?.failuresByAsset} />}
                    </section>
                </div>

                {/* ── MTTR Trend Chart ──────────────────────────── */}
                <section className="glass-card db-panel">
                    {/* Card header: title left, filter right */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                        <SectionTitle>{mttrTitle}</SectionTitle>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <select
                                className="db-filter-select"
                                style={{ fontSize: '0.78rem', padding: '4px 8px' }}
                                value={['3','6','12'].includes(mttrRange) ? mttrRange : 'month'}
                                onChange={e => {
                                    if (e.target.value !== 'month') setMttrRange(e.target.value);
                                }}
                            >
                                <option value="3">Last 3 Months</option>
                                <option value="6">Last 6 Months</option>
                                <option value="12">Last 12 Months</option>
                                <option value="month" disabled={['3','6','12'].includes(mttrRange)}>Specific Month ▾</option>
                            </select>
                            {!['3','6','12'].includes(mttrRange) || specificMonths.length > 0 ? (
                                <select
                                    className="db-filter-select"
                                    style={{ fontSize: '0.78rem', padding: '4px 8px' }}
                                    value={!['3','6','12'].includes(mttrRange) ? mttrRange : ''}
                                    onChange={e => { if (e.target.value) setMttrRange(e.target.value); }}
                                >
                                    <option value="">— Pick month —</option>
                                    {specificMonths.map(m => (
                                        <option key={m} value={m}>{m}</option>
                                    ))}
                                </select>
                            ) : null}
                        </div>
                    </div>
                    {loading ? <Skeleton /> : <MTTRChart data={filteredMttrData} />}
                </section>

                {/* ── Recent Breakdowns Table ───────────────────── */}
                <section className="glass-card db-panel">
                    <SectionTitle>Recent Breakdowns</SectionTitle>
                    {loading ? <Skeleton /> : <BreakdownTable data={data?.breakdowns} />}
                </section>

                {/* ── RCA Reports ───────────────────────────────── */}
                <section>
                    <SectionTitle>Recent RCA Reports</SectionTitle>
                    {loading ? <Skeleton /> : <RCAList data={data?.rcaReports} />}
                </section>

            </main>
        </div>
    );
};

export default DashboardPage;
