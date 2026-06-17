import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import NavBar from '../components/NavBar';


const DEFAULT_STEPS = [
    'Recalibrate machine per OEM specification',
    'Schedule quarterly preventive calibration audit',
];

const CAPACreationPage = () => {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const editId = searchParams.get('edit');
    const isEditMode = Boolean(editId);

    const [actionType, setActionType] = useState('corrective');
    const [steps, setSteps] = useState(DEFAULT_STEPS);
    const [owner, setOwner] = useState('');
    const [owners, setOwners] = useState([
        'Mr. S.K. Muduli', 'Mr. Nitish kumar', 'MR. SOURAV MOHANTY',
        'MR. GANESH MOHANTY', 'Mr. Bijayasen Pradhan', 'Mr. Bhajahari Das',
        'MR. KAUSHAL SINGH', 'MR. B. S. CHANDEL', 'Mr. Bijay Pradhan',
        'Mr. Uday Singh', 'Mr. Sunil Das', 'Mr. Sidharta Mahapatra',
        'Raghu Viswanadhu'
    ]);

    // Fetch existing CAPA owners to dynamically populate autocomplete datalist
    useEffect(() => {
        fetch('/api/capa', { credentials: 'include' })
            .then(r => r.json())
            .then(data => {
                if (Array.isArray(data)) {
                    const uniqueOwners = new Set([
                        'Mr. S.K. Muduli', 'Mr. Nitish kumar', 'MR. SOURAV MOHANTY',
                        'MR. GANESH MOHANTY', 'Mr. Bijayasen Pradhan', 'Mr. Bhajahari Das',
                        'MR. KAUSHAL SINGH', 'MR. B. S. CHANDEL', 'Mr. Bijay Pradhan',
                        'Mr. Uday Singh', 'Mr. Sunil Das', 'Mr. Sidharta Mahapatra',
                        'Raghu Viswanadhu'
                    ]);
                    data.forEach(c => {
                        if (c.owner && c.owner.trim()) {
                            const parts = c.owner.replace(/\r/g, '').split(/[\n+&,]/);
                            parts.forEach(part => {
                                const trimmed = part.trim();
                                if (trimmed && trimmed.length > 2 && !trimmed.startsWith('CA:') && !trimmed.startsWith('PA:')) {
                                    uniqueOwners.add(trimmed);
                                }
                            });
                        }
                    });
                    setOwners([...uniqueOwners].sort());
                }
            })
            .catch(() => {});
    }, []);
    const [dueDate, setDueDate] = useState('');
    const [priority, setPriority] = useState('');
    const [riskImpact, setRiskImpact] = useState('');
    const [status, setStatus] = useState('Open');
    const [submitting, setSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState('');

    // Pre-fill form when editing an existing CAPA
    useEffect(() => {
        if (!editId) return;
        fetch(`/api/capa/${editId}`, {
            credentials: 'include',
        })
            .then(r => r.json())
            .then(data => {
                if (!data || data.error) return;
                const raw = data.capa ?? data;
                setActionType(raw.action_type?.toLowerCase() ?? 'corrective');
                setSteps(raw.actions ? raw.actions.split('\n').filter(Boolean) : DEFAULT_STEPS);
                setOwner(raw.owner ?? '');
                setDueDate((raw.due_date ?? raw.dueDate ?? '').split('T')[0]);
                setPriority(raw.priority ?? '');
                setRiskImpact(raw.impact_level ? `${raw.impact_level} Impact` : '');
                setStatus(raw.status ?? 'Open');
            })
            .catch(() => {});
    }, [editId]);

    const rootCause = 'Improper machine calibration';

    const daysRemaining = (() => {
        if (!dueDate) return null;
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const due = new Date(dueDate);
        const diff = Math.round((due - today) / (1000 * 60 * 60 * 24));
        return diff >= 0 ? diff : null;
    })();

    const handleStepChange = (i, val) => {
        const updated = [...steps];
        updated[i] = val;
        setSteps(updated);
    };

    const addStep = () => setSteps(prev => [...prev, '']);

    const removeStep = (i) => setSteps(prev => prev.filter((_, idx) => idx !== i));

    const handleCreate = async (e) => {
        e.preventDefault();
        setSubmitError('');
        setSubmitting(true);
        try {
            const url    = isEditMode ? `/api/capa/${editId}` : '/api/capa';
            const method = isEditMode ? 'PUT' : 'POST';
            const res = await fetch(url, {
                method,
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action_type: actionType.charAt(0).toUpperCase() + actionType.slice(1),
                    actions: steps.filter(Boolean).join('\n'),
                    owner,
                    due_date: dueDate,
                    priority,
                    impact_level: riskImpact.replace(' Impact', ''),
                    status,
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.message || 'Submission failed.');
            }
            navigate('/capa/board');
        } catch (err) {
            setSubmitError(err.message);
        } finally {
            setSubmitting(false);
        }
    };

    const isReady = owner && dueDate && priority && riskImpact && status;

    return (
        <div className="bl-page">
            <div className="db-blob db-blob-1" />
            <div className="db-blob db-blob-2" />

            <NavBar activePage="" />

            {/* Hero */}
            <div className="bl-hero">
                <span className="bl-hero-icon">🛡️</span>
                <div>
                    <h1 className="bl-hero-title">{isEditMode ? 'Edit CAPA' : 'CAPA Creation'}</h1>
                    <p className="bl-hero-sub">{isEditMode ? 'Update the details of this Corrective / Preventive Action' : 'Create a Corrective / Preventive Action from an identified Root Cause'}</p>
                </div>
            </div>

            <form className="bl-form" onSubmit={handleCreate} noValidate>

                {/* ── 1. Root Cause Reference ──────────────────── */}
                <div className="bl-section">
                    <div className="bl-section-header">
                        <span className="bl-step">1</span>
                        <h2 className="bl-section-title">Root Cause Reference</h2>
                    </div>
                    <div className="bl-section-body">
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 12,
                            padding: '12px 16px',
                            background: 'rgba(51,177,176,0.07)',
                            border: '1px solid rgba(51,177,176,0.3)',
                            borderRadius: 'var(--radius-sm)',
                        }}>
                            <span style={{ fontSize: '1.2rem' }}>🔍</span>
                            <div>
                                <p style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 2px' }}>
                                    Root Cause
                                </p>
                                <p style={{ fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>{rootCause}</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* ── 2. Action Type ───────────────────────────── */}
                <div className="bl-section">
                    <div className="bl-section-header">
                        <span className="bl-step">2</span>
                        <h2 className="bl-section-title">Action Type</h2>
                    </div>
                    <div className="bl-section-body">
                        <div className="pill-group">
                            {[
                                { val: 'corrective', label: 'Corrective Action' },
                                { val: 'preventive', label: 'Preventive Action' },
                                { val: 'both', label: 'Both' },
                            ].map(opt => (
                                <button
                                    key={opt.val}
                                    type="button"
                                    className={`pill-btn ${actionType === opt.val ? 'pill-active' : ''}`}
                                    onClick={() => setActionType(opt.val)}
                                >
                                    {opt.label}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                {/* ── 3. CAPA Action Steps ─────────────────────── */}
                <div className="bl-section">
                    <div className="bl-section-header">
                        <span className="bl-step">3</span>
                        <h2 className="bl-section-title">CAPA Action Steps</h2>
                    </div>
                    <div className="bl-section-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                        {steps.map((step, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <span style={{
                                    width: 22, height: 22, borderRadius: '50%',
                                    background: 'rgba(51,177,176,0.15)',
                                    color: '#33B1B0', fontSize: '0.72rem', fontWeight: 700,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    flexShrink: 0,
                                }}>{i + 1}</span>
                                <input
                                    className="form-input"
                                    value={step}
                                    onChange={e => handleStepChange(i, e.target.value)}
                                    placeholder={`Step ${i + 1}…`}
                                    style={{ flex: 1 }}
                                />
                                {steps.length > 1 && (
                                    <button
                                        type="button"
                                        onClick={() => removeStep(i)}
                                        style={{
                                            background: 'none', border: 'none',
                                            cursor: 'pointer', color: 'var(--text-secondary)',
                                            fontSize: '1rem', lineHeight: 1, padding: '4px',
                                            flexShrink: 0,
                                        }}
                                        title="Remove step"
                                    >✕</button>
                                )}
                            </div>
                        ))}
                        <button
                            type="button"
                            className="btn btn-ghost"
                            onClick={addStep}
                            style={{ alignSelf: 'flex-start', fontSize: '0.85rem', padding: '8px 16px', marginTop: 4 }}
                        >
                            + Add another step
                        </button>
                    </div>
                </div>

                {/* ── 4–5. Owner & Due Date ────────────────────── */}
                <div className="bl-section">
                    <div className="bl-section-header">
                        <span className="bl-step">4</span>
                        <h2 className="bl-section-title">Assignment & Timeline</h2>
                    </div>
                    <div className="bl-section-body" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                        <div className="form-group">
                            <label className="form-label">Assign Owner</label>
                            <input
                                type="text"
                                className="form-input"
                                placeholder="Select or type owner name..."
                                value={owner}
                                onChange={e => setOwner(e.target.value)}
                                list="owners-list"
                            />
                            <datalist id="owners-list">
                                {owners.map(o => <option key={o} value={o} />)}
                            </datalist>
                        </div>

                        <div className="form-group">
                            <label className="form-label">Due Date</label>
                            <input
                                className="form-input"
                                type="date"
                                value={dueDate}
                                min={new Date().toISOString().split('T')[0]}
                                onChange={e => setDueDate(e.target.value)}
                            />
                            {daysRemaining !== null && (
                                <p style={{ fontSize: '0.78rem', color: '#33B1B0', margin: '6px 0 0', fontWeight: 500 }}>
                                    📅 This CAPA will be active for <strong>{daysRemaining}</strong> day{daysRemaining !== 1 ? 's' : ''}
                                </p>
                            )}
                            {dueDate && daysRemaining === null && (
                                <p style={{ fontSize: '0.78rem', color: 'var(--danger)', margin: '6px 0 0' }}>
                                    ⚠ Due date is in the past
                                </p>
                            )}
                        </div>
                    </div>
                </div>

                {/* ── 6–8. Priority, Risk, Status ─────────────── */}
                <div className="bl-section">
                    <div className="bl-section-header">
                        <span className="bl-step">5</span>
                        <h2 className="bl-section-title">Priority, Risk & Status</h2>
                    </div>
                    <div className="bl-section-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
                        <div className="form-group">
                            <label className="form-label">Priority</label>
                            <select
                                className="form-input bl-select"
                                value={priority}
                                onChange={e => setPriority(e.target.value)}
                            >
                                <option value="">— Select —</option>
                                <option value="High">High</option>
                                <option value="Medium">Medium</option>
                                <option value="Low">Low</option>
                            </select>
                        </div>

                        <div className="form-group">
                            <label className="form-label">Risk / Impact</label>
                            <select
                                className="form-input bl-select"
                                value={riskImpact}
                                onChange={e => setRiskImpact(e.target.value)}
                            >
                                <option value="">— Select —</option>
                                <option value="High Impact">High Impact</option>
                                <option value="Medium Impact">Medium Impact</option>
                                <option value="Low Impact">Low Impact</option>
                            </select>
                        </div>

                        <div className="form-group">
                            <label className="form-label">Status</label>
                            <select
                                className="form-input bl-select"
                                value={status}
                                onChange={e => setStatus(e.target.value)}
                            >
                                <option value="Open">Open</option>
                                <option value="In Progress">In Progress</option>
                                <option value="Pending Validation">Pending Validation</option>
                                <option value="Completed">Completed</option>
                            </select>
                        </div>
                    </div>
                </div>

                {/* ── 9. Confirmation Card ─────────────────────── */}
                {isReady && (
                    <div className="bl-section fade-in">
                        <div className="bl-section-header">
                            <span className="bl-step">✓</span>
                            <h2 className="bl-section-title">Review &amp; Confirm</h2>
                        </div>
                        <div className="bl-section-body">
                            <div style={{
                                display: 'grid', gridTemplateColumns: '1fr 1fr',
                                gap: '12px 24px',
                                padding: '16px', marginBottom: 16,
                                background: 'rgba(51,177,176,0.05)',
                                border: '1px solid rgba(51,177,176,0.2)',
                                borderRadius: 'var(--radius-sm)',
                            }}>
                                {[
                                    { label: 'Root Cause', value: rootCause },
                                    { label: 'Owner', value: owner },
                                    { label: 'Due Date', value: dueDate },
                                    { label: 'Priority', value: priority },
                                    { label: 'Risk / Impact', value: riskImpact },
                                    { label: 'Status', value: status },
                                ].map(row => (
                                    <div key={row.label}>
                                        <p style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 2px' }}>
                                            {row.label}
                                        </p>
                                        <p style={{ fontWeight: 600, color: 'var(--text-primary)', margin: 0, fontSize: '0.9rem' }}>
                                            {row.value}
                                        </p>
                                    </div>
                                ))}
                            </div>

                            {submitError && (
                                <p style={{ fontSize: '0.82rem', color: 'var(--danger)', marginBottom: 10 }}>⚠ {submitError}</p>
                            )}

                            <button
                                type="submit"
                                className="btn btn-primary"
                                style={{ width: '100%' }}
                                disabled={submitting}
                            >
                                {submitting ? (isEditMode ? 'Saving…' : 'Creating…') : (isEditMode ? '✅ Save Changes' : '✅ Confirm & Create CAPA')}
                            </button>
                        </div>
                    </div>
                )}

                {!isReady && (
                    <p style={{ textAlign: 'center', fontSize: '0.82rem', color: 'var(--text-secondary)', position: 'relative', zIndex: 1 }}>
                        Fill in all required fields above to preview and confirm the CAPA.
                    </p>
                )}

            </form>
        </div>
    );
};

export default CAPACreationPage;
