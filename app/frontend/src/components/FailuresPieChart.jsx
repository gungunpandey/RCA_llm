import React, { useState } from 'react';

const W=290,H=296,CX=145,CY=146,RO=108,RI=66,DEPTH=11,GAP=3.8;

const PAL=[
  {hi:'#ddd6fe',mid:'#a78bfa',lo:'#5b4db0'},
  {hi:'#a5e8f5',mid:'#38bdf8',lo:'#2272a3'},
  {hi:'#a7f3d0',mid:'#34d399',lo:'#0f7a5a'},
  {hi:'#fef08a',mid:'#facc15',lo:'#a16a1a'},
  {hi:'#fecaca',mid:'#f87171',lo:'#9b3535'},
  {hi:'#f5d0fe',mid:'#c084fc',lo:'#7e3aab'},
  {hi:'#fed7aa',mid:'#fb923c',lo:'#9a4a20'},
  {hi:'#bae6fd',mid:'#38bdf8',lo:'#1a6fa3'},
];

function xy(cx,cy,r,deg){
  const a=(deg-90)*Math.PI/180;
  return [cx+r*Math.cos(a),cy+r*Math.sin(a)];
}

function arc(cx,cy,ri,ro,a1,a2,dy=0){
  const lg=(a2-a1)>180?1:0;
  const [x1,y1]=xy(cx,cy,ro,a1);
  const [x2,y2]=xy(cx,cy,ro,a2);
  const [x3,y3]=xy(cx,cy,ri,a2);
  const [x4,y4]=xy(cx,cy,ri,a1);
  return `M${x1},${y1+dy} A${ro},${ro} 0 ${lg} 1 ${x2},${y2+dy} L${x3},${y3+dy} A${ri},${ri} 0 ${lg} 0 ${x4},${y4+dy}Z`;
}

const FailuresPieChart=({data})=>{
  const [act,setAct]=useState(null);
  if(!data||!data.length) return <div className="chart-empty">No failure data.</div>;

  const total=data.reduce((s,d)=>s+d.count,0);
  let cursor=0;
  const segs=data.map((d,i)=>{
    const sweep=(d.count/total)*(360-GAP*data.length);
    const a1=cursor+GAP/2, a2=a1+sweep;
    cursor+=sweep+GAP;
    const mid=(a1+a2)/2;
    const [lx,ly]=xy(CX,CY,(RI+RO)/2,mid);
    const pct=Math.round((d.count/total)*100);
    return {d,a1,a2,mid,lx,ly,pct,p:PAL[i%PAL.length],i};
  });

  return(
    <div style={{width:'100%',display:'flex',alignItems:'center',gap:12}}>
      <div style={{flex:'0 0 54%',position:'relative'}}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{overflow:'visible'}}>
          <defs>
            {segs.map(({p,i})=>(
              <radialGradient key={i} id={`rg${i}`} cx="36%" cy="28%" r="72%" fx="36%" fy="28%">
                <stop offset="0%"   stopColor={p.hi} stopOpacity={0.95}/>
                <stop offset="55%"  stopColor={p.mid} stopOpacity={0.88}/>
                <stop offset="100%" stopColor={p.lo}  stopOpacity={0.72}/>
              </radialGradient>
            ))}
            {segs.map(({p,i})=>(
              <linearGradient key={i} id={`dg${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={p.lo} stopOpacity={0.9}/>
                <stop offset="100%" stopColor={p.lo} stopOpacity={0.5}/>
              </linearGradient>
            ))}
            <radialGradient id="spec" cx="32%" cy="22%" r="68%">
              <stop offset="0%"   stopColor="#fff" stopOpacity={0.65}/>
              <stop offset="55%"  stopColor="#fff" stopOpacity={0.15}/>
              <stop offset="100%" stopColor="#fff" stopOpacity={0}/>
            </radialGradient>
            <radialGradient id="hole" cx="50%" cy="40%" r="60%">
              <stop offset="0%"   stopColor="#f8fafc"/>
              <stop offset="100%" stopColor="#e2e8f0"/>
            </radialGradient>
            <filter id="dshadow" x="-25%" y="-25%" width="150%" height="175%">
              <feDropShadow dx="0" dy="5" stdDeviation="9" floodColor="rgba(0,0,0,0.16)"/>
            </filter>
            <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="7" result="b"/>
              <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>

          {/* ambient ground shadow */}
          <ellipse cx={CX} cy={CY+DEPTH+10} rx={RO+6} ry={(RO+6)*0.22}
            fill="rgba(0,0,0,0.11)" style={{filter:'blur(9px)'}}/>

          {/* depth / side extrusion layer */}
          <g filter="url(#dshadow)">
            {segs.map(({a1,a2,i})=>(
              <path key={i} d={arc(CX,CY,RI,RO,a1,a2,DEPTH)}
                fill={`url(#dg${i})`}
                opacity={act===null||act===i?1:0.35}
                style={{transition:'opacity 0.2s'}}/>
            ))}
          </g>

          {/* top face */}
          {segs.map(({a1,a2,p,i})=>{
            const on=act===i;
            return(
              <path key={i}
                d={arc(CX,CY,RI,RO,a1,a2,on?-4:0)}
                fill={`url(#rg${i})`}
                stroke="rgba(255,255,255,0.3)"
                strokeWidth={on?2.5:1.2}
                opacity={act===null||on?1:0.4}
                style={{cursor:'pointer',transition:'all 0.22s',
                  filter:on?`drop-shadow(0 0 12px ${p.mid}99)`:'none'}}
                onMouseEnter={()=>setAct(i)}
                onMouseLeave={()=>setAct(null)}/>
            );
          })}

          {/* jelly specular highlight */}
          {segs.map(({a1,a2,i})=>{
            const span=a2-a1;
            return(
              <path key={i}
                d={arc(CX,CY,RI+7,RO-7,a1,a1+span*0.52,0)}
                fill="url(#spec)"
                pointerEvents="none"
                opacity={act===null||act===i?0.88:0.25}
                style={{transition:'opacity 0.2s'}}/>
            );
          })}

          {/* outer rim shadow */}
          <circle cx={CX} cy={CY} r={RO+1} fill="none"
            stroke="rgba(0,0,0,0.07)" strokeWidth={4} pointerEvents="none"/>

          {/* inner hole */}
          <circle cx={CX} cy={CY} r={RI-1} fill="url(#hole)"/>
          <circle cx={CX} cy={CY} r={RI-1} fill="none"
            stroke="rgba(0,0,0,0.09)" strokeWidth={3}/>

          {/* % labels */}
          {segs.map(({lx,ly,pct,i})=>pct>=5&&(
            <text key={i} x={lx} y={ly}
              textAnchor="middle" dominantBaseline="middle"
              fontSize={pct>=14?12:10} fontWeight={800}
              fill="#fff" fontFamily="inherit"
              filter="drop-shadow(0 1px 3px rgba(0,0,0,0.55))"
              opacity={act===null||act===i?1:0.25}
              style={{pointerEvents:'none',transition:'opacity 0.2s'}}>
              {pct}%
            </text>
          ))}

          {/* center total */}
          <text x={CX} y={CY-9} textAnchor="middle" dominantBaseline="middle"
            fontSize={27} fontWeight={800} fill="#1a1a1a" fontFamily="inherit" letterSpacing="-1">
            {total}
          </text>
          <text x={CX} y={CY+13} textAnchor="middle" dominantBaseline="middle"
            fontSize={9.5} fontWeight={700} fill="#9ca3af" fontFamily="inherit" letterSpacing="1.8">
            TOTAL
          </text>
        </svg>
      </div>

      {/* legend */}
      <div style={{flex:'0 0 43%',display:'flex',flexDirection:'column',gap:6,paddingLeft:4}}>
        {segs.map(({d,pct,p,i})=>{
          const on=act===i;
          return(
            <div key={i}
              onMouseEnter={()=>setAct(i)}
              onMouseLeave={()=>setAct(null)}
              style={{
                display:'flex',alignItems:'center',gap:8,cursor:'pointer',
                opacity:act===null||on?1:0.4,
                transition:'all 0.2s',
                padding:'5px 10px',borderRadius:9,
                background:on?`${p.mid}14`:'transparent',
                border:on?`1px solid ${p.mid}44`:'1px solid transparent',
              }}>
              <span style={{
                width:11,height:11,borderRadius:'50%',flexShrink:0,
                background:`linear-gradient(135deg,${p.hi},${p.mid})`,
                boxShadow:on?`0 0 8px ${p.mid}`:'none',
                transition:'box-shadow 0.2s',
              }}/>
              <span style={{
                flex:1,fontSize:'0.77rem',color:'var(--text-primary)',
                fontWeight:on?700:400,whiteSpace:'nowrap',
                overflow:'hidden',textOverflow:'ellipsis',
              }}>{d.category}</span>
              <span style={{
                fontSize:'0.72rem',fontWeight:700,flexShrink:0,
                color:on?p.mid:'var(--text-secondary)',
              }}>
                {d.count} <span style={{fontWeight:400,opacity:0.65}}>({pct}%)</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default FailuresPieChart;
