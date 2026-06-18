import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import NavBar from '../components/NavBar';
import { fetchEquipmentList } from '../api/equipment';
import { fetchBreakdowns } from '../api/dashboard';

const NODE_POSITIONS = {
    'Vibro Feeder': { x: 40, y: 70, icon: '📥', label: 'Vibro Feeder' },
    'Scrubber': { x: 190, y: 70, icon: '🌀', label: 'Scrubber' },
    'Primary Ball Mill': { x: 340, y: 70, icon: '⚙️', label: 'Primary Ball Mill' },
    'DD Screen': { x: 490, y: 70, icon: '🏁', label: 'DD Screen' },
    'Slurry Pump': { x: 490, y: 270, icon: '⛽', label: 'Slurry Pump' },
    'Cyclone Cluster': { x: 640, y: 170, icon: '🌪️', label: 'Cyclone Cluster' },
    'Secondary Ball Mill': { x: 340, y: 270, icon: '⚙️', label: 'Sec. Ball Mill' },
    'HGMS': { x: 790, y: 70, icon: '🧲', label: 'HGMS Separator' },
    'Stack sizer': { x: 790, y: 220, icon: '📐', label: 'Stack Sizer' },
    'HT Thickener': { x: 790, y: 370, icon: '🛢️', label: 'HT Thickener' },
    'FilterPress': { x: 640, y: 370, icon: '📦', label: 'Filter Press' },
};

const PIPELINES = [
    { from: 'Vibro Feeder', to: 'Scrubber', points: '160,115 190,115' },
    { from: 'Scrubber', to: 'Primary Ball Mill', points: '310,115 340,115' },
    { from: 'Primary Ball Mill', to: 'DD Screen', points: '460,115 490,115' },
    // Undersize to Slurry Pump
    { from: 'DD Screen', to: 'Slurry Pump', points: '550,160 550,270' },
    // Oversize to Secondary Ball Mill (return/regrind loop)
    { from: 'DD Screen', to: 'Secondary Ball Mill', points: '610,115 625,115 625,40 400,40 400,270' },
    // Pump to Cyclone Cluster
    { from: 'Slurry Pump', to: 'Cyclone Cluster', points: '610,315 625,315 625,215 640,215' },
    // Cyclone Underflow (coarse) to Secondary Ball Mill
    { from: 'Cyclone Cluster', to: 'Secondary Ball Mill', points: '640,215 625,215 625,330 460,330' },
    // Secondary Ball Mill back to Slurry Pump
    { from: 'Secondary Ball Mill', to: 'Slurry Pump', points: '460,315 490,315' },
    // Cyclone Overflow (fine) split to HGMS and Stack Sizer
    { from: 'Cyclone Cluster', to: 'HGMS', points: '760,215 775,215 775,115 790,115' },
    { from: 'Cyclone Cluster', to: 'Stack sizer', points: '760,215 775,215 775,265 790,265' },
    // Concentrate to Thickener
    { from: 'HGMS', to: 'HT Thickener', points: '910,115 925,115 925,415 910,415' },
    { from: 'Stack sizer', to: 'HT Thickener', points: '910,265 925,265 925,415 910,415' },
    // Thickener to FilterPress
    { from: 'HT Thickener', to: 'FilterPress', points: '790,415 760,415' },
];

const BeneficiationPFDPage = () => {
    const navigate = useNavigate();
    const [equipmentData, setEquipmentData] = useState([]);
    const [breakdowns, setBreakdowns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [selectedEquip, setSelectedEquip] = useState(null);
    const [detailBreakdowns, setDetailBreakdowns] = useState([]);
    const [detailLoading, setDetailLoading] = useState(false);

    useEffect(() => {
        const loadPFDData = async () => {
            try {
                setLoading(true);
                const [eqList, bdList] = await Promise.all([
                    fetchEquipmentList(),
                    fetchBreakdowns({ plant: 'BNFC' })
                ]);
                
                // Filter for BNFC plant
                const bnfcEq = eqList.filter(e => e.category === 'BNFC');
                setEquipmentData(bnfcEq);
                setBreakdowns(bdList);
                setError('');
            } catch (err) {
                console.error(err);
                setError('Failed to load real-time PFD metrics.');
            } finally {
                setLoading(false);
            }
        };

        loadPFDData();
        const interval = setInterval(loadPFDData, 30000); // refresh every 30s
        return () => clearInterval(interval);
    }, []);

    // Helper to find stats and status for a node
    const getNodeStats = (name) => {
        const eq = equipmentData.find(e => e.name.toLowerCase() === name.toLowerCase()) || {};
        
        // Find if there is an active breakdown on this equipment (Open or In Progress)
        const activeBDs = breakdowns.filter(
            b => b.equipment_name && b.equipment_name.toLowerCase() === name.toLowerCase() && 
            (b.status === 'Open' || b.status === 'In Progress')
        );
        
        return {
            id: eq.id || null,
            assetTag: eq.asset_tag || 'EQ-xxxx',
            health: eq.asset_health_score ?? 100,
            failures: eq.failure_count ?? 0,
            lastFailure: eq.last_failure_date ? new Date(eq.last_failure_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) : 'None',
            criticality: eq.criticality || 'Medium',
            hasActiveBreakdown: activeBDs.length > 0,
            activeBreakdowns: activeBDs
        };
    };

    const handleNodeClick = async (name) => {
        const stats = getNodeStats(name);
        if (!stats.id) return;
        
        setSelectedEquip({ name, ...stats });
        setDetailLoading(true);
        setDetailBreakdowns([]);
        
        try {
            // Fetch comprehensive equipment detail including components and breakdown history
            const resp = await fetch(`/api/equipment/${stats.id}`, { credentials: 'include' });
            if (resp.ok) {
                const detail = await resp.json();
                setSelectedEquip(prev => ({
                    ...prev,
                    components: detail.components || [],
                    location: detail.location || 'BNFC Plant',
                }));
                setDetailBreakdowns(detail.breakdowns || []);
            }
        } catch (err) {
            console.error('Failed to load details', err);
        } finally {
            setDetailLoading(false);
        }
    };

    const handleQuickLog = () => {
        if (!selectedEquip) return;
        navigate('/log-breakdown', { 
            state: { 
                equipmentId: selectedEquip.id, 
                division: 'BNFC' 
            } 
        });
    };

    return (
        <div className="db-page" style={{ background: '#0B0F19', color: '#E2E8F0', minHeight: '100vh', overflowX: 'hidden' }}>
            {/* Dark background grids */}
            <div style={{
                position: 'fixed', inset: 0,
                backgroundImage: 'radial-gradient(rgba(51, 177, 176, 0.08) 1.5px, transparent 1.5px), radial-gradient(rgba(51, 177, 176, 0.04) 1.5px, transparent 1.5px)',
                backgroundSize: '32px 32px', backgroundPosition: '0 0, 16px 16px',
                pointerEvents: 'none', zIndex: 0
            }} />

            <NavBar activePage="plant-pfd" />

            <div className="bl-hero fade-in" style={{ maxWidth: 1400, margin: '0 auto 20px', zIndex: 1, position: 'relative', borderBottom: '1px solid rgba(51, 177, 176, 0.15)', paddingBottom: 15 }}>
                <div className="bl-hero-icon" style={{ textShadow: '0 0 15px rgba(51, 177, 176, 0.5)' }}>🖥️</div>
                <div style={{ flex: 1 }}>
                    <h1 className="bl-hero-title" style={{ color: '#F1F5F9' }}>Beneficiation Process Flow Diagram</h1>
                    <p className="bl-hero-sub" style={{ color: '#94A3B8' }}>Interactive mimic panel displaying real-time equipment status, health, and breakdown tracking.</p>
                </div>
                {loading && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span className="spinner" style={{ borderTopColor: '#33B1B0', width: 18, height: 18, borderWidth: 2 }} />
                        <span style={{ fontSize: '0.85rem', color: '#94A3B8' }}>Polling metrics...</span>
                    </div>
                )}
            </div>

            {error && (
                <div className="bl-banner bl-error fade-in" style={{ maxWidth: 1400, margin: '10px auto', zIndex: 1, position: 'relative' }}>
                    ⚠️ {error}
                </div>
            )}

            {/* PFD Control Room Main Area */}
            <div style={{
                maxWidth: 1400, width: '100%', margin: '0 auto', display: 'flex',
                gap: 20, zIndex: 1, position: 'relative', height: 'calc(100vh - 220px)',
                minHeight: 650
            }} className="fade-in">
                {/* SVG Mimic Mimic Diagram Card */}
                <div className="glass-card" style={{
                    flex: 1, display: 'flex', flexDirection: 'column', background: 'rgba(15, 23, 42, 0.85)',
                    border: '1px solid rgba(51, 177, 176, 0.2)', padding: 15, position: 'relative', overflow: 'hidden',
                    borderRadius: 16, boxShadow: '0 12px 40px rgba(0,0,0,0.5)'
                }}>
                    {/* Header Legend */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12, borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: 8 }}>
                        <div style={{ fontSize: '0.82rem', color: '#94A3B8', fontWeight: 600 }}>BNFC MIMIC OVERVIEW</div>
                        <div style={{ display: 'flex', gap: 16, fontSize: '0.78rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10B981', boxShadow: '0 0 8px #10B981' }} />
                                <span>Normal / Running</span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#EF4444', animation: 'ping 1.5s infinite', boxShadow: '0 0 10px #EF4444' }} />
                                <span>Active Breakdown</span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                <span style={{ display: 'inline-block', width: 12, height: 2, borderTop: '2px dashed #10B981' }} />
                                <span>Feed Flow</span>
                            </div>
                        </div>
                    </div>

                    {/* Interactive Mimic View */}
                    <div style={{ flex: 1, position: 'relative', width: '100%', maxWidth: 950, height: '100%', alignSelf: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <svg viewBox="0 0 950 480" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style={{ pointerEvents: 'all' }}>
                            <defs>
                                <linearGradient id="normalGrad" x1="0" y1="0" x2="1" y2="1">
                                    <stop offset="0%" stopColor="#1E293B" />
                                    <stop offset="100%" stopColor="#0F172A" />
                                </linearGradient>
                                <linearGradient id="alertGrad" x1="0" y1="0" x2="1" y2="1">
                                    <stop offset="0%" stopColor="#2D1212" />
                                    <stop offset="100%" stopColor="#1C0808" />
                                </linearGradient>
                            </defs>

                            {/* Render Pipelines */}
                            {PIPELINES.map((pipe, i) => {
                                const fromStats = getNodeStats(pipe.from);
                                const toStats = getNodeStats(pipe.to);
                                const isBroken = fromStats.hasActiveBreakdown || toStats.hasActiveBreakdown;
                                
                                return (
                                    <g key={i}>
                                        <polyline
                                            points={pipe.points}
                                            fill="none"
                                            stroke={isBroken ? '#EF4444' : '#10B981'}
                                            strokeWidth={isBroken ? 4 : 3}
                                            strokeOpacity={isBroken ? 0.9 : 0.6}
                                            strokeDasharray={isBroken ? '6,6' : '8,8'}
                                            style={{
                                                animation: isBroken 
                                                    ? 'flow-animation-broken 0.8s linear infinite' 
                                                    : 'flow-animation-normal 1.5s linear infinite',
                                            }}
                                        />
                                        {/* Background thicker glow lines */}
                                        <polyline
                                            points={pipe.points}
                                            fill="none"
                                            stroke={isBroken ? '#EF4444' : '#10B981'}
                                            strokeWidth={isBroken ? 8 : 6}
                                            strokeOpacity="0.12"
                                        />
                                    </g>
                                );
                            })}

                            {/* Render Node Cards inside SVG using foreignObject */}
                            {Object.entries(NODE_POSITIONS).map(([name, pos]) => {
                                const stats = getNodeStats(name);
                                const isSelected = selectedEquip && selectedEquip.name === name;
                                
                                return (
                                    <foreignObject
                                        key={name}
                                        x={pos.x}
                                        y={pos.y}
                                        width="120"
                                        height="90"
                                        style={{ overflow: 'visible', cursor: 'pointer' }}
                                        onClick={() => handleNodeClick(name)}
                                    >
                                        <div style={{
                                            width: 120, height: 90, borderRadius: 10,
                                            background: stats.hasActiveBreakdown ? 'url(#alertGrad)' : 'url(#normalGrad)',
                                            border: isSelected 
                                                ? '2px solid #33B1B0' 
                                                : (stats.hasActiveBreakdown 
                                                    ? '1.5px solid #EF4444' 
                                                    : '1.5px solid rgba(51, 177, 176, 0.25)'),
                                            boxShadow: stats.hasActiveBreakdown 
                                                ? '0 0 16px rgba(239, 68, 68, 0.45)' 
                                                : (isSelected ? '0 0 16px rgba(51, 177, 176, 0.4)' : '0 4px 10px rgba(0,0,0,0.3)'),
                                            padding: '8px 10px', display: 'flex', flexDirection: 'column',
                                            justifyContent: 'space-between', boxSizing: 'border-box',
                                            transition: 'all 0.25s ease', position: 'relative',
                                            transform: isSelected ? 'scale(1.05)' : 'none',
                                            userSelect: 'none'
                                        }}
                                        onMouseEnter={(e) => {
                                            if (!isSelected) {
                                                e.currentTarget.style.borderColor = 'rgba(51, 177, 176, 0.8)';
                                                e.currentTarget.style.transform = 'translateY(-2px)';
                                            }
                                        }}
                                        onMouseLeave={(e) => {
                                            if (!isSelected) {
                                                e.currentTarget.style.borderColor = stats.hasActiveBreakdown ? '#EF4444' : 'rgba(51, 177, 176, 0.25)';
                                                e.currentTarget.style.transform = 'none';
                                            }
                                        }}
                                        >
                                            {/* Flashing Alert Badge */}
                                            {stats.hasActiveBreakdown && (
                                                <div style={{
                                                    position: 'absolute', top: -8, left: '50%', transform: 'translateX(-50%)',
                                                    background: '#EF4444', color: '#fff', fontSize: '0.62rem', fontWeight: 800,
                                                    padding: '2px 6px', borderRadius: 99, display: 'flex', alignItems: 'center', gap: 2,
                                                    whiteSpace: 'nowrap', boxShadow: '0 2px 5px rgba(239,68,68,0.4)',
                                                    animation: 'pulse 1s ease-in-out infinite alternate'
                                                }}>
                                                    ⚠️ FAIL
                                                </div>
                                            )}

                                            {/* Top info row */}
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 4 }}>
                                                <span style={{ fontSize: '1rem' }}>{pos.icon}</span>
                                                <span style={{ fontSize: '0.65rem', color: '#94A3B8', fontWeight: 700, letterSpacing: '0.02em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                    {stats.assetTag}
                                                </span>
                                            </div>

                                            {/* Name */}
                                            <div style={{
                                                fontSize: '0.74rem', fontWeight: 700, color: stats.hasActiveBreakdown ? '#FCA5A5' : '#E2E8F0',
                                                lineHeight: 1.1, textAlign: 'center', margin: '4px 0', overflow: 'hidden',
                                                textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical'
                                            }}>
                                                {pos.label}
                                            </div>

                                            {/* Bottom status row */}
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.62rem', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 4 }}>
                                                <span style={{ color: '#94A3B8' }}>F: <strong style={{ color: stats.failures > 0 ? '#fb923c' : '#94A3B8' }}>{stats.failures}</strong></span>
                                                <span style={{
                                                    color: stats.health > 85 ? '#10B981' : (stats.health > 60 ? '#F59E0B' : '#EF4444'),
                                                    fontWeight: 800
                                                }}>
                                                    H: {stats.health}%
                                                </span>
                                            </div>
                                        </div>
                                    </foreignObject>
                                );
                            })}
                        </svg>
                    </div>
                </div>

                {/* Right Details Sidebar Panel */}
                <div style={{
                    width: 380, display: 'flex', flexDirection: 'column', gap: 15,
                    height: '100%', pointerEvents: 'all'
                }}>
                    {selectedEquip ? (
                        <div className="glass-card" style={{
                            flex: 1, display: 'flex', flexDirection: 'column', background: 'rgba(15, 23, 42, 0.85)',
                            border: '1.5px solid rgba(51, 177, 176, 0.3)', padding: 20, borderRadius: 16,
                            boxShadow: '0 8px 32px rgba(0,0,0,0.5)', overflowY: 'auto'
                        }}>
                            {/* Panel Header */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: 15, marginBottom: 15 }}>
                                <div>
                                    <span style={{ background: '#33B1B0', color: '#0B0F19', fontSize: '0.68rem', fontWeight: 800, padding: '2px 8px', borderRadius: 99 }}>
                                        {selectedEquip.assetTag}
                                    </span>
                                    <h2 style={{ fontSize: '1.2rem', fontWeight: 800, marginTop: 6, color: '#F8FAFC' }}>
                                        {selectedEquip.name}
                                    </h2>
                                </div>
                                <button
                                    onClick={() => setSelectedEquip(null)}
                                    className="btn btn-ghost"
                                    style={{ padding: '4px 10px', fontSize: '0.9rem', color: '#94A3B8', minWidth: 0, borderRadius: 8 }}
                                >✕</button>
                            </div>

                            {/* Health Indicator Circle */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 16, background: 'rgba(255,255,255,0.03)', padding: 12, borderRadius: 12, border: '1px solid rgba(255,255,255,0.05)', marginBottom: 15 }}>
                                <div style={{
                                    width: 54, height: 54, borderRadius: '50%', border: '4px solid #1E293B',
                                    borderTopColor: selectedEquip.health > 85 ? '#10B981' : (selectedEquip.health > 60 ? '#F59E0B' : '#EF4444'),
                                    display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: '0.95rem',
                                    color: selectedEquip.health > 85 ? '#10B981' : (selectedEquip.health > 60 ? '#F59E0B' : '#EF4444'),
                                    boxShadow: selectedEquip.health > 85 ? '0 0 10px rgba(16,185,129,0.2)' : 'none'
                                }}>
                                    {selectedEquip.health}%
                                </div>
                                <div style={{ flex: 1 }}>
                                    <div style={{ fontSize: '0.65rem', color: '#94A3B8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Asset Condition</div>
                                    <div style={{ fontSize: '0.86rem', fontWeight: 700, color: selectedEquip.health > 85 ? '#34D399' : (selectedEquip.health > 60 ? '#FBBF24' : '#F87171') }}>
                                        {selectedEquip.health > 85 ? 'Optimal Health' : (selectedEquip.health > 60 ? 'Degraded Performance' : 'Urgent Intervention')}
                                    </div>
                                </div>
                            </div>

                            {/* Details list */}
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px', marginBottom: 20 }}>
                                {[
                                    { label: 'Plant Location', value: selectedEquip.location || 'Beneficiation' },
                                    { label: 'Criticality', value: <span style={{ color: selectedEquip.criticality === 'Critical' ? '#F87171' : (selectedEquip.criticality === 'High' ? '#FBBF24' : '#E2E8F0'), fontWeight: 700 }}>{selectedEquip.criticality}</span> },
                                    { label: 'Total Failures', value: <strong style={{ color: '#E2E8F0', fontSize: '1rem' }}>{selectedEquip.failures}</strong> },
                                    { label: 'Last Breakdown', value: selectedEquip.lastFailure },
                                ].map(({ label, value }) => (
                                    <div key={label}>
                                        <p style={{ fontSize: '0.65rem', fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>{label}</p>
                                        <div style={{ fontSize: '0.84rem', color: '#E2E8F0' }}>{value}</div>
                                    </div>
                                ))}
                            </div>

                            {/* Active breakdown warning box */}
                            {selectedEquip.hasActiveBreakdown && (
                                <div style={{
                                    background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)',
                                    borderRadius: 12, padding: 12, marginBottom: 20, animation: 'pulse-red-border 1.5s infinite'
                                }}>
                                    <h4 style={{ margin: '0 0 6px', color: '#FCA5A5', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700 }}>
                                        🚨 ACTIVE OUTAGE DETECTED
                                    </h4>
                                    {selectedEquip.activeBreakdowns.map((bd, index) => (
                                        <p key={index} style={{ margin: 0, fontSize: '0.76rem', color: '#E2E8F0', lineHeight: 1.4 }}>
                                            {bd.description || 'No description recorded.'}
                                        </p>
                                    ))}
                                </div>
                            )}

                            {/* Components list */}
                            <div style={{ marginBottom: 20 }}>
                                <p style={{ fontSize: '0.72rem', fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
                                    Sub-Equipment Components
                                </p>
                                {(!selectedEquip.components || selectedEquip.components.length === 0) ? (
                                    <p style={{ fontSize: '0.78rem', color: '#64748B', fontStyle: 'italic', margin: 0 }}>
                                        No components defined.
                                    </p>
                                ) : (
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                        {selectedEquip.components.map(comp => (
                                            <span key={comp.id} style={{
                                                padding: '3px 8px', borderRadius: 6, fontSize: '0.7rem',
                                                fontWeight: 600, color: '#33B1B0',
                                                background: 'rgba(51, 177, 176, 0.06)',
                                                border: '1px solid rgba(51, 177, 176, 0.15)'
                                            }}>
                                                ⚙️ {comp.name}
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Recent breakdown history list */}
                            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 180 }}>
                                <p style={{ fontSize: '0.72rem', fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
                                    Breakdown Log History
                                </p>
                                {detailLoading ? (
                                    <div className="skeleton" style={{ height: 60, borderRadius: 8, background: '#1E293B' }} />
                                ) : (detailBreakdowns.length === 0) ? (
                                    <p style={{ fontSize: '0.78rem', color: '#64748B', fontStyle: 'italic', margin: 0 }}>
                                        No incident history records.
                                    </p>
                                ) : (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto', flex: 1, maxHeight: 240, paddingRight: 4 }}>
                                        {detailBreakdowns.map(b => (
                                            <div key={b.id} style={{
                                                padding: '10px', background: 'rgba(255,255,255,0.02)',
                                                border: '1px solid rgba(255,255,255,0.04)', borderRadius: 8
                                            }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                                    <span style={{ fontSize: '0.68rem', fontWeight: 700, color: b.severity_level === 'Critical' ? '#EF4444' : '#F59E0B' }}>
                                                        {b.severity_level || 'Medium'}
                                                    </span>
                                                    <span style={{ fontSize: '0.62rem', color: '#64748B' }}>
                                                        {new Date(b.reported_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' })}
                                                    </span>
                                                </div>
                                                <p style={{ margin: 0, fontSize: '0.74rem', color: '#CBCFD4', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={b.description}>
                                                    {b.description || 'No details.'}
                                                </p>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Sidebar Quick Actions */}
                            <div style={{ marginTop: 'auto', paddingTop: 15, borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', gap: 10 }}>
                                <button
                                    onClick={handleQuickLog}
                                    className="btn btn-primary"
                                    style={{ flex: 1, padding: '8px 12px', fontSize: '0.78rem', background: '#33B1B0', color: '#0B0F19', border: 'none' }}
                                >
                                    Log Failure
                                </button>
                                <button
                                    onClick={() => navigate('/equipment')}
                                    className="btn btn-ghost"
                                    style={{ flex: 1, padding: '8px 12px', fontSize: '0.78rem', color: '#E2E8F0', border: '1px solid rgba(255,255,255,0.1)' }}
                                >
                                    Asset Master
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="glass-card" style={{
                            flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                            background: 'rgba(15, 23, 42, 0.85)', border: '1px solid rgba(51, 177, 176, 0.12)',
                            padding: 24, borderRadius: 16, textAlign: 'center', color: '#64748B'
                        }}>
                            <div style={{ fontSize: '2.5rem', marginBottom: 12 }}>🏭</div>
                            <h3 style={{ margin: '0 0 6px', color: '#94A3B8', fontSize: '0.95rem', fontWeight: 700 }}>
                                Equipment Detail
                            </h3>
                            <p style={{ margin: 0, fontSize: '0.78rem', lineHeight: 1.4 }}>
                                Select any equipment node on the mimic diagram to view its active health index, criticality, components, and breakdown log logs.
                            </p>
                        </div>
                    )}
                </div>
            </div>

            {/* Custom Embedded CSS Styles for animations */}
            <style>{`
                @keyframes flow-animation-normal {
                    to {
                        stroke-dashoffset: -28;
                    }
                }
                @keyframes flow-animation-broken {
                    to {
                        stroke-dashoffset: -16;
                    }
                }
                @keyframes pulse-red-border {
                    0% { border-color: rgba(239, 68, 68, 0.2); }
                    50% { border-color: rgba(239, 68, 68, 0.6); }
                    100% { border-color: rgba(239, 68, 68, 0.2); }
                }
                @keyframes pulse {
                    0% { opacity: 0.85; transform: translateX(-50%) scale(0.95); }
                    100% { opacity: 1; transform: translateX(-50%) scale(1.05); }
                }
            `}</style>
        </div>
    );
};

export default BeneficiationPFDPage;
