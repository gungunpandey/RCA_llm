import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import NavBar from '../components/NavBar';

const TODAY = new Date();
TODAY.setHours(0, 0, 0, 0);

const PRIORITY_COLOR = { High: '#e03c3c', Medium: '#f0a500', Low: '#33B1B0' };

const COLUMNS = ['Open', 'In Progress', 'Pending Validation', 'Completed'];
const OWNERS = ['Alice Johnson', 'Bob Martinez', 'Carol Lee', 'David Singh', 'Emma Watson'];
const EQUIPMENT = ['CNC Machine', 'Conveyor', 'Boiler', 'Press', 'Pump', 'Motor', 'Compressor'];
const authOpts = () => ({ credentials: 'include' });
const normalise = (c) => ({ ...c, dueDate: c.due_date ?? c.dueDate });

const dueDateInfo = (dueDateStr, status) => {
    if (status === 'Completed') return null;
    const due = new Date(dueDateStr);
    due.setHours(0, 0, 0, 0);
    const diff = Math.round((due - TODAY) / (1000 * 60 * 60 * 24));
    if (diff < 0)  return { label: `${Math.abs(diff)}d overdue`, color: '#e03c3c' };
    if (diff <= 3) return { label: `Due in ${diff}d`, color: '#f0a500' };
    return null;
};

const CAPACard = ({ capa, onStatusChange }) => {
    const navigate = useNavigate();
    const dateInfo = dueDateInfo(capa.dueDate, capa.status);
    const formattedDate = new Date(capa.dueDate).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

    return (
        <div style={{
            background: 'radial-gradient(ellipse at center, #ffffff 30%, rgba(51,177,176,0.14) 100%)',
            border: '1px solid rgba(60,61,63,0.18)',
            borderRadius: 12,
            overflow: 'hidden',
            transition: 'box-shadow 0.2s',
            boxShadow: '0 2px 8px rgba(60,61,63,0.08)',
        }}
            onMouseEnter={e => e.currentTarget.style.boxShadow = '0 6px 20px rgba(60,61,63,0.13)'}
            onMouseLeave={e => e.currentTarget.style.boxShadow = '0 2px 8px rgba(60,61,63,0.08)'}
        >
            {/* Priority strip */}
            <div style={{ height: 4, background: PRIORITY_COLOR[capa.priority] }} />

            <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {/* Title */}
                <p style={{ fontWeight: 700, fontSize: '0.88rem', color: '#1a1a1a', margin: 0, lineHeight: 1.4 }}>
                    {capa.title}
                </p>

                {/* Meta row */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: '0.75rem', color: '#3C3D3F' }}>👤 {capa.owner}</span>
                    <span style={{
                        fontSize: '0.7rem', fontWeight: 700, padding: '2px 8px',
                        borderRadius: 99, background: `${PRIORITY_COLOR[capa.priority]}18`,
                        color: PRIORITY_COLOR[capa.priority],
                    }}>
                        {capa.priority}
                    </span>
                </div>

                {/* Due date */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: '0.75rem', color: dateInfo ? dateInfo.color : '#3C3D3F', fontWeight: dateInfo ? 600 : 400 }}>
                        📅 {formattedDate}
                    </span>
                    {dateInfo && (
                        <span style={{
                            fontSize: '0.68rem', fontWeight: 700,
                            background: `${dateInfo.color}18`, color: dateInfo.color,
                            padding: '1px 7px', borderRadius: 99,
                        }}>
                            {dateInfo.label}
                        </span>
                    )}
                </div>

                {/* Divider */}
                <div style={{ borderTop: '1px solid rgba(60,61,63,0.10)', margin: '2px 0' }} />

                {/* Quick actions */}
                <div style={{ display: 'flex', gap: 6 }}>
                    {capa.status !== 'Completed' && (
                        <button
                            onClick={() => onStatusChange(capa.id, 'Completed')}
                            title="Mark Complete"
                            style={iconBtn('#22a85a')}
                        >✓ Done</button>
                    )}
                    {capa.status !== 'Completed' && (
                        <button
                            title="Edit"
                            style={iconBtn('#33B1B0')}
                            onClick={() => navigate(`/capa/create?edit=${capa.id}`)}
                        >✏ Edit</button>
                    )}
                    <button
                        title="View Details"
                        style={iconBtn('#3C3D3F')}
                        onClick={() => navigate(`/capa/${capa.id}/detail`)}
                    >👁 View</button>
                </div>
            </div>
        </div>
    );
};

const iconBtn = (color) => ({
    fontSize: '0.72rem', fontWeight: 600, padding: '3px 9px',
    borderRadius: 6, border: `1px solid ${color}22`,
    background: `${color}12`, color, cursor: 'pointer',
    fontFamily: 'inherit', transition: 'background 0.15s',
});

const EmptyCol = () => (
    <div style={{
        textAlign: 'center', padding: '28px 12px',
        color: 'rgba(60,61,63,0.4)', fontSize: '0.8rem',
        border: '1.5px dashed rgba(60,61,63,0.15)',
        borderRadius: 10,
    }}>
        No CAPAs here
    </div>
);

const CAPATrackingBoard = () => {
    const navigate = useNavigate();
    const [capas, setCapas]               = useState([]);
    const [loading, setLoading]           = useState(true);
    const [search, setSearch]             = useState('');
    const [filterStatus, setFilterStatus] = useState('');
    const [filterOwner, setFilterOwner]   = useState('');
    const [filterEquip, setFilterEquip]   = useState('');

    useEffect(() => {
        fetch('/api/capa', { credentials: 'include' })
            .then(r => r.json())
            .then(data => setCapas(Array.isArray(data) ? data.map(normalise) : []))
            .catch(() => setCapas([]))
            .finally(() => setLoading(false));
    }, []);

    const handleStatusChange = async (id, newStatus) => {
        setCapas(prev => prev.map(c => c.id === id ? { ...c, status: newStatus } : c));
        try {
            await fetch(`/api/capa/${id}/status`, {
                method: 'PATCH',
                credentials: 'include', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus }),
            });
        } catch (_) {}
    };

    const filtered = useMemo(() => capas.filter(c => {
        if (filterStatus && c.status !== filterStatus) return false;
        if (filterOwner  && c.owner  !== filterOwner)  return false;
        if (filterEquip  && !c.title?.toLowerCase().includes(filterEquip.toLowerCase())) return false;
        if (search && !c.title?.toLowerCase().includes(search.toLowerCase())) return false;
        return true;
    }), [capas, search, filterStatus, filterOwner, filterEquip]);

    const total     = capas.length;
    const inProg    = capas.filter(c => c.status === 'In Progress').length;
    const completed = capas.filter(c => c.status === 'Completed').length;
    const overdue   = capas.filter(c => c.status !== 'Completed' && new Date(c.dueDate) < TODAY).length;

    if (loading) return (
        <div className="db-page">            <NavBar activePage="capa-board" />
            <div className="db-main" style={{ justifyContent: 'center', alignItems: 'center', paddingTop: 60 }}>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Loading CAPAs…</p>
            </div>
        </div>
    );

    return (
        <div className="db-page">
            <div className="db-blob db-blob-1" />
            <div className="db-blob db-blob-2" />

            <NavBar activePage="capa-board" />

            <div className="db-main" style={{ maxWidth: 1400 }}>

                {/* ── Hero ──────────────────────────────── */}
                <div className="bl-hero" style={{ maxWidth: '100%', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                        <span className="bl-hero-icon">📋</span>
                        <div>
                            <h1 className="bl-hero-title">CAPA Tracking Board</h1>
                            <p className="bl-hero-sub">Monitor and manage all corrective & preventive actions</p>
                        </div>
                    </div>
                    <button
                        style={{
                            fontSize: '0.9rem', fontWeight: 700, padding: '10px 22px',
                            borderRadius: 8, border: 'none',
                            background: '#33B1B0', color: '#fff', cursor: 'pointer',
                            fontFamily: 'inherit', transition: 'background 0.15s',
                            whiteSpace: 'nowrap',
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = '#2a9a99'}
                        onMouseLeave={e => e.currentTarget.style.background = '#33B1B0'}
                        onClick={() => navigate('/capa/create')}
                    >＋ Create CAPA</button>
                </div>

                {/* ── Summary bar ───────────────────────── */}
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    {[
                        { label: 'Total CAPAs',  value: total,     color: '#33B1B0' },
                        { label: 'In Progress',  value: inProg,    color: '#f0a500' },
                        { label: 'Completed',    value: completed,  color: '#22a85a' },
                        { label: 'Overdue',      value: overdue,    color: '#e03c3c' },
                    ].map(s => (
                        <div key={s.label} className="glass-card" style={{
                            padding: '10px 20px', display: 'flex', alignItems: 'center', gap: 10, flex: '1 1 140px',
                        }}>
                            <span style={{ fontSize: '1.5rem', fontWeight: 800, color: s.color }}>{s.value}</span>
                            <span style={{ fontSize: '0.78rem', color: '#3C3D3F', fontWeight: 600 }}>{s.label}</span>
                        </div>
                    ))}
                </div>

                {/* ── Filter bar ────────────────────────── */}
                <div className="glass-card" style={{ padding: '12px 18px', display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                    <input
                        className="form-input"
                        style={{ flex: '2 1 180px', padding: '8px 12px', fontSize: '0.85rem' }}
                        placeholder="🔍 Search by CAPA title…"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                    />
                    {[
                        { label: 'All Statuses',   opts: COLUMNS,    val: filterStatus, set: setFilterStatus },
                        { label: 'All Owners',     opts: OWNERS,     val: filterOwner,  set: setFilterOwner  },
                        { label: 'All Equipment',  opts: EQUIPMENT,  val: filterEquip,  set: setFilterEquip  },
                    ].map(f => (
                        <select
                            key={f.label}
                            className="form-input bl-select"
                            style={{ flex: '1 1 140px', padding: '8px 12px', fontSize: '0.85rem' }}
                            value={f.val}
                            onChange={e => f.set(e.target.value)}
                        >
                            <option value="">{f.label}</option>
                            {f.opts.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                    ))}
                    {(search || filterStatus || filterOwner || filterEquip) && (
                        <button
                            className="btn btn-ghost"
                            style={{ padding: '7px 14px', fontSize: '0.82rem', whiteSpace: 'nowrap' }}
                            onClick={() => { setSearch(''); setFilterStatus(''); setFilterOwner(''); setFilterEquip(''); }}
                        >✕ Clear</button>
                    )}
                </div>

                {/* ── Empty state ───────────────────────── */}
                {filtered.length === 0 && (
                    <div className="glass-card" style={{ textAlign: 'center', padding: '48px 24px' }}>
                        <p style={{ fontSize: '1.5rem', marginBottom: 8 }}>📭</p>
                        <p style={{ fontWeight: 700, color: '#1a1a1a', margin: '0 0 6px' }}>No CAPAs found</p>
                        <p style={{ fontSize: '0.85rem', color: '#3C3D3F', margin: 0 }}>
                            No CAPAs yet. Create one from Root Cause Analysis.
                        </p>
                    </div>
                )}

                {/* ── Kanban Board ──────────────────────── */}
                {filtered.length > 0 && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, alignItems: 'start' }}>
                        {COLUMNS.map(col => {
                            const cards = filtered.filter(c => c.status === col);
                            return (
                                <div key={col} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                    {/* Column header */}
                                    <div style={{
                                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                        padding: '8px 12px',
                                        background: 'radial-gradient(ellipse at center, #ffffff 30%, rgba(51,177,176,0.14) 100%)',
                                        border: '1px solid rgba(60,61,63,0.15)',
                                        borderRadius: 10,
                                    }}>
                                        <span style={{ fontWeight: 700, fontSize: '0.82rem', color: '#1a1a1a', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                                            {col}
                                        </span>
                                        <span style={{
                                            fontWeight: 700, fontSize: '0.75rem',
                                            background: 'rgba(51,177,176,0.15)', color: '#33B1B0',
                                            padding: '2px 8px', borderRadius: 99,
                                        }}>{cards.length}</span>
                                    </div>

                                    {/* Cards */}
                                    {cards.length === 0
                                        ? <EmptyCol />
                                        : cards.map(c => (
                                            <CAPACard key={c.id} capa={c} onStatusChange={handleStatusChange} />
                                        ))
                                    }
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* Responsive note for smaller screens */}
                <style>{`
                    @media (max-width: 900px) {
                        .capa-board-grid { grid-template-columns: repeat(2, 1fr) !important; }
                    }
                    @media (max-width: 560px) {
                        .capa-board-grid { grid-template-columns: 1fr !important; }
                    }
                `}</style>

            </div>
        </div>
    );
};

export default CAPATrackingBoard;
