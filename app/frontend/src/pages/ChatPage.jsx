import React, { useState, useEffect, useRef } from 'react';
import NavBar from '../components/NavBar';
import { sendChatMessage } from '../api/chat';

const SUGGESTED_PROMPTS = [
    { text: "What is the correct vibration limit for a rotary kiln motor?", label: "Vibration limits" },
    { text: "Search manuals for lubrication procedures on kiln girth gears.", label: "Lubrication procedures" },
    { text: "Have we seen VFD overcurrent trips on Pellet 1 or DRI plants before?", label: "Historical trips" },
    { text: "Suggest corrective actions for a motor winding insulation failure.", label: "Winding failure CAPA" }
];

const ChatPage = () => {
    const [messages, setMessages] = useState([]);
    const [inputText, setInputText] = useState('');
    const [loading, setLoading] = useState(false);
    const [statusText, setStatusText] = useState('');
    const [error, setError] = useState(null);
    const chatEndRef = useRef(null);

    // Auto-scroll to bottom of chat
    const scrollToBottom = () => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, loading]);

    const handleSend = async (textToSend) => {
        const query = textToSend.trim();
        if (!query) return;

        setError(null);
        setInputText('');
        
        // Append user message
        const updatedMessages = [...messages, { role: 'user', content: query }];
        setMessages(updatedMessages);
        setLoading(true);
        setStatusText('Searching manuals and history...');

        // Micro-status timeline simulations
        const timer1 = setTimeout(() => setStatusText('Querying Weaviate RAG database...'), 600);
        const timer2 = setTimeout(() => setStatusText('Matching Neo4j knowledge graph...'), 1400);
        const timer3 = setTimeout(() => setStatusText('ProdAI is synthesizing grounded answer...'), 2200);

        try {
            const data = await sendChatMessage(updatedMessages);
            
            clearTimeout(timer1);
            clearTimeout(timer2);
            clearTimeout(timer3);

            if (data.status === 'success') {
                setMessages(prev => [
                    ...prev,
                    { 
                        role: 'assistant', 
                        content: data.reply,
                        has_rag: data.has_rag_context,
                        has_history: data.has_history_context
                    }
                ]);
            } else {
                throw new Error(data.message || 'Unknown response status');
            }
        } catch (err) {
            clearTimeout(timer1);
            clearTimeout(timer2);
            clearTimeout(timer3);
            console.error(err);
            setError(err.message || 'Failed to communicate with the AI assistant.');
        } finally {
            setLoading(false);
            setStatusText('');
        }
    };

    const handleClear = () => {
        setMessages([]);
        setError(null);
    };

    return (
        <div className="db-page">
            {/* Ambient Blobs */}
            <div className="db-blob db-blob-1" />
            <div className="db-blob db-blob-2" />

            <NavBar activePage="chat" />

            {/* Header section */}
            <div style={{ textAlign: 'center', margin: '-10px 0 10px', position: 'relative', zIndex: 1 }}>
                <h1 style={{ margin: 0, fontSize: '1.85rem', fontWeight: 800, color: '#1a1a1a', letterSpacing: '-0.01em' }}>
                    🤖 ProdAI Assistant
                </h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginTop: 4 }}>
                    Ask general maintenance questions, query OEM manuals (RAG) and historical incidents (Graph).
                </p>
            </div>

            <main className="db-main" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 190px)', minHeight: 480 }}>
                
                {/* Error Banner */}
                {error && (
                    <div className="alert-error fade-in" style={{ padding: '12px 20px', borderRadius: 'var(--radius-sm)', marginBottom: 12 }}>
                        ⚠️ {error}
                    </div>
                )}

                {/* Main Dialogue Panel */}
                <div className="glass-card" style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    overflow: 'hidden',
                    position: 'relative',
                    padding: '24px 28px',
                    boxSizing: 'border-box'
                }}>
                    
                    {/* Chat container */}
                    <div style={{
                        flex: 1,
                        overflowY: 'auto',
                        paddingRight: 8,
                        marginBottom: 20,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 16
                    }}>
                        {messages.length === 0 ? (
                            <div className="fade-in" style={{
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                justifyContent: 'center',
                                height: '100%',
                                textAlign: 'center',
                                padding: '40px 20px',
                                boxSizing: 'border-box'
                            }}>
                                <div style={{ fontSize: '3rem', marginBottom: 16 }}>💬</div>
                                <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: 8 }}>Welcome to ProdAI Chat</h3>
                                <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', maxWidth: 460, marginBottom: 32, lineHeight: 1.6 }}>
                                    Type a question below to search manuals and logs, or select one of the suggested prompts to get started:
                                </p>
                                
                                {/* Suggested prompt grids */}
                                <div style={{
                                    display: 'grid',
                                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                                    gap: 12,
                                    width: '100%',
                                    maxWidth: 750
                                }}>
                                    {SUGGESTED_PROMPTS.map((p, idx) => (
                                        <button
                                            key={idx}
                                            onClick={() => handleSend(p.text)}
                                            style={{
                                                background: 'rgba(51, 177, 176, 0.04)',
                                                border: '1.5px solid rgba(51, 177, 176, 0.20)',
                                                borderRadius: 12,
                                                padding: '16px',
                                                cursor: 'pointer',
                                                textAlign: 'left',
                                                transition: 'all 0.2s ease-in-out',
                                                display: 'flex',
                                                flexDirection: 'column',
                                                gap: 6
                                            }}
                                            onMouseEnter={e => {
                                                e.currentTarget.style.background = 'rgba(51, 177, 176, 0.08)';
                                                e.currentTarget.style.borderColor = '#33B1B0';
                                                e.currentTarget.style.transform = 'translateY(-2px)';
                                            }}
                                            onMouseLeave={e => {
                                                e.currentTarget.style.background = 'rgba(51, 177, 176, 0.04)';
                                                e.currentTarget.style.borderColor = 'rgba(51, 177, 176, 0.20)';
                                                e.currentTarget.style.transform = 'none';
                                            }}
                                        >
                                            <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: '#33B1B0', letterSpacing: '0.05em' }}>
                                                {p.label}
                                            </span>
                                            <span style={{ fontSize: '0.84rem', color: 'var(--text-primary)', fontWeight: 500, lineHeight: 1.4 }}>
                                                {p.text}
                                            </span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        ) : (
                            messages.map((msg, idx) => (
                                <div
                                    key={idx}
                                    className="fade-in"
                                    style={{
                                        display: 'flex',
                                        flexDirection: 'column',
                                        alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                                        maxWidth: '85%',
                                        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                                        animationDelay: `${idx * 0.05}s`
                                    }}
                                >
                                    {/* Sender Label */}
                                    <span style={{
                                        fontSize: '0.72rem',
                                        fontWeight: 600,
                                        color: 'var(--text-secondary)',
                                        marginBottom: 4,
                                        padding: '0 4px'
                                    }}>
                                        {msg.role === 'user' ? 'You' : 'ProdAI Assistant'}
                                    </span>

                                    {/* Message Bubble */}
                                    <div style={{
                                        background: msg.role === 'user' 
                                            ? 'linear-gradient(135deg, #33B1B0, #2a9a99)' 
                                            : 'rgba(51, 177, 176, 0.06)',
                                        color: msg.role === 'user' ? '#ffffff' : 'var(--text-primary)',
                                        border: msg.role === 'user' ? 'none' : '1px solid rgba(51, 177, 176, 0.18)',
                                        borderRadius: msg.role === 'user' 
                                            ? '16px 16px 4px 16px' 
                                            : '16px 16px 16px 4px',
                                        padding: '14px 18px',
                                        boxShadow: '0 4px 16px rgba(0,0,0,0.02)',
                                        fontSize: '0.9rem',
                                        lineHeight: 1.55,
                                        whiteSpace: 'pre-wrap',
                                        wordBreak: 'break-word'
                                    }}>
                                        {msg.content}
                                    </div>

                                    {/* Source Attributions Badges for Assistant replies */}
                                    {msg.role === 'assistant' && (msg.has_rag || msg.has_history) && (
                                        <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                                            {msg.has_rag && (
                                                <span className="category-tag" style={{ background: 'rgba(51, 177, 176, 0.10)', color: '#33B1B0', border: '1px solid rgba(51, 177, 176, 0.25)', borderRadius: 99, padding: '2px 10px', fontSize: '0.7rem', fontWeight: 700 }}>
                                                    📖 OEM manuals referenced
                                                </span>
                                            )}
                                            {msg.has_history && (
                                                <span className="category-tag" style={{ background: 'rgba(249, 115, 22, 0.08)', color: '#f97316', border: '1px solid rgba(249, 115, 22, 0.25)', borderRadius: 99, padding: '2px 10px', fontSize: '0.7rem', fontWeight: 700 }}>
                                                    📜 Incident history matched
                                                </span>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))
                        )}

                        {/* Loading / Retrieval Status */}
                        {loading && (
                            <div style={{
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'flex-start',
                                alignSelf: 'flex-start',
                                maxWidth: '85%'
                            }}>
                                <span style={{
                                    fontSize: '0.72rem',
                                    fontWeight: 600,
                                    color: 'var(--text-secondary)',
                                    marginBottom: 4,
                                    padding: '0 4px'
                                }}>
                                    ProdAI Assistant
                                </span>
                                
                                <div style={{
                                    background: 'rgba(51, 177, 176, 0.04)',
                                    border: '1px solid rgba(51, 177, 176, 0.12)',
                                    borderRadius: '16px 16px 16px 4px',
                                    padding: '14px 18px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 12,
                                    fontSize: '0.88rem',
                                    color: 'var(--text-secondary)'
                                }}>
                                    <span className="spinner" style={{
                                        width: '16px',
                                        height: '16px',
                                        borderWidth: '2px',
                                        borderTopColor: '#33B1B0',
                                        borderLeftColor: 'transparent',
                                        borderRightColor: 'transparent',
                                        borderBottomColor: 'transparent',
                                        animation: 'spin 0.8s linear infinite'
                                    }} />
                                    <span>{statusText}</span>
                                </div>
                            </div>
                        )}

                        <div ref={chatEndRef} />
                    </div>

                    {/* Bottom controls & input row */}
                    <div style={{
                        borderTop: '1px solid rgba(60, 61, 63, 0.08)',
                        paddingTop: 18,
                        display: 'flex',
                        gap: 12,
                        alignItems: 'center'
                    }}>
                        {/* Clear button */}
                        {messages.length > 0 && (
                            <button
                                type="button"
                                className="btn btn-ghost"
                                onClick={handleClear}
                                title="Clear conversation"
                                style={{
                                    padding: '12px',
                                    width: 46,
                                    height: 46,
                                    flexShrink: 0,
                                    borderRadius: 10,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                }}
                            >
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <polyline points="3 6 5 6 21 6"></polyline>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                    <line x1="10" y1="11" x2="10" y2="17"></line>
                                    <line x1="14" y1="11" x2="14" y2="17"></line>
                                </svg>
                            </button>
                        )}

                        {/* Text Field Form */}
                        <form
                            onSubmit={(e) => { e.preventDefault(); handleSend(inputText); }}
                            style={{ flex: 1, display: 'flex', gap: 12 }}
                        >
                            <input
                                type="text"
                                className="form-input"
                                value={inputText}
                                onChange={(e) => setInputText(e.target.value)}
                                disabled={loading}
                                placeholder="Type your maintenance query or equipment issue here..."
                                style={{
                                    borderRadius: 10,
                                    height: 46,
                                    padding: '0 16px',
                                    background: 'rgba(255,255,255,0.7)',
                                    boxSizing: 'border-box'
                                }}
                            />
                            
                            <button
                                type="submit"
                                className="btn btn-primary"
                                disabled={loading || !inputText.trim()}
                                style={{
                                    width: 'auto',
                                    height: 46,
                                    padding: '0 20px',
                                    borderRadius: 10,
                                    flexShrink: 0
                                }}
                            >
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
            </main>
        </div>
    );
};

export default ChatPage;
