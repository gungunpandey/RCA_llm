import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import NavBar from '../components/NavBar';
import { fetchEquipmentList, fetchEquipmentDetail, createEquipment } from '../api/equipment';

const CRITICALITY_OPTIONS = ['Critical', 'High', 'Medium', 'Low'];

const criticalityColor = (c) => {
    if (c === 'Critical') return { color: '#ff5e5e', bg: 'rgba(255,94,94,0.12)' };
    if (c === 'High')     return { color: '#fb923c', bg: 'rgba(251,146,60,0.12)' };
    if (c === 'Medium')   return { color: '#ffd93d', bg: 'rgba(255,217,61,0.12)' };
    return { color: '#4ade80', bg: 'rgba(74,222,128,0.12)' };
};

const healthColor = (score) => {
    if (score >= 80) return '#4ade80';
    if (score >= 50) return '#ffd93d';
    return '#ff5e5e';
};

const CriticalityBadge = ({ value }) => {
    const { color, bg } = criticalityColor(value);
    return (
        <span style={{
            display: 'inline-flex', alignItems: 'center',
            padding: '2px 10px', borderRadius: 99, fontSize: '0.72rem',
            fontWeight: 700, color, background: bg, whiteSpace: 'nowrap',
        }}>
            {value}
        </span>
    );
};

const HealthDot = ({ score }) => {
    const color = healthColor(score);
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0 }} />
            <span style={{ fontWeight: 700, color }}>{score != null ? score : '—'}</span>
        </div>
    );
};

const formatDate = (d) => {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
};

const EMPTY_FORM = { name: '', asset_tag: '', category: '', location: '', criticality: 'Medium', asset_health_score: 100 };

const EquipmentMasterPage = () => {
    const { user } = useAuth();
    const [equipment, setEquipment] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [critFilter, setCritFilter] = useState('');
    const [selected, setSelected] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [showAdd, setShowAdd] = useState(false);
    const [form, setForm] = useState(EMPTY_FORM);
    const [formErrors, setFormErrors] = useState({});
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState('');
    const [loadError, setLoadError] = useState('');
    const [successMsg, setSuccessMsg] = useState('');

    const loadList = useCallback(() => {
        setLoading(true);
        setLoadError('');
        fetchEquipmentList({ search, criticality: critFilter })
            .then(data => { setEquipment(data); })
            .catch(err => {
                setEquipment([]);
                setLoadError(err.message || 'Failed to load equipment.');
            })
            .finally(() => setLoading(false));
    }, [search, critFilter]);

    useEffect(() => {
        const t = setTimeout(loadList, 300);
        return () => clearTimeout(t);
    }, [loadList]);

    const openDetail = async (eq) => {
        setSelected({ ...eq, breakdowns: null });
        setDetailLoading(true);
        try {
            const data = await fetchEquipmentDetail(eq.id);
            setSelected(data);
        } catch {
            setSelected(prev => ({ ...prev, breakdowns: [] }));
        } finally {
            setDetailLoading(false);
        }
    };

    const closeDetail = () => setSelected(null);

    const handleFormChange = (field, value) => {
        setForm(f => ({ ...f, [field]: value }));
        if (formErrors[field]) setFormErrors(e => ({ ...e, [field]: '' }));
    };

    const validateForm = () => {
        const errs = {};
        if (!form.name.trim()) errs.name = 'Name is required.';
        if (!form.asset_tag.trim()) errs.asset_tag = 'Asset tag is required.';
        const hs = Number(form.asset_health_score);
        if (isNaN(hs) || hs < 0 || hs > 100) errs.asset_health_score = 'Must be 0–100.';
        return errs;
    };

    const handleAddSubmit = async (e) => {
        e.preventDefault();
        setSaveError('');
        const errs = validateForm();
        if (Object.keys(errs).length) { setFormErrors(errs); return; }
        setSaving(true);
        try {
            await createEquipment({ ...form, asset_health_score: Number(form.asset_health_score) });
            setShowAdd(false);
            setForm(EMPTY_FORM);
            setSuccessMsg('Equipment added successfully!');
            setTimeout(() => setSuccessMsg(''), 3000);
            loadList();
        } catch (err) {
            setSaveError(err.message || 'Failed to save.');
        } finally {
            setSaving(false);
        }
    };

    if (!user) return null;

    return (
        <div className="db-page">
            <div className="db-blob db-blob-1" />
            <div className="db-blob db-blob-2" />

            <NavBar activePage="equipment" />

            {/* ── Page Header ── */}
            <div className="bl-hero fade-in" style={{ maxWidth: '100%' }}>
                <div className="bl-hero-icon">🏭</div>
                <div style={{ flex: 1 }}>
                    <h1 className="bl-hero-title">Equipment Master</h1>
                    <p className="bl-hero-sub">Track all assets, criticality, health scores, and breakdown history.</p>
                </div>
                <button
                    className="btn btn-primary"
                    style={{ width: 'auto', whiteSpace: 'nowrap' }}
                    onClick={() => { setShowAdd(true); setForm(EMPTY_FORM); setSaveError(''); setFormErrors({}); }}
                >
                    + Add New Equipment
                </button>
            </div>

            {successMsg && (
                <div className="bl-banner bl-success fade-in" style={{ maxWidth: '100%', position: 'relative', zIndex: 1 }}>
                    ✅ {successMsg}
                </div>
            )}
            {loadError && (
                <div className="bl-banner bl-error fade-in" style={{ maxWidth: '100%', position: 'relative', zIndex: 1 }}>
                    ⚠️ {loadError}
                </div>
            )}

            {/* ── Filters ── */}
            <div className="fade-in" style={{
                display: 'flex', gap: 12, flexWrap: 'wrap', position: 'relative', zIndex: 1,
                maxWidth: 1280, width: '100%', margin: '0 auto',
            }}>
                <input
                    type="text"
                    className="form-input"
                    placeholder="🔍  Search by name or asset tag…"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    style={{ maxWidth: 320 }}
                />
                <select
                    className="form-input bl-select"
                    value={critFilter}
                    onChange={e => setCritFilter(e.target.value)}
                    style={{ maxWidth: 200 }}
                >
                    <option value="">All Criticalities</option>
                    {CRITICALITY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
            </div>

            {/* ── Table ── */}
            <div className="db-main fade-in">
                <div className="glass-card db-panel" style={{ padding: 0, overflow: 'hidden' }}>
                    {loading ? (
                        <div style={{ padding: 48, textAlign: 'center' }}>
                            <span className="spinner" style={{ borderTopColor: '#33B1B0', borderColor: 'rgba(51,177,176,0.2)', display: 'inline-block' }} />
                            <p style={{ marginTop: 12, color: 'var(--text-secondary)', fontSize: '0.88rem' }}>Loading equipment…</p>
                        </div>
                    ) : equipment.length === 0 ? (
                        <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.88rem' }}>
                            No equipment found.
                        </div>
                    ) : (
                        <div className="bd-table-wrapper">
                            <table className="bd-table">
                                <thead>
                                    <tr>
                                        <th>Asset Tag</th>
                                        <th>Equipment Name</th>
                                        <th>Category</th>
                                        <th>Location</th>
                                        <th>Criticality</th>
                                        <th>Health Score</th>
                                        <th>Failures</th>
                                        <th>Last Failure</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {equipment.map(eq => (
                                        <tr
                                            key={eq.id}
                                            className="bd-row"
                                            style={{ cursor: 'pointer' }}
                                            onClick={() => openDetail(eq)}
                                        >
                                            <td><span className="tag">{eq.asset_tag}</span></td>
                                            <td style={{ fontWeight: 600 }}>{eq.name}</td>
                                            <td>
                                                {eq.category ? <span className="category-tag">{eq.category}</span> : <span style={{ color: 'rgba(60,61,63,0.35)', fontSize: '0.8rem' }}>—</span>}
                                            </td>
                                            <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{eq.location || '—'}</td>
                                            <td><CriticalityBadge value={eq.criticality || 'Medium'} /></td>
                                            <td><HealthDot score={eq.asset_health_score} /></td>
                                            <td>
                                                <span style={{
                                                    fontWeight: 700,
                                                    color: eq.failure_count > 5 ? '#ff5e5e' : eq.failure_count > 2 ? '#fb923c' : 'var(--text-primary)',
                                                }}>
                                                    {eq.failure_count}
                                                </span>
                                            </td>
                                            <td style={{ fontSize: '0.83rem', color: 'var(--text-secondary)' }}>
                                                {formatDate(eq.last_failure_date)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>

            {/* ── Detail Side Panel ── */}
            {selected && (
                <>
                    <div
                        onClick={closeDetail}
                        style={{
                            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.18)',
                            zIndex: 100, backdropFilter: 'blur(2px)',
                        }}
                    />
                    <div
                        className="glass-card fade-in"
                        style={{
                            position: 'fixed', top: 0, right: 0, bottom: 0,
                            width: '420px', maxWidth: '95vw', zIndex: 101,
                            borderRadius: '16px 0 0 16px',
                            overflowY: 'auto', display: 'flex', flexDirection: 'column',
                            padding: '28px 24px',
                        }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
                            <div>
                                <span className="tag" style={{ fontSize: '0.78rem' }}>{selected.asset_tag}</span>
                                <h2 style={{ fontSize: '1.15rem', fontWeight: 700, marginTop: 6, color: 'var(--text-primary)' }}>{selected.name}</h2>
                            </div>
                            <button
                                onClick={closeDetail}
                                className="btn btn-ghost"
                                style={{ padding: '6px 12px', fontSize: '1rem', minWidth: 0, borderRadius: 8 }}
                            >✕</button>
                        </div>

                        {/* Details grid */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px', marginBottom: 20 }}>
                            {[
                                { label: 'Category', value: selected.category || '—' },
                                { label: 'Location', value: selected.location || '—' },
                                { label: 'Criticality', value: <CriticalityBadge value={selected.criticality || 'Medium'} /> },
                                { label: 'Health Score', value: <HealthDot score={selected.asset_health_score} /> },
                                { label: 'Total Failures', value: <span style={{ fontWeight: 700 }}>{selected.failure_count}</span> },
                                { label: 'Last Failure', value: formatDate(selected.last_failure_date) },
                            ].map(({ label, value }) => (
                                <div key={label}>
                                    <p style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{label}</p>
                                    <div style={{ fontSize: '0.88rem', color: 'var(--text-primary)' }}>{value}</div>
                                </div>
                            ))}
                        </div>

                        {/* Breakdown history */}
                        <p className="section-title" style={{ marginBottom: 12 }}>Breakdown History</p>
                        {detailLoading ? (
                            <div className="skeleton" style={{ height: 60, borderRadius: 8 }} />
                        ) : (!selected.breakdowns || selected.breakdowns.length === 0) ? (
                            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', textAlign: 'center', padding: '24px 0' }}>No breakdown history.</p>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                {selected.breakdowns.map(b => {
                                    const sev = { Critical: '#ff5e5e', High: '#fb923c', Medium: '#ffd93d', Low: '#4ade80' }[b.severity_level] || '#ccc';
                                    return (
                                        <div key={b.id} className="glass-card" style={{ padding: '12px 14px' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: sev }}>{b.severity_level}</span>
                                                <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{formatDate(b.reported_at)}</span>
                                            </div>
                                            {b.failure_type && (
                                                <span className="category-tag" style={{ marginBottom: 4, display: 'inline-block' }}>{b.failure_type}</span>
                                            )}
                                            {b.description && (
                                                <p className="ellipsis" style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0 }}>{b.description}</p>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </>
            )}

            {showAdd && (
                <div
                    style={{
                        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.20)',
                        zIndex: 200, backdropFilter: 'blur(3px)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        padding: '16px',
                    }}
                    onClick={(e) => { if (e.target === e.currentTarget) setShowAdd(false); }}
                >
                    <div
                        className="glass-card fade-in"
                        style={{
                            width: '100%', maxWidth: 480, zIndex: 201,
                            padding: '28px 28px 24px',
                            maxHeight: 'calc(100vh - 32px)',
                            overflowY: 'auto',
                        }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                            <h2 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Add New Equipment</h2>
                            <button onClick={() => setShowAdd(false)} className="btn btn-ghost" style={{ padding: '6px 12px', minWidth: 0, borderRadius: 8 }}>✕</button>
                        </div>
                        {saveError && (
                            <div className="alert-error" style={{ marginBottom: 14 }}>⚠️ {saveError}</div>
                        )}
                        <form onSubmit={handleAddSubmit} noValidate>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                                {[
                                    { field: 'name', label: 'Equipment Name *', type: 'text', placeholder: 'e.g. CNC Lathe Machine' },
                                    { field: 'asset_tag', label: 'Asset Tag *', type: 'text', placeholder: 'e.g. EQ-1021' },
                                    { field: 'category', label: 'Category', type: 'text', placeholder: 'e.g. Mechanical' },
                                    { field: 'location', label: 'Location', type: 'text', placeholder: 'e.g. Plant A – Bay 3' },
                                ].map(({ field, label, type, placeholder }) => (
                                    <div key={field} className="form-group">
                                        <label className="form-label">{label}</label>
                                        <input
                                            type={type}
                                            className={`form-input ${formErrors[field] ? 'input-error' : ''}`}
                                            placeholder={placeholder}
                                            value={form[field]}
                                            onChange={e => handleFormChange(field, e.target.value)}
                                        />
                                        {formErrors[field] && <p className="field-error">{formErrors[field]}</p>}
                                    </div>
                                ))}

                                <div className="form-group">
                                    <label className="form-label">Criticality</label>
                                    <select
                                        className="form-input bl-select"
                                        value={form.criticality}
                                        onChange={e => handleFormChange('criticality', e.target.value)}
                                    >
                                        {CRITICALITY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                                    </select>
                                </div>

                                <div className="form-group">
                                    <label className="form-label">Asset Health Score (0–100)</label>
                                    <input
                                        type="number"
                                        min={0}
                                        max={100}
                                        className={`form-input ${formErrors.asset_health_score ? 'input-error' : ''}`}
                                        value={form.asset_health_score}
                                        onChange={e => handleFormChange('asset_health_score', e.target.value)}
                                    />
                                    {formErrors.asset_health_score && <p className="field-error">{formErrors.asset_health_score}</p>}
                                </div>
                            </div>

                            <div style={{ display: 'flex', gap: 12, marginTop: 22 }}>
                                <button type="submit" className="btn btn-primary" style={{ flex: 1 }} disabled={saving}>
                                    {saving ? <><span className="spinner" /> Saving…</> : '+ Add Equipment'}
                                </button>
                                <button type="button" className="btn btn-ghost" style={{ flex: 1 }} onClick={() => setShowAdd(false)}>
                                    Cancel
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default EquipmentMasterPage;
