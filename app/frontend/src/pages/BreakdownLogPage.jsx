import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { fetchBreakdownEquipment, submitBreakdown } from '../api/breakdown';
import FileUpload from '../components/FileUpload';
import NavBar from '../components/NavBar';

/* ── Constants ──────────────────────────────────────────────── */
const SEVERITY_OPTIONS = [
    { value: 'Critical', label: 'Critical', color: '#ff5e5e', bg: 'rgba(255,94,94,0.15)' },
    { value: 'High', label: 'High', color: '#fb923c', bg: 'rgba(251,146,60,0.15)' },
    { value: 'Medium', label: 'Medium', color: '#ffd93d', bg: 'rgba(255,217,61,0.15)' },
    { value: 'Low', label: 'Low', color: '#4ade80', bg: 'rgba(74,222,128,0.15)' },
];

const FAILURE_TYPES = [
    'Electrical', 'Mechanical', 'Hydraulic',
    'Pneumatic', 'Software', 'Structural', 'Other',
];

/* Divisions are derived from equipment data — no hardcoding */

/* ── Pill selector helpers ──────────────────────────────────── */
const SeverityPill = ({ option, selected, onSelect }) => (
    <button
        type="button"
        onClick={() => onSelect(option.value)}
        className={`pill-btn ${selected === option.value ? 'pill-active' : ''}`}
        style={selected === option.value
            ? { color: option.color, background: option.bg, borderColor: option.color }
            : {}}
    >
        {option.label}
    </button>
);

/* Multi-select: selected is a Set */
const TypePill = ({ value, selected, onSelect }) => (
    <button
        type="button"
        onClick={() => onSelect(value)}
        className={`pill-btn ${selected.has(value) ? 'pill-active pill-type-active' : ''}`}
    >
        {value}
    </button>
);

/* ── Section header ─────────────────────────────────────────── */
const FormSection = ({ step, title, children }) => (
    <div className="bl-section">
        <div className="bl-section-header">
            <div className="bl-step">{step}</div>
            <h3 className="bl-section-title">{title}</h3>
        </div>
        <div className="bl-section-body">{children}</div>
    </div>
);

/* ── Helper: parse datetime-local string to minutes since epoch ── */
const toMinutes = (dtStr) => {
    if (!dtStr) return null;
    const d = new Date(dtStr);
    return isNaN(d.getTime()) ? null : Math.floor(d.getTime() / 60000);
};

/* ── Total form steps (matches layout rows that have sections) ── */
const TOTAL_STEPS = 11;

/* ── Main page ──────────────────────────────────────────────── */
const BreakdownLogPage = () => {
    const { user } = useAuth();
    const navigate = useNavigate();

    /* Equipment dropdown data */
    const [equipment, setEquipment] = useState([]);
    const [eqLoading, setEqLoading] = useState(true);

    /* Form state */
    const now = new Date();
    now.setSeconds(0, 0);
    const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
        .toISOString().slice(0, 16);

    const [form, setForm] = useState({
        division: '',
        equipment_id: '',
        issue_start_at: localNow,
        issue_end_at: localNow,
        feed_loss_applicable: false,
        revenue_loss: '',
        description: '',
        doc_description: '',
        severity_level: '',
        failure_type: new Set(),   // ← now a Set for multi-select
    });
    const [files, setFiles] = useState([]);
    const [errors, setErrors] = useState({});
    const [submitting, setSubmitting] = useState(false);
    const [successMsg, setSuccessMsg] = useState('');
    const [apiError, setApiError] = useState('');

    /* Track which step the user is currently on (1-indexed) */
    const [activeStep, setActiveStep] = useState(1);

    /* Fetch equipment list on mount */
    useEffect(() => {
        fetchBreakdownEquipment()
            .then(setEquipment)
            .catch(() => setEquipment([]))
            .finally(() => setEqLoading(false));
    }, []);

    /* Derive unique divisions from equipment data */
    const divisions = [...new Set(equipment.map(eq => eq.category))].sort();

    /* Filter equipment by selected division */
    const filteredEquipment = form.division
        ? equipment.filter(eq => eq.category === form.division)
        : equipment;

    /* Field change handler */
    const handleChange = (field, value) => {
        setForm(f => {
            const updated = { ...f, [field]: value };
            // Reset equipment when division changes
            if (field === 'division') updated.equipment_id = '';
            return updated;
        });
        if (errors[field]) setErrors(e => ({ ...e, [field]: '' }));
    };

    /* Toggle a failure type in/out of the Set */
    const toggleFailureType = (value) => {
        setForm(f => {
            const next = new Set(f.failure_type);
            if (next.has(value)) {
                next.delete(value);
            } else {
                next.add(value);
            }
            return { ...f, failure_type: next };
        });
        if (errors.failure_type) setErrors(e => ({ ...e, failure_type: '' }));
    };

    /* Computed BD time in minutes — reactive to both datetime fields */
    const bdTimeMinutes = (() => {
        const startMin = toMinutes(form.issue_start_at);
        const endMin   = toMinutes(form.issue_end_at);
        if (startMin === null || endMin === null) return null;
        const diff = endMin - startMin;
        return diff >= 0 ? diff : null;
    })();

    /* Revenue loss per hour by division (₹/hour) */
    const REVENUE_MULTIPLIER = {
        'Pellet 1': 115 * 8000,
        'Pellet 2': 115 * 8000,
        'DRI 1':    12.5 * 20000,
        'DRI 2':    54 * 20000,
        'SMS 1':    12.5 * 20000,
        'SMS 2':    54 * 20000,
        'CPP':      54 * 20000,
        'CPP 2':    54 * 20000,
    };

    /* Auto-calculate revenue loss when feed loss = Yes */
    const autoRevenueLoss = (() => {
        if (!form.feed_loss_applicable) return 0;
        const hours = (bdTimeMinutes ?? 0) / 60;
        if (hours <= 0) return 0;
        const multiplier = REVENUE_MULTIPLIER[form.division] || 0;
        return Math.round(hours * multiplier);
    })();

    /* Validation */
    const validate = () => {
        const e = {};
        if (!form.equipment_id) e.equipment_id = 'Please select equipment.';
        if (!form.issue_start_at) e.issue_start_at = 'Please specify the issue start date & time.';
        return e;
    };

    /* Submit — action: 'rca_ai' | 'create_rca' | 'log_only' */
    const handleSubmit = async (action) => {
        setApiError('');
        setSuccessMsg('');

        const errs = validate();
        if (Object.keys(errs).length) {
            setErrors(errs);
            document.querySelector('.field-error')?.closest('.bl-section')?.scrollIntoView({ behavior: 'smooth' });
            return;
        }

        setSubmitting(true);
        try {
            const selectedEquip = equipment.find(eq => String(eq.id) === String(form.equipment_id));
            const fd = new FormData();
            fd.append('equipment_id', form.equipment_id);
            fd.append('machine_name', selectedEquip ? selectedEquip.name : '');
            fd.append('reported_at', form.issue_start_at);
            fd.append('description', form.description);
            fd.append('severity_level', form.severity_level);
            fd.append('failure_type', Array.from(form.failure_type).join(','));
            fd.append('division', form.division);
            fd.append('issue_end_at', form.issue_end_at);
            fd.append('feed_loss_applicable', form.feed_loss_applicable ? 'Y' : 'N');
            fd.append('revenue_loss', form.feed_loss_applicable ? autoRevenueLoss : form.revenue_loss);
            fd.append('doc_description', form.doc_description);
            files.forEach(f => fd.append('attachments', f));

            const result = await submitBreakdown(fd);
            const logId = result.id;

            if (action === 'rca_ai') {
                // Navigate to Jinja2 create-rca page with AI auto-start
                window.location.href = `/create-rca/${logId}?ai=true`;
            } else if (action === 'create_rca') {
                // Navigate to Jinja2 create-rca page (manual)
                window.location.href = `/create-rca/${logId}`;
            } else {
                setSuccessMsg('Breakdown logged successfully! Redirecting…');
                setTimeout(() => navigate('/dashboard'), 1800);
            }
        } catch (err) {
            setApiError(err.message || 'Failed to submit. Please try again.');
        } finally {
            setSubmitting(false);
        }
    };

    if (!user) return null;

    return (
        <div className="bl-page">
            {/* Ambient blobs */}
            <div className="db-blob db-blob-1" />
            <div className="db-blob db-blob-2" />

            {/* ── Nav bar ──────────────────────────────────── */}
            <NavBar activePage="log-issue" />

            {/* ── Page header ──────────────────────────────── */}
            <div className="bl-hero fade-in">
                <div className="bl-hero-icon">🔧</div>
                <div>
                    <h1 className="bl-hero-title">Log Machinery Breakdown</h1>
                    <p className="bl-hero-sub">Record details of the incident for tracking and analysis.</p>
                </div>
            </div>

            {/* ── Progress indicator ────────────────────────── */}
            <div className="bl-progress fade-in">
                Step {activeStep} of {TOTAL_STEPS}
            </div>

            {/* ── Success / Error banners ───────────────────── */}
            {successMsg && (
                <div className="bl-banner bl-success fade-in">✅ {successMsg}</div>
            )}
            {apiError && (
                <div className="bl-banner bl-error fade-in">⚠️ {apiError}</div>
            )}

            {/* ── Form ─────────────────────────────────────── */}
            <form className="bl-form" onSubmit={e => e.preventDefault()} noValidate>

                {/* ── Row 1: Division | Equipment ───────────── */}
                <div className="bl-row-2col">
                    {/* Division */}
                    <FormSection step="1" title="Division">
                        <select
                            id="division"
                            className="form-input bl-select"
                            value={form.division}
                            onFocus={() => setActiveStep(1)}
                            onChange={e => { setActiveStep(1); handleChange('division', e.target.value); }}
                        >
                            <option value="">— Select division —</option>
                            {divisions.map(d => (
                                <option key={d} value={d}>{d}</option>
                            ))}
                        </select>
                    </FormSection>

                    {/* Equipment */}
                    <FormSection step="2" title="Equipment">
                        {eqLoading ? (
                            <div className="skeleton" style={{ height: 46, borderRadius: 8 }} />
                        ) : (
                            <select
                                id="equipment_id"
                                className={`form-input bl-select ${errors.equipment_id ? 'input-error' : ''}`}
                                value={form.equipment_id}
                                onFocus={() => setActiveStep(2)}
                                onChange={e => { setActiveStep(2); handleChange('equipment_id', e.target.value); }}
                            >
                                <option value="">— Select equipment —</option>
                                {filteredEquipment.map(eq => (
                                    <option key={eq.id} value={eq.id}>
                                        [{eq.asset_tag}] {eq.name}
                                    </option>
                                ))}
                            </select>
                        )}
                        {errors.equipment_id && <p className="field-error">{errors.equipment_id}</p>}
                    </FormSection>
                </div>

                {/* ── Row 2: Start Date & Time | End Date & Time ── */}
                <div className="bl-row-2col">
                    {/* Issue Start Date & Time */}
                    <FormSection step="3" title="Issue Start Date &amp; Time">
                        <input
                            type="datetime-local"
                            id="issue_start_at"
                            className={`form-input ${errors.issue_start_at ? 'input-error' : ''}`}
                            value={form.issue_start_at}
                            max={localNow}
                            onFocus={() => setActiveStep(3)}
                            onChange={e => { setActiveStep(3); handleChange('issue_start_at', e.target.value); }}
                        />
                        {errors.issue_start_at && <p className="field-error">{errors.issue_start_at}</p>}
                    </FormSection>

                    {/* Issue End Date & Time */}
                    <FormSection step="4" title="Issue End Date &amp; Time">
                        <input
                            type="datetime-local"
                            id="issue_end_at"
                            className="form-input"
                            value={form.issue_end_at}
                            onFocus={() => setActiveStep(4)}
                            onChange={e => { setActiveStep(4); handleChange('issue_end_at', e.target.value); }}
                        />
                    </FormSection>
                </div>

                {/* ── Row 3: Feed Loss (Step 5) ─────────────────── */}
                <div>
                    <FormSection step="5" title="Feed Loss Applicable (Y/N)">
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-evenly', width: '100%' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                                <input
                                    type="radio"
                                    name="feed_loss_applicable"
                                    checked={form.feed_loss_applicable === true}
                                    onChange={() => { setActiveStep(5); handleChange('feed_loss_applicable', true); }}
                                />
                                <span>Yes</span>
                            </label>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                                <input
                                    type="radio"
                                    name="feed_loss_applicable"
                                    checked={form.feed_loss_applicable === false}
                                    onChange={() => { setActiveStep(5); handleChange('feed_loss_applicable', false); }}
                                />
                                <span>No</span>
                            </label>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <span style={{ fontWeight: 500, whiteSpace: 'nowrap' }}>BD Time (Minutes):</span>
                                <input
                                    type="text"
                                    className="form-input"
                                    readOnly
                                    value={bdTimeMinutes === null ? '—' : bdTimeMinutes}
                                    placeholder="Auto"
                                    style={{ background: 'rgba(51,177,176,0.05)', cursor: 'default', width: '90px' }}
                                />
                                {bdTimeMinutes === null && form.issue_end_at && form.issue_start_at && (
                                    <span style={{ fontSize: '0.75rem', color: '#fb923c' }}>⚠ End must be after start</span>
                                )}
                            </div>
                        </div>
                    </FormSection>
                </div>

                {/* ── Row 3b: Revenue Loss (Step 6) ───────────────── */}
                <div>
                    <FormSection step="6" title="Estimated Revenue Loss (₹)">
                        <input
                            type="number"
                            id="revenue_loss"
                            className="form-input"
                            placeholder={form.feed_loss_applicable ? 'Auto-calculated' : 'Enter amount in ₹'}
                            min="0"
                            readOnly={form.feed_loss_applicable}
                            value={form.feed_loss_applicable ? autoRevenueLoss : form.revenue_loss}
                            onFocus={() => setActiveStep(6)}
                            onChange={e => { if (!form.feed_loss_applicable) { setActiveStep(6); handleChange('revenue_loss', e.target.value); } }}
                            style={form.feed_loss_applicable ? { background: 'rgba(51,177,176,0.05)', cursor: 'default', color: '#ff5e5e', fontWeight: 700 } : {}}
                        />
                    </FormSection>
                </div>

                {/* ── Row 4: Fault Description (full width) ──── */}
                <div>
                    <FormSection step="7" title="Fault Description">
                        <textarea
                            id="description"
                            className="form-input bl-textarea"
                            placeholder="Describe what happened, any error codes, last known good state…"
                            value={form.description}
                            onFocus={() => setActiveStep(7)}
                            onChange={e => { setActiveStep(7); handleChange('description', e.target.value); }}
                            rows={4}
                        />
                    </FormSection>
                </div>

                {/* ── Row 5: Attachments (full width) ───────── */}
                <div>
                    <FormSection step="8" title="Attachments">
                        <FileUpload files={files} onChange={setFiles} />
                        <div style={{ marginTop: '1rem' }}>
                            <p style={{ fontWeight: 600, marginBottom: '0.4rem', fontSize: '0.9rem' }}>Document Description</p>
                            <input
                                type="text"
                                id="doc_description"
                                className="form-input"
                                placeholder="Brief description of the uploaded document…"
                                value={form.doc_description}
                                onFocus={() => setActiveStep(9)}
                                onChange={e => { setActiveStep(9); handleChange('doc_description', e.target.value); }}
                                style={{ background: '#fff' }}
                            />
                        </div>
                    </FormSection>
                </div>

                {/* ── Row 7: Severity Level (full width) ────── */}
                <div>
                    <FormSection step="10" title="Severity Level (Optional)">
                        <div className="pill-group">
                            {SEVERITY_OPTIONS.map(opt => (
                                <SeverityPill
                                    key={opt.value}
                                    option={opt}
                                    selected={form.severity_level}
                                    onSelect={v => { setActiveStep(10); handleChange('severity_level', v); }}
                                />
                            ))}
                        </div>
                    </FormSection>
                </div>

                {/* ── Row 8: Failure Type (full width, multi-select) ── */}
                <div>
                    <FormSection step="11" title="Failure Type (Optional)">
                        <div className="pill-group">
                            {FAILURE_TYPES.map(type => (
                                <TypePill
                                    key={type}
                                    value={type}
                                    selected={form.failure_type}
                                    onSelect={v => { setActiveStep(11); toggleFailureType(v); }}
                                />
                            ))}
                        </div>
                    </FormSection>
                </div>

                {/* ── Last Row: RCA AI Assist | Create RCA | Cancel ── */}
                <div className="bl-actions">
                    <button
                        type="button"
                        className="btn btn-primary bl-submit-btn"
                        disabled={submitting}
                        onClick={() => handleSubmit('rca_ai')}
                    >
                        {submitting ? (
                            <><span className="spinner" /> Submitting…</>
                        ) : (
                            <><span>🤖</span> RCA AI Assist</>
                        )}
                    </button>
                    <button
                        type="button"
                        className="btn btn-primary bl-submit-btn"
                        disabled={submitting}
                        onClick={() => handleSubmit('create_rca')}
                    >
                        {submitting ? (
                            <><span className="spinner" /> Submitting…</>
                        ) : (
                            <><span>📋</span> Create RCA</>
                        )}
                    </button>
                    <Link to="/dashboard" className="btn btn-ghost" style={{ textDecoration: 'none' }}>
                        Cancel
                    </Link>
                </div>
            </form>
        </div>
    );
};

export default BreakdownLogPage;
