import { useState, useRef, useEffect } from 'react'

// ─── Evidence metadata ───────────────────────────────────────────────────────
const EVIDENCE_META = {
    CONFIRMED: { color: '#34d399', bg: 'rgba(52,211,153,0.15)', border: 'rgba(52,211,153,0.5)', priority: 3, posRatio: 0.28 },
    SUPPORTED: { color: '#4a7cff', bg: 'rgba(74,124,255,0.15)', border: 'rgba(74,124,255,0.5)', priority: 2, posRatio: 0.54 },
    POSSIBLE: { color: '#fbbf24', bg: 'rgba(251,191,36,0.15)', border: 'rgba(251,191,36,0.5)', priority: 1, posRatio: 0.78 },
    EFFECT: { color: '#6b7280', bg: 'rgba(107,114,128,0.12)', border: 'rgba(107,114,128,0.4)', priority: 0, posRatio: null },
}

// ─── Category layout (top vs bottom rows) ────────────────────────────────────
const TOP_CATS = ['Machine', 'Material', 'Environment']
const BOTTOM_CATS = ['Method', 'Man', 'Measurement']
const CAT_ICONS = {
    Machine: '⚙️', Material: '📦', Environment: '🌡️',
    Method: '📋', Man: '👷', Measurement: '📊',
}

// ─── Text wrap helper (SVG foreignObject for multi-line text in rect) ─────────
function LeafNode({ x, y, cause, level, isActive, isDimmed, onClick, onMouseEnter, onMouseLeave }) {
    const meta = EVIDENCE_META[level] || EVIDENCE_META.POSSIBLE
    const w = 140
    const h = 52
    const left = x - w / 2
    const top = y - h / 2
    const opac = isDimmed ? 0.25 : 1

    return (
        <g
            className={`leaf-node ${isActive ? 'leaf-active' : ''}`}
            style={{ cursor: 'pointer', opacity: opac, transition: 'opacity 0.25s' }}
            onClick={onClick}
            onMouseEnter={onMouseEnter}
            onMouseLeave={onMouseLeave}
        >
            <rect
                x={left} y={top} width={w} height={h}
                rx={8} ry={8}
                fill={meta.bg}
                stroke={isActive ? meta.color : meta.border}
                strokeWidth={isActive ? 2 : 1}
                filter={isActive ? 'drop-shadow(0 0 6px ' + meta.color + '88)' : undefined}
            />
            {/* Evidence label pill */}
            <rect
                x={left + w - 66} y={top + h - 18} width={58} height={14}
                rx={4} fill={meta.color + '33'} stroke={meta.color + '66'} strokeWidth={0.5}
            />
            <text
                x={left + w - 37} y={top + h - 8}
                textAnchor="middle" fontSize={8} fill={meta.color} fontWeight={700}
                style={{ letterSpacing: '0.3px', textTransform: 'uppercase' }}
            >
                {level}
            </text>
            {/* Cause text — clipped at 2 lines via foreignObject */}
            <foreignObject x={left + 6} y={top + 5} width={w - 12} height={h - 20}>
                <div xmlns="http://www.w3.org/1999/xhtml" style={{
                    fontSize: '10px', lineHeight: '13px', color: '#e0e0e0',
                    overflow: 'hidden', display: '-webkit-box',
                    WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                    fontFamily: "'Segoe UI', system-ui, sans-serif",
                }}>
                    {cause}
                </div>
            </foreignObject>
        </g>
    )
}

// ─── Single primary bone (one category branch + its leaf nodes) ───────────────
function PrimaryBone({
    cat, causes, spineY, spineStartX, spineEndX, isTop, boneIndex, totalBones,
    activeBone, setActiveBone, activeLeaf, setActiveLeaf,
}) {
    const ANGLE_DEG = 35
    const ANGLE_RAD = (ANGLE_DEG * Math.PI) / 180
    const BONE_LENGTH = 220

    // Evenly distribute bones along the spine (exclude last 15% for head)
    const usableLength = (spineEndX - spineStartX) * 0.82
    const spacing = usableLength / (totalBones + 1)
    const rootX = spineStartX + spacing * (boneIndex + 1)
    const rootY = spineY

    const tipX = rootX - BONE_LENGTH * Math.cos(ANGLE_RAD)
    const tipY = isTop
        ? rootY - BONE_LENGTH * Math.sin(ANGLE_RAD)
        : rootY + BONE_LENGTH * Math.sin(ANGLE_RAD)

    // Filter out EFFECT causes
    const mainCauses = causes.filter(c => c.evidence_level !== 'EFFECT')

    // Sort by priority so CONFIRMED is nearest the spine
    const sorted = [...mainCauses].sort((a, b) => {
        const pa = EVIDENCE_META[a.evidence_level]?.priority ?? 1
        const pb = EVIDENCE_META[b.evidence_level]?.priority ?? 1
        return pb - pa // highest priority (CONFIRMED=3) first → nearest spine
    })

    const boneKey = cat
    const isActive = activeBone === boneKey
    const isDimmed = activeBone && activeBone !== boneKey
    const opacity = isDimmed ? 0.2 : 1

    return (
        <g
            className="primary-bone"
            style={{ transition: 'opacity 0.25s', opacity }}
            onMouseEnter={() => setActiveBone(boneKey)}
            onMouseLeave={() => { setActiveBone(null); setActiveLeaf(null) }}
        >
            {/* Main bone line */}
            <line
                x1={rootX} y1={rootY} x2={tipX} y2={tipY}
                stroke={isActive ? '#7da8ff' : '#3a4060'}
                strokeWidth={isActive ? 2.5 : 1.5}
                strokeLinecap="round"
                style={{ transition: 'stroke 0.2s, stroke-width 0.2s' }}
            />
            {/* Category label at tip */}
            <text
                x={tipX + (isTop ? 0 : 0)}
                y={isTop ? tipY - 12 : tipY + 18}
                textAnchor="middle"
                fontSize={11}
                fontWeight={700}
                fill={isActive ? '#c0d4ff' : '#7da8ff'}
                style={{ letterSpacing: '0.6px', textTransform: 'uppercase', transition: 'fill 0.2s' }}
            >
                {CAT_ICONS[cat]} {cat}
            </text>

            {/* Leaf nodes placed along the bone */}
            {sorted.map((c, i) => {
                const meta = EVIDENCE_META[c.evidence_level] || EVIDENCE_META.POSSIBLE
                const ratio = meta.posRatio ?? 0.78
                // stagger multiple causes at same priority slightly
                const spread = sorted.filter(x => x.evidence_level === c.evidence_level).indexOf(c) * 0.12
                const r = Math.min(ratio + spread, 0.95)
                const lx = rootX + (tipX - rootX) * r
                const ly = rootY + (tipY - rootY) * r

                // Sub-bone connecting leaf to primary bone
                const subBoneLen = isTop ? -30 : 30
                const perpX = Math.sin(ANGLE_RAD) * (isTop ? -15 : 15)
                const perpY = Math.cos(ANGLE_RAD) * (isTop ? 15 : -15)
                const leafKey = `${cat}-${i}`
                const leafActive = activeLeaf === leafKey && isActive
                const leafDimmed = activeLeaf && activeLeaf !== leafKey && isActive

                return (
                    <g key={i}>
                        {/* Small perpendicular sub-bone */}
                        <line
                            x1={lx} y1={ly}
                            x2={lx + perpX} y2={ly + perpY}
                            stroke={leafActive ? '#7da8ff' : '#2a3050'}
                            strokeWidth={1}
                            strokeDasharray="3,2"
                        />
                        <LeafNode
                            x={lx + perpX + (isTop ? -8 : -8)}
                            y={ly + perpY + (isTop ? -35 : 35)}
                            cause={c.cause}
                            level={c.evidence_level || 'POSSIBLE'}
                            isActive={leafActive}
                            isDimmed={leafDimmed}
                            onMouseEnter={() => setActiveLeaf(leafKey)}
                            onMouseLeave={() => setActiveLeaf(null)}
                            onClick={() => setActiveLeaf(leafActive ? null : leafKey)}
                        />
                    </g>
                )
            })}
        </g>
    )
}

// ─── Timeline modal (5 Whys steps) ───────────────────────────────────────────
function TimelineModal({ whySteps, onClose }) {
    if (!whySteps?.length) return null
    return (
        <div className="timeline-overlay" onClick={onClose}>
            <div className="timeline-modal" onClick={e => e.stopPropagation()}>
                <div className="timeline-modal-header">
                    <h3>📋 5 Whys — Causal Chain</h3>
                    <button className="timeline-close" onClick={onClose}>✕</button>
                </div>
                <div className="timeline-steps">
                    {whySteps.map((step, i) => (
                        <div className="timeline-step" key={i}>
                            <div className="timeline-num">{step.step_number || i + 1}</div>
                            <div className="timeline-body">
                                <p className="timeline-q">{step.question}</p>
                                <p className="timeline-a">{step.answer}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}

// ─── EFFECT Rail ──────────────────────────────────────────────────────────────
function EffectRail({ effects }) {
    const [open, setOpen] = useState(false)
    if (!effects.length) return null
    return (
        <div className="effect-rail-wrapper">
            <button className="effect-toggle" onClick={() => setOpen(o => !o)}>
                ⚠ {open ? 'Hide' : 'Show'} Effects ({effects.length})
                <span className="effect-toggle-hint"> — consequences, not causes</span>
            </button>
            {open && (
                <div className="effect-rail">
                    {effects.map((e, i) => (
                        <div key={i} className="effect-pill">
                            <span className="effect-cat">{e.cat}</span>
                            <span className="effect-text">{e.cause}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

// ─── Main FishboneCanvas ──────────────────────────────────────────────────────
export default function FishboneCanvas({ fishbone, whySteps }) {
    const [activeBone, setActiveBone] = useState(null)
    const [activeLeaf, setActiveLeaf] = useState(null)
    const [showTimeline, setShowTimeline] = useState(false)
    const [expanded, setExpanded] = useState(true)
    const containerRef = useRef(null)
    const [dims, setDims] = useState({ w: 1100, h: 520 })

    // Measure container and update SVG viewBox on resize
    useEffect(() => {
        const el = containerRef.current
        if (!el) return
        const ro = new ResizeObserver(([entry]) => {
            const { width, height } = entry.contentRect
            setDims({ w: Math.max(width, 700), h: Math.max(height, 420) })
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    if (!fishbone?.categories) return null

    // Collect causes for each category, separating EFFECT causes
    const effectCauses = []
    const catMap = {}
        ;[...TOP_CATS, ...BOTTOM_CATS].forEach(cat => {
            const causes = fishbone.categories?.[cat] || []
            const main = causes.filter(c => {
                if (c.evidence_level === 'EFFECT') {
                    effectCauses.push({ cat, ...c })
                    return false
                }
                return true
            })
            if (main.length > 0) catMap[cat] = main
        })

    const topCats = TOP_CATS.filter(c => catMap[c])
    const bottomCats = BOTTOM_CATS.filter(c => catMap[c])
    const allCats = [...topCats, ...bottomCats]

    // SVG geometry
    const W = dims.w
    const H = dims.h
    const PAD = 40
    const HEAD_W = 160
    const spineY = H / 2
    const spineX1 = PAD
    const spineX2 = W - PAD - HEAD_W    // spine ends at head

    return (
        <div className="fishbone-canvas-section">
            {/* Header */}
            <div className="fishbone-canvas-header">
                <div>
                    <h3 className="fishbone-canvas-title">Contributing Cause Map</h3>
                    <p className="fishbone-canvas-subtitle">Ishikawa Fishbone — hover a branch to highlight, click root to view timeline</p>
                </div>
                <button className="expand-toggle fishbone-toggle" onClick={() => setExpanded(e => !e)}>
                    <span className="toggle-icon">{expanded ? '▼' : '▶'}</span>
                    {expanded ? 'Collapse' : 'Expand'}
                </button>
            </div>

            {expanded && (
                <>
                    {/* SVG Canvas */}
                    <div
                        ref={containerRef}
                        className="fishbone-svg-wrapper"
                        onMouseLeave={() => { setActiveBone(null); setActiveLeaf(null) }}
                    >
                        <svg
                            width="100%"
                            height="100%"
                            viewBox={`0 0 ${W} ${H}`}
                            preserveAspectRatio="xMidYMid meet"
                            style={{ display: 'block' }}
                        >
                            {/* ── Spine ── */}
                            <line
                                x1={spineX1} y1={spineY}
                                x2={spineX2} y2={spineY}
                                stroke="#ef4444" strokeWidth={4} strokeLinecap="round"
                            />
                            {/* Spine arrow head */}
                            <polygon
                                points={`${spineX2},${spineY} ${spineX2 - 14},${spineY - 8} ${spineX2 - 14},${spineY + 8}`}
                                fill="#ef4444"
                            />

                            {/* ── Root Cause Head ── */}
                            <g
                                className="root-cause-node"
                                style={{ cursor: 'pointer' }}
                                onClick={() => setShowTimeline(t => !t)}
                            >
                                <rect
                                    x={spineX2} y={spineY - 44}
                                    width={HEAD_W} height={88}
                                    rx={10} ry={10}
                                    fill="#1e1025"
                                    stroke="#ef4444" strokeWidth={2}
                                    filter="drop-shadow(0 0 10px #ef444488)"
                                />
                                <rect
                                    x={spineX2} y={spineY - 14}
                                    width={50} height={14}
                                    rx={4} fill="#ef444422" stroke="#ef444455" strokeWidth={0.5}
                                />
                                <text
                                    x={spineX2 + 25} y={spineY - 4}
                                    textAnchor="middle" fontSize={7.5} fill="#ef4444"
                                    fontWeight={700} style={{ letterSpacing: '0.5px', textTransform: 'uppercase' }}
                                >ROOT CAUSE</text>
                                <foreignObject x={spineX2 + 4} y={spineY - 44} width={HEAD_W - 8} height={28}>
                                    <div xmlns="http://www.w3.org/1999/xhtml" style={{
                                        fontSize: '9px', lineHeight: '12px', color: '#f0d0d0',
                                        fontFamily: "'Segoe UI', system-ui, sans-serif",
                                        padding: '4px 2px',
                                        overflow: 'hidden', display: '-webkit-box',
                                        WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                                    }}>
                                        {fishbone.root_cause_confirmed}
                                    </div>
                                </foreignObject>
                                {/* Click hint */}
                                <text x={spineX2 + HEAD_W / 2} y={spineY + 36}
                                    textAnchor="middle" fontSize={8} fill="#888">
                                    📋 click for timeline
                                </text>
                            </g>

                            {/* ── Top bones ── */}
                            {topCats.map((cat, i) => (
                                <PrimaryBone
                                    key={cat}
                                    cat={cat}
                                    causes={catMap[cat]}
                                    spineY={spineY}
                                    spineStartX={spineX1}
                                    spineEndX={spineX2}
                                    isTop={true}
                                    boneIndex={i}
                                    totalBones={topCats.length}
                                    activeBone={activeBone}
                                    setActiveBone={setActiveBone}
                                    activeLeaf={activeLeaf}
                                    setActiveLeaf={setActiveLeaf}
                                />
                            ))}

                            {/* ── Bottom bones ── */}
                            {bottomCats.map((cat, i) => (
                                <PrimaryBone
                                    key={cat}
                                    cat={cat}
                                    causes={catMap[cat]}
                                    spineY={spineY}
                                    spineStartX={spineX1}
                                    spineEndX={spineX2}
                                    isTop={false}
                                    boneIndex={i}
                                    totalBones={bottomCats.length}
                                    activeBone={activeBone}
                                    setActiveBone={setActiveBone}
                                    activeLeaf={activeLeaf}
                                    setActiveLeaf={setActiveLeaf}
                                />
                            ))}

                            {/* ── Spine label (left anchor) ── */}
                            <text
                                x={spineX1 + 8} y={spineY - 10}
                                fontSize={9} fill="#ef444466"
                                style={{ letterSpacing: '0.5px', textTransform: 'uppercase' }}
                            >
                                Contributing Factors
                            </text>
                        </svg>
                    </div>

                    {/* ── EFFECT Rail ── */}
                    <EffectRail effects={effectCauses} />

                    {/* ── Timeline Modal ── */}
                    {showTimeline && (
                        <TimelineModal
                            whySteps={whySteps}
                            onClose={() => setShowTimeline(false)}
                        />
                    )}
                </>
            )}
        </div>
    )
}
