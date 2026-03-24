import React, { useState, useRef, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import NavBar from '../components/NavBar';

const CAPA = {
    title: 'Fix hydraulic leak on Press #2',
    status: 'In Progress',
    owner: 'Alice Johnson',
    dueDate: '2026-04-05',
    priority: 'High',
    rootCause: 'Improper machine calibration',
};

const INIT_TASKS = [
    { id: 1, title: 'Isolate press and depressurise hydraulic circuit', done: true,  comment: '', file: null },
    { id: 2, title: 'Inspect all hydraulic fittings and seals',          done: true,  comment: '', file: null },
    { id: 3, title: 'Replace faulty O-ring on cylinder port #3',         done: true,  comment: 'Done — used OEM seal kit', file: 'seal_photo.jpg' },
    { id: 4, title: 'Flush and refill hydraulic fluid',                  done: false, comment: '', file: null },
    { id: 5, title: 'Conduct pressure test at 300 bar for 30 min',       done: false, comment: '', file: null },
    { id: 6, title: 'Verify no leaks under full operating load',          done: false, comment: '', file: null },
];

const INIT_COMMENTS = [
    { id: 1, author: 'Alice Johnson',  time: '21 Mar 2026, 09:14', text: 'Hydraulic fluid has been ordered, arriving tomorrow.' },
    { id: 2, author: 'David Singh',    time: '21 Mar 2026, 11:02', text: 'OEM seal kit confirmed compatible with press model HP-220.' },
];

const INIT_LOG = [
    { time: '21 Mar, 11:02', label: 'Comment added by David Singh' },
    { time: '21 Mar, 09:14', label: 'Comment added by Alice Johnson' },
    { time: '20 Mar, 16:45', label: 'Evidence uploaded for Task 3' },
    { time: '20 Mar, 14:30', label: 'Task 3 marked complete' },
    { time: '19 Mar, 10:00', label: 'CAPA created from RCA #47' },
];

const PRIORITY_COLOR = { High: '#e03c3c', Medium: '#f0a500', Low: '#33B1B0' };
const STATUS_COLOR   = { 'In Progress': '#f0a500', 'Pending Validation': '#7c6bff', 'Completed': '#22a85a', 'Open': '#33B1B0' };

const authH = () => ({ 'Content-Type': 'application/json' });

const fmtTime = () => new Date().toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

const badge = (label, color) => (
    <span style={{
        fontSize: '0.72rem', fontWeight: 700, padding: '3px 10px',
        borderRadius: 99, background: `${color}18`, color,
    }}>{label}</span>
);

const STATIC_CAPA = CAPA;

export default function CAPADetailPage() {
    const { id: capaId } = useParams();
    const navigate = useNavigate();
    const [capaInfo, setCapaInfo]   = useState(STATIC_CAPA);
    const [tasks, setTasks]         = useState(INIT_TASKS);
    const [comments, setComments]   = useState(INIT_COMMENTS);
    const [log, setLog]             = useState(INIT_LOG);
    const [newComment, setNewComment] = useState('');
    const [newTask, setNewTask]     = useState('');
    const [validated, setValidated] = useState(false);
    const fileRefs = useRef({});

    useEffect(() => {
        if (!capaId) return;
        fetch(`/api/capa-detail/${capaId}/details`, { credentials: 'include', headers: authH() })
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (!data) return;
                if (data.capa) {
                    setCapaInfo({
                        title:     data.capa.actions?.split('\n')[0] || data.capa.actions || STATIC_CAPA.title,
                        status:    data.capa.status    || STATIC_CAPA.status,
                        owner:     data.capa.owner     || STATIC_CAPA.owner,
                        dueDate:   data.capa.due_date  || STATIC_CAPA.dueDate,
                        priority:  data.capa.priority  || STATIC_CAPA.priority,
                        rootCause: STATIC_CAPA.rootCause,
                    });
                }
                if (data.tasks?.length) {
                    setTasks(data.tasks.map(t => ({
                        id: t.id, title: t.task_title,
                        done: t.is_completed, comment: '', file: null,
                    })));
                }
                if (data.comments?.length) {
                    setComments(data.comments.map(c => ({
                        id: c.id, author: 'Team',
                        time: new Date(c.created_at).toLocaleString('en-GB'),
                        text: c.comment_text,
                    })));
                }
            })
            .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [capaId]);

    const done  = tasks.filter(t => t.done).length;
    const total = tasks.length;
    const pct   = total ? Math.round((done / total) * 100) : 0;

    const toggleTask = async (id) => {
        const task = tasks.find(t => t.id === id);
        if (!task) return;
        const next = !task.done;
        setTasks(prev => prev.map(t => t.id === id ? { ...t, done: next } : t));
        addLog(next ? `Task "${task.title.slice(0, 30)}…" marked complete` : 'Task reopened');
        try {
            await fetch(`/api/capa-detail/tasks/${id}/status`, {
                method: 'PATCH', credentials: 'include', headers: authH(),
                body: JSON.stringify({ is_completed: next }),
            });
        } catch (_) {}
    };

    const updateComment = (id, val) => setTasks(prev => prev.map(t => t.id === id ? { ...t, comment: val } : t));

    const handleFile = (id, file) => {
        if (!file) return;
        setTasks(prev => prev.map(t => t.id === id ? { ...t, file: file.name } : t));
        addLog(`Evidence uploaded for task`);
    };

    const addTask = async () => {
        if (!newTask.trim()) return;
        try {
            const res = await fetch('/api/capa-detail/tasks', {
                method: 'POST', credentials: 'include', headers: authH(),
                body: JSON.stringify({ capa_id: capaId, task_title: newTask.trim() }),
            });
            const data = res.ok ? await res.json() : null;
            const taskId = data?.task?.id ?? Date.now();
            setTasks(prev => [...prev, { id: taskId, title: newTask.trim(), done: false, comment: '', file: null }]);
        } catch (_) {
            setTasks(prev => [...prev, { id: Date.now(), title: newTask.trim(), done: false, comment: '', file: null }]);
        }
        setNewTask('');
        addLog('New task added');
    };

    const addComment = async () => {
        if (!newComment.trim()) return;
        try {
            const res = await fetch('/api/capa-detail/comments', {
                method: 'POST', credentials: 'include', headers: authH(),
                body: JSON.stringify({ capa_id: capaId, comment_text: newComment.trim() }),
            });
            const data = res.ok ? await res.json() : null;
            const entry = { id: data?.comment?.id ?? Date.now(), author: 'You', time: 'Just now', text: newComment.trim() };
            setComments(prev => [...prev, entry]);
        } catch (_) {
            setComments(prev => [...prev, { id: Date.now(), author: 'You', time: 'Just now', text: newComment.trim() }]);
        }
        addLog('Comment added');
        setNewComment('');
    };

    const addLog = (label) => {
        setLog(prev => [{ time: fmtTime(), label }, ...prev]);
    };

    const markValidation = () => {
        setValidated(true);
        addLog('CAPA marked ready for validation');
    };

    return (
        <div className="db-page">
            <div className="db-blob db-blob-1" />
            <div className="db-blob db-blob-2" />
            <NavBar activePage="" />

            <div style={{ maxWidth: 1300, width: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20, position: 'relative', zIndex: 1 }}>

                {/* ── Top header card ─────────────────────────────── */}
                <div className="glass-card" style={{ padding: '20px 24px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                                <span style={{ fontSize: '1.3rem', fontWeight: 800, color: '#1a1a1a' }}>🛡️ {capaInfo.title}</span>
                                {badge(capaInfo.status, STATUS_COLOR[capaInfo.status] ?? '#33B1B0')}
                                {badge(capaInfo.priority, PRIORITY_COLOR[capaInfo.priority] ?? '#ccc')}
                            </div>
                            <p style={{ margin: 0, fontSize: '0.82rem', color: '#3C3D3F' }}>
                                <strong>Root Cause:</strong> {capaInfo.rootCause}
                            </p>
                        </div>
                        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                            {[['Owner', capaInfo.owner], ['Due Date', capaInfo.dueDate]].map(([l, v]) => (
                                <div key={l}>
                                    <p style={{ margin: '0 0 2px', fontSize: '0.7rem', fontWeight: 700, color: '#3C3D3F', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{l}</p>
                                    <p style={{ margin: 0, fontWeight: 600, fontSize: '0.88rem', color: '#1a1a1a' }}>{v}</p>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Progress bar */}
                    <div style={{ marginTop: 16 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#3C3D3F' }}>Task Progress</span>
                            <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#33B1B0' }}>{done} / {total} tasks completed ({pct}%)</span>
                        </div>
                        <div style={{ height: 8, background: 'rgba(60,61,63,0.10)', borderRadius: 99, overflow: 'hidden' }}>
                            <div style={{
                                height: '100%', borderRadius: 99,
                                background: pct === 100 ? '#22a85a' : 'linear-gradient(90deg,#33B1B0,#2a9a99)',
                                width: `${pct}%`, transition: 'width 0.4s ease',
                            }} />
                        </div>
                    </div>
                </div>

                {/* ── Main 2-col layout ────────────────────────────── */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, alignItems: 'start' }}>

                    {/* ── LEFT: tasks + comments ────────────────────── */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

                        {/* Task checklist */}
                        <div className="glass-card" style={{ padding: '18px 22px' }}>
                            <p style={{ margin: '0 0 14px', fontSize: '0.78rem', fontWeight: 700, color: '#3C3D3F', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                                Task Checklist
                            </p>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                {tasks.map(task => (
                                    <div key={task.id} style={{
                                        border: '1px solid rgba(60,61,63,0.12)',
                                        borderRadius: 10, padding: '12px 14px',
                                        background: task.done ? 'rgba(34,168,90,0.04)' : '#fff',
                                        transition: 'background 0.2s',
                                    }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                            <input
                                                type="checkbox"
                                                checked={task.done}
                                                onChange={() => toggleTask(task.id)}
                                                style={{ accentColor: '#33B1B0', width: 16, height: 16, flexShrink: 0, cursor: 'pointer' }}
                                            />
                                            <span style={{
                                                flex: 1, fontSize: '0.88rem', fontWeight: 500,
                                                color: task.done ? '#3C3D3F' : '#1a1a1a',
                                                textDecoration: task.done ? 'line-through' : 'none',
                                            }}>{task.title}</span>

                                            {/* Evidence upload */}
                                            <input
                                                type="file"
                                                ref={el => fileRefs.current[task.id] = el}
                                                style={{ display: 'none' }}
                                                onChange={e => handleFile(task.id, e.target.files[0])}
                                            />
                                            <button
                                                onClick={() => fileRefs.current[task.id]?.click()}
                                                style={{
                                                    fontSize: '0.7rem', fontWeight: 600, padding: '3px 10px',
                                                    borderRadius: 6, border: '1px solid rgba(51,177,176,0.3)',
                                                    background: 'rgba(51,177,176,0.08)', color: '#33B1B0',
                                                    cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: 'inherit',
                                                }}
                                            >📎 Evidence</button>
                                        </div>

                                        {task.file && (
                                            <p style={{ margin: '6px 0 0 26px', fontSize: '0.72rem', color: '#22a85a' }}>
                                                ✓ {task.file}
                                            </p>
                                        )}

                                        <input
                                            className="form-input"
                                            placeholder="Add a comment for this task…"
                                            value={task.comment}
                                            onChange={e => updateComment(task.id, e.target.value)}
                                            style={{ marginTop: 8, fontSize: '0.8rem', padding: '6px 10px' }}
                                        />
                                    </div>
                                ))}
                            </div>

                            {/* Add new task */}
                            <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
                                <input
                                    className="form-input"
                                    placeholder="New task title…"
                                    value={newTask}
                                    onChange={e => setNewTask(e.target.value)}
                                    onKeyDown={e => e.key === 'Enter' && addTask()}
                                    style={{ fontSize: '0.85rem', padding: '8px 12px' }}
                                />
                                <button
                                    onClick={addTask}
                                    className="btn btn-ghost"
                                    style={{ whiteSpace: 'nowrap', padding: '8px 14px', fontSize: '0.82rem' }}
                                >+ Add Task</button>
                            </div>
                        </div>

                        {/* Comments */}
                        <div className="glass-card" style={{ padding: '18px 22px' }}>
                            <p style={{ margin: '0 0 14px', fontSize: '0.78rem', fontWeight: 700, color: '#3C3D3F', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                                Comments
                            </p>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 14 }}>
                                {comments.map(c => (
                                    <div key={c.id} style={{
                                        padding: '10px 14px', borderRadius: 8,
                                        background: 'rgba(51,177,176,0.05)',
                                        border: '1px solid rgba(51,177,176,0.15)',
                                    }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                            <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#1a1a1a' }}>{c.author}</span>
                                            <span style={{ fontSize: '0.7rem', color: '#3C3D3F' }}>{c.time}</span>
                                        </div>
                                        <p style={{ margin: 0, fontSize: '0.83rem', color: '#3C3D3F' }}>{c.text}</p>
                                    </div>
                                ))}
                            </div>

                            <div style={{ display: 'flex', gap: 8 }}>
                                <input
                                    className="form-input"
                                    placeholder="Write a comment…"
                                    value={newComment}
                                    onChange={e => setNewComment(e.target.value)}
                                    onKeyDown={e => e.key === 'Enter' && addComment()}
                                    style={{ fontSize: '0.85rem', padding: '8px 12px' }}
                                />
                                <button
                                    onClick={addComment}
                                    className="btn btn-ghost"
                                    style={{ whiteSpace: 'nowrap', padding: '8px 14px', fontSize: '0.82rem' }}
                                >Add Comment</button>
                            </div>
                        </div>

                        {/* Validation button */}
                        <button
                            onClick={markValidation}
                            disabled={validated}
                            className="btn btn-primary"
                            style={{
                                width: '100%', padding: '16px', fontSize: '1rem',
                                fontWeight: 700, letterSpacing: '0.02em',
                                background: validated
                                    ? '#22a85a'
                                    : 'linear-gradient(135deg,#33B1B0,#2a9a99)',
                            }}
                        >
                            {validated ? '✅ Marked Ready for Validation' : '🔖 Mark CAPA Ready for Validation'}
                        </button>
                    </div>

                    {/* ── RIGHT: activity log ───────────────────────── */}
                    <div className="glass-card" style={{ padding: '18px 20px', position: 'sticky', top: 20 }}>
                        <p style={{ margin: '0 0 14px', fontSize: '0.78rem', fontWeight: 700, color: '#3C3D3F', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                            Activity Log
                        </p>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                            {log.map((entry, i) => (
                                <div key={i} style={{ display: 'flex', gap: 10, paddingBottom: 14, position: 'relative' }}>
                                    {/* timeline line */}
                                    {i < log.length - 1 && (
                                        <div style={{
                                            position: 'absolute', left: 7, top: 18,
                                            width: 1, bottom: 0,
                                            background: 'rgba(51,177,176,0.2)',
                                        }} />
                                    )}
                                    <div style={{
                                        width: 15, height: 15, borderRadius: '50%', flexShrink: 0,
                                        background: 'linear-gradient(135deg,#33B1B0,#2a9a99)',
                                        marginTop: 2,
                                    }} />
                                    <div>
                                        <p style={{ margin: 0, fontSize: '0.8rem', fontWeight: 500, color: '#1a1a1a', lineHeight: 1.4 }}>{entry.label}</p>
                                        <p style={{ margin: '2px 0 0', fontSize: '0.7rem', color: '#3C3D3F' }}>{entry.time}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
