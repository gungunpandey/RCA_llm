import React, { useState, useMemo } from 'react';

const STATUS_COLORS = {
    'Open':        { color: '#ff6b6b', bg: 'rgba(255,107,107,0.15)' },
    'In Progress': { color: '#ffd93d', bg: 'rgba(255,217,61,0.15)'  },
    'Resolved':    { color: '#4ade80', bg: 'rgba(74,222,128,0.15)'  },
    'Completed':   { color: '#4ade80', bg: 'rgba(74,222,128,0.15)'  },
    'Closed':      { color: '#4ade80', bg: 'rgba(74,222,128,0.15)'  },
};

const SEV_COLORS = {
    'Critical': '#ff5e5e',
    'High':     '#fb923c',
    'Medium':   '#ffd93d',
    'Low':      '#4ade80',
};

const formatDate = (dt) => {
    if (!dt) return '—';
    return new Date(dt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
};

const SORT_FIELDS = [
    { label: 'Date (Newest)', value: 'date_desc' },
    { label: 'Date (Oldest)', value: 'date_asc'  },
    { label: 'BD Hours ↑',    value: 'mttr_asc'  },
    { label: 'BD Hours ↓',    value: 'mttr_desc' },
    { label: 'Equipment A-Z', value: 'equip_asc' },
];

const STATUS_FILTERS = ['', 'Open', 'In Progress', 'Resolved', 'Closed'];

const BreakdownTable = ({ data, showAll = false }) => {
    const [search, setSearch]         = useState('');
    const [statusFilter, setStatus]   = useState('');
    const [sortMode, setSort]         = useState('date_desc');
    const [expanded, setExpanded]     = useState(false);

    const processed = useMemo(() => {
        if (!data) return [];
        let list = [...data];
        if (statusFilter) list = list.filter(r => r.status === statusFilter);
        if (search.trim()) {
            const q = search.toLowerCase();
            list = list.filter(r =>
                (r.equipment_name || '').toLowerCase().includes(q) ||
                (r.asset_tag || '').toLowerCase().includes(q) ||
                (r.description || '').toLowerCase().includes(q)
            );
        }
        switch (sortMode) {
            case 'date_desc': list.sort((a,b) => new Date(b.reported_at||0) - new Date(a.reported_at||0)); break;
            case 'date_asc':  list.sort((a,b) => new Date(a.reported_at||0) - new Date(b.reported_at||0)); break;
            case 'mttr_asc':  list.sort((a,b) => (Number(a.mttr_hours)||0) - (Number(b.mttr_hours)||0));  break;
            case 'mttr_desc': list.sort((a,b) => (Number(b.mttr_hours)||0) - (Number(a.mttr_hours)||0));  break;
            case 'equip_asc': list.sort((a,b) => (a.equipment_name||'').localeCompare(b.equipment_name||'')); break;
            default: break;
        }
        return list;
    }, [data, search, statusFilter, sortMode]);

    const displayed = (showAll || expanded) ? processed : processed.slice(0, 5);
    const hasMore   = processed.length > 5 && !showAll;

    if (!data || data.length === 0) {
        return <div className="chart-empty">No breakdown records found.</div>;
    }

    return (
        <div>
            {/* ── Filter / Sort bar ── */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
                <input
                    type="text"
                    className="form-input"
                    placeholder="🔍 Search equipment, tag, description…"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    style={{ maxWidth: 260, padding: '7px 12px', fontSize: '0.82rem' }}
                />
                <select
                    className="db-filter-select"
                    value={statusFilter}
                    onChange={e => setStatus(e.target.value)}
                    style={{ fontSize: '0.82rem' }}
                >
                    <option value="">All Statuses</option>
                    {STATUS_FILTERS.slice(1).map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <select
                    className="db-filter-select"
                    value={sortMode}
                    onChange={e => setSort(e.target.value)}
                    style={{ fontSize: '0.82rem' }}
                >
                    {SORT_FIELDS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
                </select>
                {(search || statusFilter) && (
                    <button
                        className="btn btn-ghost"
                        style={{ padding: '6px 12px', fontSize: '0.78rem', whiteSpace: 'nowrap' }}
                        onClick={() => { setSearch(''); setStatus(''); }}
                    >✕ Clear</button>
                )}
                <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                    {processed.length} records
                </span>
            </div>

            <div className="bd-table-wrapper" style={{ maxHeight: 'none' }}>
                <table className="bd-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Equipment</th>
                            <th>Tag</th>
                            <th>Severity</th>
                            <th>Description</th>
                            <th>Status</th>
                            <th>Reported</th>
                            <th>BD Hours</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {displayed.map((row, i) => {
                            const sc  = STATUS_COLORS[row.status] ?? { color: '#aaa', bg: 'rgba(170,170,170,0.12)' };
                            const sev = SEV_COLORS[row.severity_level];
                            return (
                                <tr key={row.id} className="bd-row">
                                    <td style={{ color: 'var(--text-secondary)', width: 28, fontSize: '0.78rem' }}>
                                        {processed.indexOf(row) + 1}
                                    </td>
                                    <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
                                        {row.equipment_name || '—'}
                                        {row.component_name && (
                                            <span style={{ fontWeight: 400, fontSize: '0.82rem', color: 'var(--text-secondary)', marginLeft: 6 }}>
                                                ({row.component_name})
                                            </span>
                                        )}
                                    </td>
                                    <td><span className="tag">{row.asset_tag || '—'}</span></td>
                                    <td>
                                        {sev
                                            ? <span style={{ fontWeight: 700, fontSize: '0.75rem', color: sev }}>{row.severity_level}</span>
                                            : <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>—</span>
                                        }
                                    </td>
                                    <td style={{ color: 'var(--text-secondary)', maxWidth: 200 }}>
                                        <span className="ellipsis">{row.description || '—'}</span>
                                    </td>
                                    <td>
                                        <span className="status-badge" style={{ color: sc.color, background: sc.bg }}>
                                            {row.status}
                                        </span>
                                    </td>
                                    <td style={{ color: 'var(--text-secondary)', whiteSpace: 'nowrap', fontSize: '0.82rem' }}>
                                        {formatDate(row.reported_at)}
                                    </td>
                                    <td style={{ fontWeight: 600, textAlign: 'center' }}>
                                        {row.mttr_hours != null ? `${Number(row.mttr_hours).toFixed(1)} h` : '—'}
                                    </td>
                                    <td style={{ textAlign: 'center' }}>
                                        {/* Full-page navigation — /create-rca/{id} is a Jinja route,
                                            not a SPA route. Using <a href> hits the FastAPI server
                                            so the original RCA workflow page renders. */}
                                        <a
                                            href={`/create-rca/${row.id}`}
                                            title={row.has_rca ? 'Open RCA Report' : 'Create RCA Report'}
                                            style={{
                                                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                                padding: '5px 12px', borderRadius: 6, fontSize: '0.75rem', fontWeight: 700,
                                                background: row.has_rca ? '#33B1B0' : 'rgba(51,177,176,0.10)',
                                                color: row.has_rca ? '#ffffff' : '#33B1B0',
                                                textDecoration: 'none', whiteSpace: 'nowrap',
                                                border: row.has_rca ? '1px solid #33B1B0' : '1px solid rgba(51,177,176,0.35)',
                                                transition: 'all 0.15s',
                                            }}
                                            onMouseEnter={e => {
                                                e.currentTarget.style.transform = 'translateY(-1px)';
                                                e.currentTarget.style.boxShadow = '0 2px 6px rgba(51,177,176,0.25)';
                                            }}
                                            onMouseLeave={e => {
                                                e.currentTarget.style.transform = '';
                                                e.currentTarget.style.boxShadow = '';
                                            }}
                                            onClick={e => e.stopPropagation()}
                                        >
                                            {row.has_rca ? 'Open RCA' : 'Create RCA'}
                                        </a>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* Show more / collapse */}
            {hasMore && (
                <div style={{ textAlign: 'center', marginTop: 12 }}>
                    <button
                        className="btn btn-ghost"
                        style={{ fontSize: '0.82rem', padding: '7px 20px' }}
                        onClick={() => setExpanded(e => !e)}
                    >
                        {expanded
                            ? `▲ Show less`
                            : `▼ Show all ${processed.length} records`
                        }
                    </button>
                </div>
            )}
        </div>
    );
};

export default BreakdownTable;
