import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '../context/AuthContext';
import NavBar from '../components/NavBar';
import { fetchEquipmentList, fetchEquipmentDetail, createEquipment, addEquipmentComponent, deleteEquipmentComponent } from '../api/equipment';

const CRITICALITY_OPTIONS = ['High', 'Medium', 'Low'];
const SORT_OPTIONS = [
    { label: 'Plant → Equipment', value: 'plant_asc' },
    { label: 'Equipment A–Z',     value: 'name_asc'  },
    { label: 'Most Failures',     value: 'fail_desc' },
    { label: 'Least Failures',    value: 'fail_asc'  },
    { label: 'Latest Failure',    value: 'date_desc' },
];

const criticalityColor = (c) => {
    if (c === 'Critical') return { color: '#000000', bg: 'rgba(255,94,94,0.12)' };
    if (c === 'High')     return { color: '#000000', bg: 'rgba(251,146,60,0.12)' };
    if (c === 'Medium')   return { color: '#000000', bg: 'rgba(255,217,61,0.12)' };
    return { color: '#000000', bg: 'rgba(74,222,128,0.12)' };
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

const formatDate = (d) => {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
};

const EMPTY_FORM = { name: '', asset_tag: '', category: '', criticality: 'Medium' };

const SortIcon = ({ field, sortKey, sortDir }) => {
    const active = sortKey === field;
    return (
        <span style={{ marginLeft: 4, fontSize: '0.65rem', opacity: active ? 1 : 0.3, color: active ? '#33B1B0' : 'inherit' }}>
            {active ? (sortDir === 'asc' ? '▲' : '▼') : '⇅'}
        </span>
    );
};

const EquipmentMasterPage = () => {
    const { user } = useAuth();
    
    const isPlantHeadOrAdmin = user?.role === 'Admin' || [
        'BNFC', 'Pellet 1', 'Pellet 2', 'SMS 1', 'SMS 2',
        'DRI 1', 'DRI 2', 'CPP', 'CPP 2', 'PGP', 'FIRE SERVICE'
    ].includes(user?.role);

    const [equipment, setEquipment] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [critFilter, setCritFilter] = useState('');
    const [plantFilter, setPlantFilter] = useState(() => (user?.role !== 'Admin' ? user?.role : ''));

    // Sync plant filter if user loads asynchronously
    useEffect(() => {
        if (user && user.role !== 'Admin') {
            setPlantFilter(user.role);
        }
    }, [user]);
    const [sortMode, setSortMode] = useState('plant_asc');
    const [selected, setSelected] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [showAdd, setShowAdd] = useState(false);
    const [form, setForm] = useState(EMPTY_FORM);
    const [formErrors, setFormErrors] = useState({});
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState('');
    const [loadError, setLoadError] = useState('');
    const [successMsg, setSuccessMsg] = useState('');
    const [newComponentName, setNewComponentName] = useState('');
    const [componentSaving, setComponentSaving] = useState(false);
    const [componentError, setComponentError] = useState('');

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

    /* Derived plant list for filter dropdown */
    const plants = useMemo(() => {
        const s = new Set(equipment.map(e => e.category).filter(Boolean));
        return [...s].sort();
    }, [equipment]);

    /* Frontend sort + plant-filter */
    const displayEquipment = useMemo(() => {
        let list = [...equipment];
        if (plantFilter) list = list.filter(e => e.category === plantFilter);
        switch (sortMode) {
            case 'plant_asc':
                list.sort((a, b) => {
                    const pa = (a.category || '').localeCompare(b.category || '');
                    return pa !== 0 ? pa : (a.name || '').localeCompare(b.name || '');
                });
                break;
            case 'name_asc':
                list.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
                break;
            case 'fail_desc':
                list.sort((a, b) => (b.failure_count || 0) - (a.failure_count || 0));
                break;
            case 'fail_asc':
                list.sort((a, b) => (a.failure_count || 0) - (b.failure_count || 0));
                break;
            case 'date_desc':
                list.sort((a, b) => {
                    if (!a.last_failure_date) return 1;
                    if (!b.last_failure_date) return -1;
                    return new Date(b.last_failure_date) - new Date(a.last_failure_date);
                });
                break;
            default: break;
        }
        return list;
    }, [equipment, plantFilter, sortMode]);

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
        return errs;
    };

    const handleAddComponent = async (e) => {
        e.preventDefault();
        if (!newComponentName.trim()) return;
        setComponentSaving(true);
        setComponentError('');
        try {
            const added = await addEquipmentComponent(selected.id, newComponentName.trim());
            setSelected(prev => ({
                ...prev,
                components: [...(prev.components || []), added]
            }));
            setNewComponentName('');
        } catch (err) {
            setComponentError(err.message || 'Failed to add component.');
        } finally {
            setComponentSaving(false);
        }
    };

    const handleDeleteComponent = async (compId) => {
        if (!window.confirm('Are you sure you want to delete this component?')) return;
        setComponentError('');
        try {
            await deleteEquipmentComponent(compId);
            setSelected(prev => ({
                ...prev,
                components: (prev.components || []).filter(c => c.id !== compId)
            }));
        } catch (err) {
            setComponentError(err.message || 'Failed to delete component.');
        }
    };

    const handleAddSubmit = async (e) => {
        e.preventDefault();
        setSaveError('');
        const errs = validateForm();
        if (Object.keys(errs).length) { setFormErrors(errs); return; }
        setSaving(true);
        try {
            await createEquipment({ ...form });
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
                    <p className="bl-hero-sub">Track all assets, criticality, and breakdown history.</p>
                </div>
                {isPlantHeadOrAdmin && (
                    <button
                        className="btn btn-primary"
                        style={{ width: 'auto', whiteSpace: 'nowrap' }}
                        onClick={() => {
                            setShowAdd(true);
                            setForm({
                                ...EMPTY_FORM,
                                category: user?.role !== 'Admin' ? user.role : ''
                            });
                            setSaveError('');
                            setFormErrors({});
                        }}
                    >
                        + Add New Equipment
                    </button>
                )}
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

            {/* ── Filters & Sort ── */}
            <div className="fade-in" style={{
                display: 'flex', gap: 10, flexWrap: 'wrap', position: 'relative', zIndex: 1,
                maxWidth: 1280, width: '100%', margin: '0 auto', alignItems: 'center',
            }}>
                <input
                    type="text"
                    className="form-input"
                    placeholder="🔍  Search by name or asset tag…"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    style={{ maxWidth: 300 }}
                />
                {/* Plant filter */}
                {user?.role === 'Admin' ? (
                    <select
                        className="form-input bl-select"
                        value={plantFilter}
                        onChange={e => setPlantFilter(e.target.value)}
                        style={{ maxWidth: 180 }}
                    >
                        <option value="">All Plants</option>
                        {plants.map(p => <option key={p} value={p}>{p}</option>)}
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
                        🏭 {user?.role}
                    </div>
                )}
                {/* Criticality filter */}
                <select
                    className="form-input bl-select"
                    value={critFilter}
                    onChange={e => setCritFilter(e.target.value)}
                    style={{ maxWidth: 180 }}
                >
                    <option value="">All Criticalities</option>
                    {CRITICALITY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                {/* Sort */}
                <select
                    className="form-input bl-select"
                    value={sortMode}
                    onChange={e => setSortMode(e.target.value)}
                    style={{ maxWidth: 200 }}
                >
                    {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
                {/* Record count */}
                {!loading && (
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginLeft: 4, whiteSpace: 'nowrap' }}>
                        {displayEquipment.length} equipment
                    </span>
                )}
            </div>

            {/* ── Table ── */}
            <div className="db-main fade-in">
                <div className="glass-card db-panel" style={{ padding: 0, overflow: 'hidden' }}>
                    {loading ? (
                        <div style={{ padding: 48, textAlign: 'center' }}>
                            <span className="spinner" style={{ borderTopColor: '#33B1B0', borderColor: 'rgba(51,177,176,0.2)', display: 'inline-block' }} />
                            <p style={{ marginTop: 12, color: 'var(--text-secondary)', fontSize: '0.88rem' }}>Loading equipment…</p>
                        </div>
                    ) : displayEquipment.length === 0 ? (
                        <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.88rem' }}>
                            No equipment found.
                        </div>
                    ) : (
                        <div className="bd-table-wrapper">
                            <table className="bd-table" style={{ minWidth: 720 }}>
                                <thead>
                                    <tr>
                                        <th style={{ cursor: 'pointer' }} onClick={() => setSortMode('name_asc')}>
                                            Asset Tag
                                        </th>
                                        <th style={{ cursor: 'pointer' }} onClick={() => setSortMode('name_asc')}>
                                            Equipment Name <SortIcon field="name_asc" sortKey={sortMode} sortDir="asc" />
                                        </th>
                                        <th style={{ cursor: 'pointer' }} onClick={() => setSortMode('plant_asc')}>
                                            Plant <SortIcon field="plant_asc" sortKey={sortMode} sortDir="asc" />
                                        </th>
                                        <th>Criticality</th>
                                        <th style={{ cursor: 'pointer' }} onClick={() => setSortMode(s => s === 'fail_desc' ? 'fail_asc' : 'fail_desc')}>
                                            Failures (till date) <SortIcon field={sortMode === 'fail_asc' ? 'fail_asc' : 'fail_desc'} sortKey={sortMode} sortDir={sortMode === 'fail_asc' ? 'asc' : 'desc'} />
                                        </th>
                                        <th style={{ cursor: 'pointer' }} onClick={() => setSortMode('date_desc')}>
                                            Last Failure <SortIcon field="date_desc" sortKey={sortMode} sortDir="desc" />
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {displayEquipment.map(eq => (
                                        <tr
                                            key={eq.id}
                                            className="bd-row"
                                            style={{ cursor: 'pointer' }}
                                            onClick={() => openDetail(eq)}
                                        >
                                            <td><span className="tag">{eq.asset_tag}</span></td>
                                            <td style={{ fontWeight: 600 }}>{eq.name}</td>
                                            <td>
                                                {eq.category
                                                    ? <span className="category-tag">{eq.category}</span>
                                                    : <span style={{ color: 'rgba(60,61,63,0.35)', fontSize: '0.8rem' }}>—</span>}
                                            </td>
                                            <td><CriticalityBadge value={eq.criticality || 'Medium'} /></td>
                                            <td>
                                                <span style={{
                                                    fontWeight: 700,
                                                    color: eq.failure_count > 5 ? '#ff5e5e' : eq.failure_count > 2 ? '#fb923c' : 'var(--text-primary)',
                                                }}>
                                                    {eq.failure_count ?? 0}
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

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px', marginBottom: 20 }}>
                            {[
                                { label: 'Plant', value: selected.category || '—' },
                                { label: 'Criticality', value: <CriticalityBadge value={selected.criticality || 'Medium'} /> },
                                { label: 'Failures (till date)', value: <span style={{ fontWeight: 700 }}>{selected.failure_count ?? 0}</span> },
                                { label: 'Last Failure', value: formatDate(selected.last_failure_date) },
                            ].map(({ label, value }) => (
                                <div key={label}>
                                    <p style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{label}</p>
                                    <div style={{ fontSize: '0.88rem', color: 'var(--text-primary)' }}>{value}</div>
                                </div>
                            ))}
                        </div>

                        {/* Components / Sub-Equipment Section */}
                        <p className="section-title" style={{ marginBottom: 12, marginTop: 16 }}>Components / Sub-Equipment</p>
                        
                        {componentError && (
                            <div style={{ color: '#ff5e5e', fontSize: '0.78rem', marginBottom: 10 }}>
                                ⚠️ {componentError}
                            </div>
                        )}

                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                            {(!selected.components || selected.components.length === 0) ? (
                                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0, fontStyle: 'italic' }}>
                                    No components defined.
                                </p>
                            ) : (
                                selected.components.map(comp => (
                                    <span key={comp.id} style={{
                                        display: 'inline-flex', alignItems: 'center', gap: 6,
                                        padding: '4px 10px', borderRadius: 99, fontSize: '0.78rem',
                                        fontWeight: 600, color: 'var(--text-primary)',
                                        background: 'rgba(51,177,176,0.10)',
                                        border: '1px solid rgba(51,177,176,0.25)',
                                    }}>
                                        {comp.name}
                                        {isPlantHeadOrAdmin && (
                                            <button
                                                type="button"
                                                onClick={() => handleDeleteComponent(comp.id)}
                                                style={{
                                                    background: 'none', border: 'none', color: '#ff5e5e',
                                                    cursor: 'pointer', fontSize: '0.85rem', padding: 0,
                                                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                                    marginLeft: 2
                                                }}
                                                title="Remove component"
                                            >✕</button>
                                        )}
                                    </span>
                                ))
                            )}
                        </div>

                        {isPlantHeadOrAdmin && (
                            <form onSubmit={handleAddComponent} style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                                <input
                                    type="text"
                                    className="form-input"
                                    placeholder="Add sub-equipment (e.g. Feed Pump)…"
                                    value={newComponentName}
                                    onChange={e => setNewComponentName(e.target.value)}
                                    style={{
                                        flex: 1, padding: '6px 12px', fontSize: '0.82rem',
                                        background: 'rgba(255,255,255,0.7)',
                                        border: '1.5px solid rgba(60,61,63,0.15)',
                                    }}
                                    disabled={componentSaving}
                                />
                                <button
                                    type="submit"
                                    className="btn btn-primary"
                                    style={{ padding: '6px 16px', fontSize: '0.82rem', width: 'auto', minWidth: 0 }}
                                    disabled={componentSaving || !newComponentName.trim()}
                                >
                                    {componentSaving ? 'Adding…' : 'Add'}
                                </button>
                            </form>
                        )}

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
                                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center', marginBottom: 4 }}>
                                                {b.failure_type && (
                                                    <span className="category-tag">{b.failure_type}</span>
                                                )}
                                                {b.component_name && (
                                                    <span className="tag" style={{ background: 'rgba(251,146,60,0.12)', color: '#fb923c', fontSize: '0.68rem', fontWeight: 700 }}>
                                                        ⚙️ {b.component_name}
                                                    </span>
                                                )}
                                            </div>
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

            {/* ── Add Equipment Modal ── */}
            {showAdd && (
                <div
                    style={{
                        position: 'fixed', inset: 0,
                        background: 'rgba(0,0,0,0.55)',
                        zIndex: 200, backdropFilter: 'blur(6px)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        padding: '16px',
                    }}
                    onClick={(e) => { if (e.target === e.currentTarget) setShowAdd(false); }}
                >
                    <div
                        className="fade-in"
                        style={{
                            width: '100%', maxWidth: 480, zIndex: 201,
                            padding: '32px 32px 28px',
                            maxHeight: 'calc(100vh - 32px)',
                            overflowY: 'auto',
                            background: '#ffffff',
                            borderRadius: 16,
                            boxShadow: '0 24px 64px rgba(0,0,0,0.30)',
                            border: '1px solid rgba(51,177,176,0.20)',
                        }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                            <div>
                                <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#1a1a1a', margin: 0 }}>Add New Equipment</h2>
                                <p style={{ fontSize: '0.8rem', color: '#6b7280', margin: '4px 0 0' }}>Fill in the details below to register a new asset.</p>
                            </div>
                            <button onClick={() => setShowAdd(false)} style={{
                                background: 'rgba(60,61,63,0.08)', border: 'none', borderRadius: 8,
                                width: 32, height: 32, cursor: 'pointer', fontSize: '1rem',
                                display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#3C3D3F',
                            }}>✕</button>
                        </div>
                        {saveError && (
                            <div className="alert-error" style={{ marginBottom: 16, padding: '10px 14px', borderRadius: 8 }}>⚠️ {saveError}</div>
                        )}
                        <form onSubmit={handleAddSubmit} noValidate>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                                {[
                                    { field: 'name', label: 'Equipment Name *', type: 'text', placeholder: 'e.g. CNC Lathe Machine' },
                                    { field: 'asset_tag', label: 'Asset Tag *', type: 'text', placeholder: 'e.g. EQ-1021' },
                                    { field: 'category', label: 'Plant', type: 'text', placeholder: 'e.g. Plant A' },
                                ].map(({ field, label, type, placeholder }) => (
                                    <div key={field} className="form-group">
                                        <label className="form-label" style={{ fontWeight: 700, fontSize: '0.82rem', color: '#374151', marginBottom: 6, display: 'block' }}>{label}</label>
                                        <input
                                            type={type}
                                            className={`form-input ${formErrors[field] ? 'input-error' : ''}`}
                                            placeholder={placeholder}
                                            value={form[field]}
                                            onChange={e => handleFormChange(field, e.target.value)}
                                            style={{ 
                                                background: (field === 'category' && user?.role !== 'Admin') ? 'rgba(60,61,63,0.06)' : '#f9fafb', 
                                                border: '1.5px solid rgba(60,61,63,0.18)',
                                                color: (field === 'category' && user?.role !== 'Admin') ? 'rgba(60,61,63,0.5)' : 'inherit',
                                                cursor: (field === 'category' && user?.role !== 'Admin') ? 'not-allowed' : 'text'
                                            }}
                                            disabled={field === 'category' && user?.role !== 'Admin'}
                                        />
                                        {formErrors[field] && <p className="field-error">{formErrors[field]}</p>}
                                    </div>
                                ))}

                                <div className="form-group">
                                    <label className="form-label" style={{ fontWeight: 700, fontSize: '0.82rem', color: '#374151', marginBottom: 6, display: 'block' }}>Criticality</label>
                                    <select
                                        className="form-input bl-select"
                                        value={form.criticality}
                                        onChange={e => handleFormChange('criticality', e.target.value)}
                                        style={{ background: '#f9fafb', border: '1.5px solid rgba(60,61,63,0.18)' }}
                                    >
                                        {CRITICALITY_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                                    </select>
                                </div>
                            </div>

                            <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
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
