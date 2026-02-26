import { useState } from 'react'

// ─── Evidence metadata ───────────────────────────────────────────────────────
const EVIDENCE_META = {
    CONFIRMED: { color: '#34d399', bg: 'rgba(52,211,153,0.15)', border: 'rgba(52,211,153,0.5)', priority: 3 },
    SUPPORTED: { color: '#4a7cff', bg: 'rgba(74,124,255,0.15)', border: 'rgba(74,124,255,0.5)', priority: 2 },
    POSSIBLE:  { color: '#fbbf24', bg: 'rgba(251,191,36,0.15)',  border: 'rgba(251,191,36,0.5)',  priority: 1 },
    EFFECT:    { color: '#6b7280', bg: 'rgba(107,114,128,0.12)', border: 'rgba(107,114,128,0.4)', priority: 0 },
}

const TOP_CATS    = ['Machine', 'Material', 'Environment']
const BOTTOM_CATS = ['Method', 'Man', 'Measurement']
const CAT_ICONS   = {
    Machine: '⚙️', Material: '📦', Environment: '🌡️',
    Method: '📋', Man: '👷', Measurement: '📊',
}

// ─── Fixed canvas size (no ResizeObserver — prevents collapse/expand layout shift) ──
const CANVAS_W = 1280
const CANVAS_H = 560

// ─── Node dimensions ──────────────────────────────────────────────────────────
const NODE_W = 134
const NODE_H = 56

// ─── LeafNode ─────────────────────────────────────────────────────────────────
function LeafNode({ x, y, cause, level, isActive, isDimmed, onClick, onMouseEnter, onMouseLeave }) {
    const meta = EVIDENCE_META[level] || EVIDENCE_META.POSSIBLE
    const left = x - NODE_W / 2
    const top  = y - NODE_H / 2
    const opac = isDimmed ? 0.22 : 1

    return (
        <g
            className={`leaf-node ${isActive ? 'leaf-active' : ''}`}
            style={{ cursor: 'pointer', opacity: opac, transition: 'opacity 0.25s' }}
            onClick={onClick}
            onMouseEnter={onMouseEnter}
            onMouseLeave={onMouseLeave}
        >
            <rect
                x={left} y={top} width={NODE_W} height={NODE_H}
                rx={8} ry={8}
                fill={meta.bg}
                stroke={isActive ? meta.color : meta.border}
                strokeWidth={isActive ? 2 : 1}
                filter={isActive ? `drop-shadow(0 0 6px ${meta.color}88)` : undefined}
            />
            {/* Evidence badge pill */}
            <rect
                x={left + NODE_W - 68} y={top + NODE_H - 18}
                width={62} height={14}
                rx={4} fill={meta.color + '33'} stroke={meta.color + '66'} strokeWidth={0.5}
            />
            <text
                x={left + NODE_W - 37} y={top + NODE_H - 7}
                textAnchor="middle" fontSize={9} fill={meta.color} fontWeight={700}
                style={{ letterSpacing: '0.3px', textTransform: 'uppercase' }}
            >
                {level}
            </text>
            {/* Cause text via foreignObject (allows wrapping) */}
            <foreignObject x={left + 7} y={top + 6} width={NODE_W - 16} height={NODE_H - 24}>
                <div xmlns="http://www.w3.org/1999/xhtml" style={{
                    fontSize: '11px', lineHeight: '14px', color: '#e0e0e0',
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

// ─── PrimaryBone ──────────────────────────────────────────────────────────────
function PrimaryBone({
    cat, causes, spineY, spineStartX, spineEndX, isTop, boneIndex, totalBones,
    activeBone, setActiveBone, activeLeaf, setActiveLeaf,
}) {
    const ANGLE_DEG = 36
    const ANGLE_RAD = (ANGLE_DEG * Math.PI) / 180
    // Vertical distance from the bone line to the node centre (straight up/down).
    // This is independent of bone angle — keeps layout predictable.
    const VERT_OFFSET = 62

    // Filter out EFFECT causes (shown in the EFFECT rail below)
    const mainCauses = causes.filter(c => c.evidence_level !== 'EFFECT')
    // Sort by priority so CONFIRMED lands nearest the spine (high-confidence first)
    const sorted = [...mainCauses].sort((a, b) => {
        const pa = EVIDENCE_META[a.evidence_level]?.priority ?? 1
        const pb = EVIDENCE_META[b.evidence_level]?.priority ?? 1
        return pb - pa
    })
    const n = sorted.length

    // Dynamic bone length: longer bones for more nodes so they never crowd
    // Minimum vertical node separation = BONE * sin(angle) * (range / (n-1))
    // We need that separation ≥ NODE_H.  Solving:  BONE ≥ NODE_H*(n-1) / (sin*range)
    // With range=0.65, sin36°≈0.588:  BONE ≥ NODE_H*(n-1) / (0.588*0.65) ≈ (n-1)*146
    const BONE_LENGTH = n <= 1 ? 230 : Math.min(Math.max(230, (n - 1) * 150), 310)

    // Evenly space bone roots along the usable spine length
    const usableLength = (spineEndX - spineStartX) * 0.82
    const spacing  = usableLength / (totalBones + 1)
    const rootX    = spineStartX + spacing * (boneIndex + 1)
    const rootY    = spineY

    const tipX = rootX - BONE_LENGTH * Math.cos(ANGLE_RAD)
    const tipY = isTop
        ? rootY - BONE_LENGTH * Math.sin(ANGLE_RAD)
        : rootY + BONE_LENGTH * Math.sin(ANGLE_RAD)

    // ── Category label position ──────────────────────────────────────────────
    // Place the label above the topmost node (top bones) or below the
    // bottommost node (bottom bones), centred over that outermost node.
    const r_outer   = n <= 1 ? 0.40 : 0.73          // r of the node farthest from spine
    const lx_outer  = rootX + (tipX - rootX) * r_outer
    const ly_outer  = rootY + (tipY - rootY) * r_outer
    const labelX    = n > 0 ? lx_outer : tipX
    const labelY    = isTop
        ? ly_outer - VERT_OFFSET - NODE_H / 2 - 12  // 12 px above top edge of topmost node
        : ly_outer + VERT_OFFSET + NODE_H / 2 + 18  // 18 px below bottom edge of bottommost node

    const boneKey  = cat
    const isActive = activeBone === boneKey
    const isDimmed = activeBone && activeBone !== boneKey
    const opacity  = isDimmed ? 0.2 : 1

    return (
        <g
            className="primary-bone"
            style={{ transition: 'opacity 0.25s', opacity }}
            onMouseEnter={() => setActiveBone(boneKey)}
            onMouseLeave={() => { setActiveBone(null); setActiveLeaf(null) }}
        >
            {/* Main diagonal bone line */}
            <line
                x1={rootX} y1={rootY} x2={tipX} y2={tipY}
                stroke={isActive ? '#7da8ff' : '#3a4060'}
                strokeWidth={isActive ? 2.5 : 1.5}
                strokeLinecap="round"
                style={{ transition: 'stroke 0.2s, stroke-width 0.2s' }}
            />

            {/* ── Leaf nodes ── */}
            {sorted.map((c, i) => {
                // Evenly distribute from 8 % to 73 % of bone length.
                // With BONE_LENGTH chosen so vertical separation ≥ NODE_H,
                // nodes will never overlap regardless of evidence level.
                const r  = n === 1 ? 0.40 : 0.08 + (i / (n - 1)) * 0.65
                const lx = rootX + (tipX - rootX) * r
                const ly = rootY + (tipY - rootY) * r

                // Node centre: straight up (top) or down (bottom) from bone point
                const nodeX = lx
                const nodeY = ly + (isTop ? -VERT_OFFSET : VERT_OFFSET)

                // Short dashed tick connecting bone → node edge
                const tickY2 = nodeY + (isTop ? NODE_H / 2 : -NODE_H / 2)

                const leafKey    = `${cat}-${i}`
                const leafActive = activeLeaf === leafKey && isActive
                const leafDimmed = activeLeaf && activeLeaf !== leafKey && isActive

                return (
                    <g key={i}>
                        <line
                            x1={lx}    y1={ly}
                            x2={nodeX} y2={tickY2}
                            stroke={leafActive ? '#7da8ff' : '#2a3050'}
                            strokeWidth={1}
                            strokeDasharray="3,2"
                        />
                        <LeafNode
                            x={nodeX}
                            y={nodeY}
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

            {/* Category label — above topmost node (top) / below bottommost node (bottom) */}
            <text
                x={labelX}
                y={labelY}
                textAnchor="middle"
                fontSize={13}
                fontWeight={700}
                fill={isActive ? '#c0d4ff' : '#7da8ff'}
                stroke="#0d1117"
                strokeWidth={3}
                paintOrder="stroke"
                style={{ letterSpacing: '0.5px', textTransform: 'uppercase', transition: 'fill 0.2s' }}
            >
                {CAT_ICONS[cat]} {cat}
            </text>
        </g>
    )
}

// ─── Timeline modal (5 Whys) ──────────────────────────────────────────────────
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
    const [activeBone,   setActiveBone]   = useState(null)
    const [activeLeaf,   setActiveLeaf]   = useState(null)
    const [showTimeline, setShowTimeline] = useState(false)
    const [expanded,     setExpanded]     = useState(true)

    if (!fishbone?.categories) return null

    // Separate EFFECT causes from main causes
    const effectCauses = []
    const catMap = {}
    ;[...TOP_CATS, ...BOTTOM_CATS].forEach(cat => {
        const causes = fishbone.categories?.[cat] || []
        const main = causes.filter(c => {
            if (c.evidence_level === 'EFFECT') { effectCauses.push({ cat, ...c }); return false }
            return true
        })
        if (main.length > 0) catMap[cat] = main
    })

    const topCats    = TOP_CATS.filter(c => catMap[c])
    const bottomCats = BOTTOM_CATS.filter(c => catMap[c])

    // ── Fixed SVG geometry ──
    const W      = CANVAS_W
    const H      = CANVAS_H
    const PAD    = 68
    const HEAD_W = 178
    const spineY = H / 2
    const spineX1 = PAD
    const spineX2 = W - PAD - HEAD_W   // spine tip (= 1034)

    return (
        <div className="fishbone-canvas-section">
            {/* Header */}
            <div className="fishbone-canvas-header">
                <div>
                    <h3 className="fishbone-canvas-title">Contributing Cause Map</h3>
                    <p className="fishbone-canvas-subtitle">
                        Ishikawa Fishbone — hover a branch to highlight, click root to view timeline
                    </p>
                </div>
                <button
                    className="expand-toggle fishbone-toggle"
                    onClick={() => setExpanded(e => !e)}
                >
                    <span className="toggle-icon">{expanded ? '▼' : '▶'}</span>
                    {expanded ? 'Collapse' : 'Expand'}
                </button>
            </div>

            {/* Use display:none instead of unmounting — prevents layout recalc on re-expand */}
            <div style={{ display: expanded ? 'block' : 'none' }}>
                {/* SVG Canvas */}
                <div
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
                        {/* Arrowhead */}
                        <polygon
                            points={`${spineX2},${spineY} ${spineX2 - 14},${spineY - 9} ${spineX2 - 14},${spineY + 9}`}
                            fill="#ef4444"
                        />

                        {/* ── Root Cause Head ── */}
                        <g
                            className="root-cause-node"
                            style={{ cursor: 'pointer' }}
                            onClick={() => setShowTimeline(t => !t)}
                        >
                            <rect
                                x={spineX2}     y={spineY - 48}
                                width={HEAD_W}  height={96}
                                rx={10} ry={10}
                                fill="#1e1025"
                                stroke="#ef4444" strokeWidth={2}
                                filter="drop-shadow(0 0 10px #ef444488)"
                            />
                            {/* ROOT CAUSE label pill */}
                            <rect
                                x={spineX2 + 6} y={spineY - 16}
                                width={58} height={15}
                                rx={4} fill="#ef444422" stroke="#ef444455" strokeWidth={0.5}
                            />
                            <text
                                x={spineX2 + 35} y={spineY - 5}
                                textAnchor="middle" fontSize={8.5} fill="#ef4444"
                                fontWeight={700} style={{ letterSpacing: '0.5px', textTransform: 'uppercase' }}
                            >ROOT CAUSE</text>
                            {/* Root cause text */}
                            <foreignObject
                                x={spineX2 + 6}  y={spineY - 48}
                                width={HEAD_W - 12} height={30}
                            >
                                <div xmlns="http://www.w3.org/1999/xhtml" style={{
                                    fontSize: '10px', lineHeight: '13px', color: '#f0d0d0',
                                    fontFamily: "'Segoe UI', system-ui, sans-serif",
                                    padding: '4px 2px',
                                    overflow: 'hidden', display: '-webkit-box',
                                    WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                                }}>
                                    {fishbone.root_cause_confirmed}
                                </div>
                            </foreignObject>
                            {/* Click hint */}
                            <text
                                x={spineX2 + HEAD_W / 2} y={spineY + 40}
                                textAnchor="middle" fontSize={9} fill="#888"
                            >
                                📋 click for timeline
                            </text>
                        </g>

                        {/* ── Top bones ── */}
                        {topCats.map((cat, i) => (
                            <PrimaryBone
                                key={cat} cat={cat} causes={catMap[cat]}
                                spineY={spineY} spineStartX={spineX1} spineEndX={spineX2}
                                isTop={true} boneIndex={i} totalBones={topCats.length}
                                activeBone={activeBone} setActiveBone={setActiveBone}
                                activeLeaf={activeLeaf}  setActiveLeaf={setActiveLeaf}
                            />
                        ))}

                        {/* ── Bottom bones ── */}
                        {bottomCats.map((cat, i) => (
                            <PrimaryBone
                                key={cat} cat={cat} causes={catMap[cat]}
                                spineY={spineY} spineStartX={spineX1} spineEndX={spineX2}
                                isTop={false} boneIndex={i} totalBones={bottomCats.length}
                                activeBone={activeBone} setActiveBone={setActiveBone}
                                activeLeaf={activeLeaf}  setActiveLeaf={setActiveLeaf}
                            />
                        ))}

                        {/* Spine label */}
                        <text
                            x={spineX1 + 10} y={spineY - 12}
                            fontSize={9} fill="#ef444466"
                            style={{ letterSpacing: '0.5px', textTransform: 'uppercase' }}
                        >
                            Contributing Factors
                        </text>
                    </svg>
                </div>

                {/* EFFECT Rail */}
                <EffectRail effects={effectCauses} />

                {/* Timeline Modal */}
                {showTimeline && (
                    <TimelineModal
                        whySteps={whySteps}
                        onClose={() => setShowTimeline(false)}
                    />
                )}
            </div>
        </div>
    )
}
