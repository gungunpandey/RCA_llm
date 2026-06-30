import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import NavBar from '../components/NavBar';
import {
    listConversations, createConversation, getConversation,
    deleteConversation, sendConversationMessage,
} from '../api/chat';

const SUGGESTED_PROMPTS = [
    { text: "What is the correct vibration limit for a rotary kiln motor?", label: "Vibration limits" },
    { text: "Search manuals for lubrication procedures on kiln girth gears.", label: "Lubrication procedures" },
    { text: "Have we seen VFD overcurrent trips on Pellet 1 or DRI plants before?", label: "Historical trips" },
    { text: "Suggest corrective actions for a motor winding insulation failure.", label: "Winding failure CAPA" }
];

const COL_MAX = 1040;   // centered conversation column width

const MarkdownBubble = ({ text }) => (
    <div className="chat-md">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
);

const SourcesDropdown = ({ sources }) => {
    const manuals = sources?.manuals || [];
    const web = sources?.web || [];
    const total = manuals.length + web.length;
    if (total === 0) return null;
    return (
        <details style={{ marginTop: 8, width: '100%' }}>
            <summary style={{
                cursor: 'pointer', listStyle: 'none', display: 'inline-flex', alignItems: 'center', gap: 6,
                fontSize: '0.72rem', fontWeight: 700, color: '#2b8c8b', padding: '4px 10px', borderRadius: 99,
                background: 'rgba(51,177,176,0.08)', border: '1px solid rgba(51,177,176,0.22)',
            }}>🔎 Sources ({total})</summary>
            <div style={{
                marginTop: 8, padding: '10px 14px', borderRadius: 10, background: 'rgba(51,177,176,0.04)',
                border: '1px solid rgba(51,177,176,0.15)', fontSize: '0.78rem', lineHeight: 1.5,
            }}>
                {manuals.length > 0 && (
                    <div style={{ marginBottom: web.length ? 10 : 0 }}>
                        <div style={{ fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 4 }}>📖 Plant manuals</div>
                        <ul style={{ margin: 0, paddingLeft: 18 }}>
                            {manuals.map((m, i) => (
                                <li key={i} style={{ color: 'var(--text-primary)' }}>{m.title}{m.page ? ` — p.${m.page}` : ''}</li>
                            ))}
                        </ul>
                    </div>
                )}
                {web.length > 0 && (
                    <div>
                        <div style={{ fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 4 }}>🌐 Web</div>
                        <ul style={{ margin: 0, paddingLeft: 18 }}>
                            {web.map((w, i) => (
                                <li key={i}><a href={w.url} target="_blank" rel="noopener noreferrer" style={{ color: '#2b8c8b', wordBreak: 'break-all' }}>{w.title || w.url}</a></li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>
        </details>
    );
};

const ChatPage = () => {
    const [conversations, setConversations] = useState([]);
    const [activeId, setActiveId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [inputText, setInputText] = useState('');
    const [loading, setLoading] = useState(false);
    const [statusText, setStatusText] = useState('');
    const [error, setError] = useState(null);
    const [attachments, setAttachments] = useState([]);   // [{type,name,data,mime}]
    const [preview, setPreview] = useState(null);          // {type,name,data} shown in lightbox
    const chatEndRef = useRef(null);
    const fileInputRef = useRef(null);

    const MAX_FILE_MB = 8;

    const onPickFiles = async (e) => {
        const files = Array.from(e.target.files || []);
        e.target.value = '';   // allow re-selecting the same file
        for (const f of files) {
            if (f.size > MAX_FILE_MB * 1024 * 1024) {
                setError(`"${f.name}" exceeds ${MAX_FILE_MB} MB.`);
                continue;
            }
            const isPdf = f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf');
            const isImg = f.type.startsWith('image/');
            if (!isPdf && !isImg) {
                setError(`"${f.name}" is not a supported image or PDF.`);
                continue;
            }
            const data = await new Promise((res) => {
                const r = new FileReader();
                r.onload = () => res(r.result);   // data URL
                r.readAsDataURL(f);
            });
            setAttachments(prev => [...prev, { type: isPdf ? 'pdf' : 'image', name: f.name, data, mime: f.type }]);
        }
    };

    const removeAttachment = (idx) => setAttachments(prev => prev.filter((_, i) => i !== idx));

    const refreshList = useCallback(async () => {
        try { setConversations(await listConversations()); } catch { /* ignore */ }
    }, []);

    useEffect(() => { refreshList(); }, [refreshList]);
    useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);

    const newChat = () => { setActiveId(null); setMessages([]); setError(null); };

    const openConversation = async (id) => {
        if (id === activeId) return;
        setError(null);
        try {
            const c = await getConversation(id);
            setActiveId(c.id);
            setMessages((c.messages || []).map(m => ({ ...m, atts: m.attachments || m.atts || [] })));
        } catch (e) { setError(e.message); }
    };

    const removeConversation = async (id, e) => {
        e.stopPropagation();
        try {
            await deleteConversation(id);
            if (id === activeId) newChat();
            refreshList();
        } catch (err) { setError(err.message); }
    };

    const handleSend = async (textToSend) => {
        let query = (textToSend || '').trim();
        const atts = attachments;
        if ((!query && atts.length === 0) || loading) return;
        if (!query && atts.length) query = 'Please analyze the attached file(s).';
        setError(null);
        setInputText('');
        setAttachments([]);

        let convId = activeId;
        if (!convId) {
            try {
                const c = await createConversation();
                convId = c.id;
                setActiveId(convId);
            } catch (e) { setError(e.message); return; }
        }

        setMessages(prev => [...prev, { role: 'user', content: query, atts }]);
        setLoading(true);
        setStatusText(atts.length ? 'Analyzing attachment…' : 'Searching manuals and history…');
        const t1 = setTimeout(() => setStatusText('Querying knowledge base & web…'), 700);
        const t2 = setTimeout(() => setStatusText('ProdAI is synthesizing an answer…'), 1800);

        try {
            const data = await sendConversationMessage(convId, query, atts.length ? atts : null);
            [t1, t2].forEach(clearTimeout);
            if (data.status === 'success') {
                setMessages(prev => [...prev, {
                    role: 'assistant', content: data.reply,
                    sources: data.sources || { manuals: [], web: [] },
                }]);
                refreshList();
            } else {
                throw new Error(data.message || 'Unknown response status');
            }
        } catch (err) {
            [t1, t2].forEach(clearTimeout);
            setError(err.message || 'Failed to communicate with the AI assistant.');
        } finally {
            setLoading(false);
            setStatusText('');
        }
    };

    return (
        <div className="db-page" style={{ gap: 0, paddingBottom: 0 }}>
            <style>{`
                .chat-md > *:first-child { margin-top: 0; }
                .chat-md > *:last-child { margin-bottom: 0; }
                .chat-md p { margin: 0 0 8px; }
                .chat-md ul, .chat-md ol { margin: 4px 0 8px; padding-left: 20px; }
                .chat-md li { margin: 2px 0; }
                .chat-md h1, .chat-md h2, .chat-md h3, .chat-md h4 { font-size: 0.95rem; font-weight: 700; margin: 10px 0 4px; }
                .chat-md code { background: rgba(51,177,176,0.12); padding: 1px 5px; border-radius: 5px; font-size: 0.85em; }
                .chat-md pre { background: rgba(31,45,61,0.06); padding: 10px 12px; border-radius: 8px; overflow-x: auto; margin: 6px 0; }
                .chat-md table { border-collapse: collapse; margin: 8px 0; width: 100%; }
                .chat-md th, .chat-md td { border: 1px solid rgba(51,177,176,0.25); padding: 5px 9px; text-align: left; font-size: 0.84rem; }
                .chat-md th { background: rgba(51,177,176,0.10); font-weight: 700; }
                .chat-md a { color: #2b8c8b; }
                .conv-item .conv-del { opacity: 0; transition: opacity 0.15s; }
                .conv-item:hover .conv-del { opacity: 1; }
                .cgpt-shell { display: flex; height: calc(100vh - 86px); margin: -24px -24px 0; }
                .attach-wrap { position: relative; display: inline-flex; }
                .attach-wrap .attach-tip {
                    position: absolute; bottom: 56px; left: 50%; transform: translateX(-50%);
                    background: #1f2d3d; color: #fff; font-size: 0.72rem; line-height: 1.3;
                    padding: 6px 10px; border-radius: 8px; white-space: nowrap; pointer-events: none;
                    opacity: 0; transition: opacity 0.15s; box-shadow: 0 4px 14px rgba(0,0,0,0.18); z-index: 20;
                }
                .attach-wrap .attach-tip::after {
                    content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
                    border: 5px solid transparent; border-top-color: #1f2d3d;
                }
                .attach-wrap:hover .attach-tip { opacity: 1; }
                .att-thumb { cursor: pointer; transition: transform 0.12s; }
                .att-thumb:hover { transform: scale(1.04); }
            `}</style>

            <div className="db-blob db-blob-1" />
            <div className="db-blob db-blob-2" />

            <NavBar activePage="chat" />

            <div className="cgpt-shell">
                {/* ── Sidebar (flush, full-height, ChatGPT-style) ── */}
                <aside style={{
                    width: 264, flexShrink: 0, height: '100%', boxSizing: 'border-box',
                    background: 'rgba(247, 250, 250, 0.92)',
                    borderRight: '1px solid rgba(60,61,63,0.10)',
                    display: 'flex', flexDirection: 'column', padding: '14px 10px',
                    position: 'relative', zIndex: 1,
                }}>
                    <button onClick={newChat} className="btn btn-primary" style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                        height: 42, borderRadius: 10, marginBottom: 16, fontWeight: 700, flexShrink: 0,
                    }}>＋ New Chat</button>

                    <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-secondary)',
                                  textTransform: 'uppercase', letterSpacing: '0.05em', padding: '0 8px 8px' }}>
                        📚 Library
                    </div>
                    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {conversations.length === 0 ? (
                            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', padding: '8px' }}>
                                No conversations yet.
                            </p>
                        ) : conversations.map(c => (
                            <div key={c.id} className="conv-item" onClick={() => openConversation(c.id)} style={{
                                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6,
                                padding: '9px 10px', borderRadius: 8, cursor: 'pointer',
                                background: c.id === activeId ? 'rgba(51,177,176,0.14)' : 'transparent',
                            }}
                                onMouseEnter={e => { if (c.id !== activeId) e.currentTarget.style.background = 'rgba(51,177,176,0.06)'; }}
                                onMouseLeave={e => { if (c.id !== activeId) e.currentTarget.style.background = 'transparent'; }}>
                                <span style={{ fontSize: '0.82rem', color: 'var(--text-primary)', overflow: 'hidden',
                                               textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                                    {c.title}
                                </span>
                                <button className="conv-del" onClick={(e) => removeConversation(c.id, e)} title="Delete"
                                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', fontSize: '0.85rem', padding: 2, flexShrink: 0 }}>🗑</button>
                            </div>
                        ))}
                    </div>
                </aside>

                {/* ── Main conversation pane ── */}
                <section style={{ flex: 1, height: '100%', display: 'flex', flexDirection: 'column',
                                  minWidth: 0, position: 'relative', zIndex: 1 }}>
                    {/* Messages scroll area */}
                    <div style={{ flex: 1, overflowY: 'auto', padding: '20px 0' }}>
                        {messages.length === 0 ? (
                            <div className="fade-in" style={{ maxWidth: COL_MAX, margin: '0 auto', padding: '40px 24px',
                                display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', minHeight: '60%' , justifyContent: 'center' }}>
                                <div style={{ fontSize: '2.6rem', marginBottom: 10 }}>🤖</div>
                                <h2 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: 6, color: '#1a1a1a' }}>ProdAI Assistant</h2>
                                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', maxWidth: 480, marginBottom: 28, lineHeight: 1.6 }}>
                                    Ask anything — grounded in your OEM manuals, incident history, and the web.
                                </p>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, width: '100%' }}>
                                    {SUGGESTED_PROMPTS.map((p, idx) => (
                                        <button key={idx} onClick={() => handleSend(p.text)} style={{
                                            background: 'rgba(51, 177, 176, 0.04)', border: '1.5px solid rgba(51, 177, 176, 0.20)',
                                            borderRadius: 12, padding: '14px', cursor: 'pointer', textAlign: 'left',
                                            display: 'flex', flexDirection: 'column', gap: 6 }}>
                                            <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: '#33B1B0', letterSpacing: '0.05em' }}>{p.label}</span>
                                            <span style={{ fontSize: '0.84rem', color: 'var(--text-primary)', fontWeight: 500, lineHeight: 1.4 }}>{p.text}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        ) : (
                            <div style={{ maxWidth: COL_MAX, margin: '0 auto', padding: '0 24px',
                                          display: 'flex', flexDirection: 'column', gap: 18 }}>
                                {error && (
                                    <div className="alert-error fade-in" style={{ padding: '10px 16px', borderRadius: 'var(--radius-sm)', fontSize: '0.82rem' }}>
                                        ⚠️ {error}
                                    </div>
                                )}
                                {messages.map((msg, idx) => (
                                    <div key={idx} className="fade-in" style={{ display: 'flex', flexDirection: 'column',
                                        alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                                        maxWidth: msg.role === 'user' ? '85%' : '100%',
                                        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                                        <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, padding: '0 4px' }}>
                                            {msg.role === 'user' ? 'You' : 'ProdAI Assistant'}
                                        </span>
                                        <div style={{
                                            background: msg.role === 'user' ? 'linear-gradient(135deg, #33B1B0, #2a9a99)' : 'rgba(51, 177, 176, 0.06)',
                                            color: msg.role === 'user' ? '#ffffff' : 'var(--text-primary)',
                                            border: msg.role === 'user' ? 'none' : '1px solid rgba(51, 177, 176, 0.18)',
                                            borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                                            padding: '14px 18px', fontSize: '0.9rem', lineHeight: 1.55,
                                            whiteSpace: msg.role === 'user' ? 'pre-wrap' : 'normal', wordBreak: 'break-word' }}>
                                            {msg.role === 'user' ? (
                                                <>
                                                    {msg.atts?.length > 0 && (
                                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: msg.content ? 8 : 0 }}>
                                                            {msg.atts.map((a, ai) => a.type === 'image' ? (
                                                                <img key={ai} src={a.data || a.url} alt={a.name} className="att-thumb"
                                                                     onClick={() => setPreview(a)}
                                                                     style={{ width: 120, height: 120, objectFit: 'cover', borderRadius: 10, border: '1px solid rgba(255,255,255,0.4)' }} />
                                                            ) : (
                                                                <span key={ai} onClick={() => setPreview(a)} className="att-thumb"
                                                                      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 12px',
                                                                               borderRadius: 10, background: 'rgba(255,255,255,0.18)', fontSize: '0.8rem' }}>
                                                                    📄 {a.name}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    )}
                                                    {msg.content}
                                                </>
                                            ) : <MarkdownBubble text={msg.content} />}
                                        </div>
                                        {msg.role === 'assistant' && <SourcesDropdown sources={msg.sources} />}
                                    </div>
                                ))}
                                {loading && (
                                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                                        <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4, padding: '0 4px' }}>ProdAI Assistant</span>
                                        <div style={{ background: 'rgba(51, 177, 176, 0.04)', border: '1px solid rgba(51, 177, 176, 0.12)',
                                            borderRadius: '16px 16px 16px 4px', padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 12,
                                            fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
                                            <span className="spinner" style={{ width: '16px', height: '16px', borderWidth: '2px',
                                                borderTopColor: '#33B1B0', borderLeftColor: 'transparent', borderRightColor: 'transparent',
                                                borderBottomColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
                                            <span>{statusText}</span>
                                        </div>
                                    </div>
                                )}
                                <div ref={chatEndRef} />
                            </div>
                        )}
                    </div>

                    {/* Composer (centered, pinned bottom) */}
                    <div style={{ borderTop: '1px solid rgba(60, 61, 63, 0.08)', background: 'rgba(255,255,255,0.55)',
                                  backdropFilter: 'blur(8px)', padding: '12px 24px 14px' }}>
                        <div style={{ maxWidth: COL_MAX, margin: '0 auto' }}>
                            {/* Attachment chips */}
                            {attachments.length > 0 && (
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                                    {attachments.map((a, i) => (
                                        <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 8,
                                            padding: '4px 8px 4px 6px', borderRadius: 10, fontSize: '0.76rem',
                                            background: 'rgba(51,177,176,0.10)', border: '1px solid rgba(51,177,176,0.25)', color: 'var(--text-primary)' }}>
                                            {a.type === 'image' ? (
                                                <img src={a.data} alt={a.name} className="att-thumb" onClick={() => setPreview(a)}
                                                     style={{ width: 34, height: 34, objectFit: 'cover', borderRadius: 6 }} />
                                            ) : (
                                                <span className="att-thumb" onClick={() => setPreview(a)} style={{ fontSize: '1.1rem' }}>📄</span>
                                            )}
                                            <span onClick={() => setPreview(a)} className="att-thumb" style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
                                            <button onClick={() => removeAttachment(i)} title="Remove"
                                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', fontWeight: 700, padding: 0 }}>✕</button>
                                        </span>
                                    ))}
                                </div>
                            )}
                            <form onSubmit={(e) => { e.preventDefault(); handleSend(inputText); }} style={{ display: 'flex', gap: 10 }}>
                                <input ref={fileInputRef} type="file" accept="image/*,application/pdf" multiple
                                       onChange={onPickFiles} style={{ display: 'none' }} />
                                <span className="attach-wrap">
                                    <span className="attach-tip">You can attach any image or PDF</span>
                                    <button type="button" onClick={() => fileInputRef.current?.click()} disabled={loading}
                                        className="btn btn-ghost"
                                        style={{ width: 48, height: 48, flexShrink: 0, borderRadius: 12, fontSize: '1.2rem',
                                                 display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}>📎</button>
                                </span>
                                <input type="text" className="form-input" value={inputText}
                                    onChange={(e) => setInputText(e.target.value)} disabled={loading}
                                    placeholder="Message ProdAI…"
                                    style={{ borderRadius: 12, height: 48, padding: '0 18px', background: 'rgba(255,255,255,0.9)', boxSizing: 'border-box', flex: 1 }} />
                                <button type="submit" className="btn btn-primary" disabled={loading || (!inputText.trim() && attachments.length === 0)}
                                    style={{ width: 'auto', height: 48, padding: '0 22px', borderRadius: 12, flexShrink: 0 }}>
                                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <span>Send</span>
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                            <line x1="22" y1="2" x2="11" y2="13"></line>
                                            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                                        </svg>
                                    </span>
                                </button>
                            </form>
                        </div>
                    </div>
                </section>
            </div>

            {/* Attachment preview lightbox */}
            {preview && (
                <div onClick={() => setPreview(null)} style={{
                    position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,0.72)',
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                    padding: 24, backdropFilter: 'blur(2px)',
                }}>
                    <div onClick={(e) => e.stopPropagation()} style={{
                        display: 'flex', flexDirection: 'column', maxWidth: '92vw', maxHeight: '92vh',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                      gap: 12, color: '#fff', marginBottom: 10 }}>
                            <span style={{ fontSize: '0.85rem', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {preview.type === 'pdf' ? '📄' : '🖼'} {preview.name}
                            </span>
                            <div style={{ display: 'flex', gap: 8 }}>
                                <a href={preview.data || preview.url} download={preview.name}
                                   onClick={(e) => e.stopPropagation()}
                                   style={{ color: '#fff', fontSize: '0.8rem', textDecoration: 'none',
                                            border: '1px solid rgba(255,255,255,0.4)', borderRadius: 8, padding: '4px 12px' }}>
                                    ⬇ Download
                                </a>
                                <button onClick={() => setPreview(null)}
                                    style={{ color: '#fff', background: 'none', border: '1px solid rgba(255,255,255,0.4)',
                                             borderRadius: 8, padding: '4px 12px', cursor: 'pointer', fontSize: '0.8rem' }}>✕ Close</button>
                            </div>
                        </div>
                        {preview.type === 'image' ? (
                            <img src={preview.data || preview.url} alt={preview.name}
                                 style={{ maxWidth: '92vw', maxHeight: '82vh', objectFit: 'contain', borderRadius: 10, background: '#fff' }} />
                        ) : (
                            <iframe title={preview.name} src={preview.data || preview.url}
                                    style={{ width: '88vw', height: '82vh', border: 'none', borderRadius: 10, background: '#fff' }} />
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default ChatPage;
