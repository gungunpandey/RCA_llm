import React, { useState } from 'react';

const W = 290;
const H = 296;
const CX = 145;
const CY = 148;
const RO = 105;
const RI = 75;
const GAP = 3.8;

const PAL = [
  { hi: '#a5b4fc', mid: '#6366f1', lo: '#4338ca' }, // Modern Indigo
  { hi: '#99f6e4', mid: '#0d9488', lo: '#115e59' }, // Deep Teal
  { hi: '#93c5fd', mid: '#3b82f6', lo: '#1d4ed8' }, // Ocean Blue
  { hi: '#a7f3d0', mid: '#10b981', lo: '#064e3b' }, // Emerald
  { hi: '#f5d0fe', mid: '#a855f7', lo: '#6b21a8' }, // Electric Purple/Orchid
  { hi: '#fecaca', mid: '#ef4444', lo: '#991b1b' }, // Soft Crimson/Coral
  { hi: '#fde047', mid: '#eab308', lo: '#854d0e' }, // Amber Gold
  { hi: '#fed7aa', mid: '#f97316', lo: '#9a3412' }  // Burning Orange
];

function xy(cx, cy, r, deg) {
  const a = (deg - 90) * Math.PI / 180;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

function arc(cx, cy, ri, ro, a1, a2) {
  const lg = (a2 - a1) > 180 ? 1 : 0;
  const [x1, y1] = xy(cx, cy, ro, a1);
  const [x2, y2] = xy(cx, cy, ro, a2);
  const [x3, y3] = xy(cx, cy, ri, a2);
  const [x4, y4] = xy(cx, cy, ri, a1);
  return `M${x1},${y1} A${ro},${ro} 0 ${lg} 1 ${x2},${y2} L${x3},${y3} A${ri},${ri} 0 ${lg} 0 ${x4},${y4}Z`;
}

const FailuresPieChart = ({ data }) => {
  const [act, setAct] = useState(null);
  if (!data || !data.length) return <div className="chart-empty">No failure data.</div>;

  const total = data.reduce((s, d) => s + d.count, 0);
  let cursor = 0;
  const segs = data.map((d, i) => {
    const sweep = (d.count / total) * (360 - GAP * data.length);
    const a1 = cursor + GAP / 2, a2 = a1 + sweep;
    cursor += sweep + GAP;
    const mid = (a1 + a2) / 2;
    const [lx, ly] = xy(CX, CY, (RI + RO) / 2, mid);
    const pct = Math.round((d.count / total) * 100);
    return { d, a1, a2, mid, lx, ly, pct, p: PAL[i % PAL.length], i };
  });

  return (
    <div style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{ flex: '0 0 54%', position: 'relative' }}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible' }}>
          <defs>
            {segs.map(({ p, i }) => (
              <linearGradient key={i} id={`lg${i}`} x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor={p.hi} />
                <stop offset="100%" stopColor={p.mid} />
              </linearGradient>
            ))}
          </defs>

          {/* Donut Segments */}
          {segs.map(({ a1, a2, mid, p, lx, ly, pct, i }) => {
            const on = act === i;
            const a = (mid - 90) * Math.PI / 180;
            const dx = Math.cos(a) * 5;
            const dy = Math.sin(a) * 5;

            return (
              <g
                key={i}
                style={{
                  transform: on ? `translate(${dx}px, ${dy}px)` : 'translate(0px, 0px)',
                  transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s',
                  opacity: act === null || on ? 1 : 0.45,
                }}
                onMouseEnter={() => setAct(i)}
                onMouseLeave={() => setAct(null)}
              >
                <path
                  d={arc(CX, CY, RI, RO, a1, a2)}
                  fill={`url(#lg${i})`}
                  stroke="var(--bg-card, #fff)"
                  strokeWidth={1.5}
                  style={{
                    cursor: 'pointer',
                    filter: on ? `drop-shadow(0 6px 12px ${p.mid}66)` : 'none',
                    transition: 'filter 0.25s',
                  }}
                />

                {/* % Label inside slice */}
                {pct >= 5 && (
                  <text
                    x={lx}
                    y={ly}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize={pct >= 14 ? 11 : 9}
                    fontWeight={700}
                    fill="#fff"
                    style={{
                      pointerEvents: 'none',
                      textShadow: '0 1px 2px rgba(0,0,0,0.2)',
                    }}
                  >
                    {pct}%
                  </text>
                )}
              </g>
            );
          })}

          {/* Center text */}
          <text
            x={CX}
            y={CY - 8}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={28}
            fontWeight={800}
            fill="var(--text-primary)"
            fontFamily="inherit"
            letterSpacing="-0.5px"
          >
            {total}
          </text>
          <text
            x={CX}
            y={CY + 14}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={9.5}
            fontWeight={700}
            fill="var(--text-secondary)"
            fontFamily="inherit"
            letterSpacing="1.8px"
            opacity={0.7}
          >
            TOTAL
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div style={{ flex: '0 0 43%', display: 'flex', flexDirection: 'column', gap: 6, paddingLeft: 4 }}>
        {segs.map(({ d, pct, p, i }) => {
          const on = act === i;
          return (
            <div
              key={i}
              onMouseEnter={() => setAct(i)}
              onMouseLeave={() => setAct(null)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                cursor: 'pointer',
                opacity: act === null || on ? 1 : 0.4,
                transition: 'all 0.2s',
                padding: '5px 10px',
                borderRadius: 9,
                background: on ? `${p.mid}14` : 'transparent',
                border: on ? `1px solid ${p.mid}44` : '1px solid transparent',
              }}
            >
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  flexShrink: 0,
                  background: `linear-gradient(135deg, ${p.hi}, ${p.mid})`,
                  boxShadow: on ? `0 0 8px ${p.mid}` : 'none',
                  transition: 'box-shadow 0.2s',
                }}
              />
              <span
                style={{
                  flex: 1,
                  fontSize: '0.77rem',
                  color: 'var(--text-primary)',
                  fontWeight: on ? 700 : 400,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textShadow: on ? '0px 0px 1px rgba(0,0,0,0.1)' : 'none',
                  textOverflow: 'ellipsis',
                }}
              >
                {d.category}
              </span>
              <span
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  flexShrink: 0,
                  color: on ? p.mid : 'var(--text-secondary)',
                }}
              >
                {d.count} <span style={{ fontWeight: 400, opacity: 0.65 }}>({pct}%)</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default FailuresPieChart;
