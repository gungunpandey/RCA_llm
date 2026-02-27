import { useState } from 'react'
import FishboneCanvas from './FishboneCanvas'

/**
 * Clean text coming from the LLM:
 *  1. Strip markdown bold/italic markers (** and *)
 *  2. Remove "SUPPORTING_DOCUMENTS:" lines
 *  3. Remove "CONFIDENCE:" lines
 */
function cleanText(raw) {
  if (!raw) return ''
  let text = raw
  text = text.replace(/\*{0,2}SUPPORTING[_ ]DOCUMENTS:?\*{0,2}[^\n]*/gi, '')
  text = text.replace(/\*{0,2}CONFIDENCE:?\*{0,2}\s*\d+%?/gi, '')
  text = text.replace(/\*{1,2}([^*]+?)\*{1,2}/g, '$1')
  text = text.replace(/\n{3,}/g, '\n\n').trim()
  return text
}

function filterDocs(docs) {
  if (!docs) return []
  return docs.filter(d => {
    const trimmed = d.trim().replace(/^[-–\s]+/, '')
    return trimmed.length > 10 && /[a-zA-Z]{3,}/.test(trimmed)
  })
}

function getEvidenceBadge(confidence, answer) {
  const text = answer.toLowerCase()
  if (text.includes('alarm') || text.includes('error code') || text.includes('trip')) {
    return { label: 'From Alarm', icon: '✔', color: '#34d399' }
  }
  if (text.includes('oem manual') || text.includes('manufacturer') || text.includes('specification')) {
    return { label: 'From Manual', icon: '✔', color: '#4a7cff' }
  }
  if (text.includes('observed') || text.includes('inspection') || text.includes('visual')) {
    return { label: 'Observed', icon: '✔', color: '#34d399' }
  }
  if (text.includes('infer') || text.includes('likely') || text.includes('probable') || confidence < 0.7) {
    return { label: 'Inferred', icon: '⚠', color: '#fbbf24' }
  }
  return { label: 'From Manual', icon: '✔', color: '#4a7cff' }
}

function EvidenceBadge({ confidence, answer }) {
  const badge = getEvidenceBadge(confidence, answer)
  return (
    <span className="evidence-badge" style={{ borderColor: badge.color, color: badge.color }}>
      <span className="evidence-icon">{badge.icon}</span>
      {badge.label}
    </span>
  )
}

// ── Domain insight sub-components ────────────────────────────────────────────

function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100)
  const color = pct >= 85 ? '#34d399' : pct >= 60 ? '#fbbf24' : '#f87171'
  return (
    <div className="confidence-bar">
      <div className="confidence-track">
        <div className="confidence-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="confidence-label" style={{ color }}>{pct}%</span>
    </div>
  )
}

function SeverityBadge({ severity }) {
  const colors = {
    critical: { bg: '#3b1a1a', border: '#d44', text: '#f88' },
    warning: { bg: '#2a2a1a', border: '#bb8800', text: '#fbbf24' },
    normal: { bg: '#1a2a1a', border: '#336633', text: '#34d399' },
  }
  const c = colors[severity] || colors.warning
  return (
    <span className="severity-badge" style={{ background: c.bg, borderColor: c.border, color: c.text }}>
      {severity}
    </span>
  )
}

const DOMAIN_LABELS = {
  mechanical: { label: 'Mechanical', color: '#f97316' },
  electrical: { label: 'Electrical', color: '#3b82f6' },
  process: { label: 'Process', color: '#a855f7' },
}

function DomainAgentsSection({ domainInsights }) {
  const [expanded, setExpanded] = useState(false)

  if (!domainInsights?.domain_analyses?.length) return null

  return (
    <div className="detailed-analysis">
      <button className="expand-toggle" onClick={() => setExpanded(!expanded)}>
        <span className="toggle-icon">{expanded ? '▼' : '▶'}</span>
        {expanded ? 'Hide' : 'Show'} Domain Expert Insights
      </button>

      {expanded && (
        <div className="domain-results">
          {domainInsights.domain_analyses.map((analysis, idx) => {
            const r = analysis
            const info = DOMAIN_LABELS[r.domain] || DOMAIN_LABELS.mechanical
            return (
              <div className="domain-card" key={idx}>
                <div className="domain-card-header">
                  <div className="domain-card-title">
                    <span className="domain-dot" style={{ background: info.color }} />
                    <h3>{info.label} Agent</h3>
                  </div>
                  <ConfidenceBar value={r.confidence} />
                </div>

                <div className="domain-hypothesis">
                  <span className="domain-hypothesis-label">Hypothesis</span>
                  <p>{r.root_cause_hypothesis}</p>
                </div>

                <div className="domain-findings">
                  {(r.findings || []).map((f, i) => (
                    <div className="domain-finding" key={i}>
                      <div className="domain-finding-header">
                        <span className="domain-finding-area">{f.area}</span>
                        <SeverityBadge severity={f.severity} />
                      </div>
                      <p className="domain-finding-obs">{f.observation}</p>
                      <p className="domain-finding-evidence">{f.evidence}</p>
                    </div>
                  ))}
                </div>

                {r.recommended_checks?.length > 0 && (
                  <div className="domain-checks">
                    <span className="domain-checks-label">Recommended Checks</span>
                    <ul>
                      {r.recommended_checks.map((check, i) => (
                        <li key={i}>{check}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function FiveWhysSection({ whySteps }) {
  const [expanded, setExpanded] = useState(false)

  if (!whySteps?.length) return null

  return (
    <div className="detailed-analysis">
      <button className="expand-toggle" onClick={() => setExpanded(!expanded)}>
        <span className="toggle-icon">{expanded ? '▼' : '▶'}</span>
        {expanded ? 'Hide' : 'Show'} Detailed 5 Whys Reasoning
      </button>

      {expanded && (
        <div className="whys-timeline">
          {whySteps.map((step) => {
            const stepDocs = filterDocs(step.supporting_documents)
            return (
              <div className="why-step" key={step.step_number}>
                <div className="why-marker">
                  <div className="why-number">{step.step_number}</div>
                  {step.step_number < 5 && <div className="why-line" />}
                </div>
                <div className="why-body">
                  <p className="why-question">{cleanText(step.question)}</p>
                  <p className="why-answer">{cleanText(step.answer)}</p>
                  <div className="why-footer">
                    <EvidenceBadge confidence={step.confidence} answer={step.answer} />
                    {stepDocs.length > 0 && (
                      <div className="why-docs">
                        {stepDocs.map((doc, i) => (
                          <span className="doc-tag" key={i}>{doc}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function RCAResult({ data, domainInsights }) {
  if (!data || !data.result) return null

  const r = data.result.five_whys_analysis || data.result
  const whySteps = r.why_steps || []

  // Use domain_insights embedded in result if not passed separately
  const insights = domainInsights || data.result?.domain_insights

  return (
    <div className="rca-result">

      {/* ══ Fishbone (collapsible, default expanded) ══ */}
      {data.result?.fishbone_analysis && (
        <>
          <div className="section-divider">
            <h3>🦴 Contributing Cause Map (Ishikawa Fishbone)</h3>
          </div>
          <FishboneCanvas
            fishbone={data.result.fishbone_analysis}
            whySteps={whySteps}
          />
        </>
      )}

      {/* ══ Domain Agents + 5 Whys — collapsible details ══ */}
      <div className="section-divider">
        <h3>🔬 Root Cause Reasoning Details</h3>
        <p className="section-subtitle">Expand below to explore domain expert findings and 5 Whys causal chain</p>
      </div>

      <DomainAgentsSection domainInsights={insights} />
      <FiveWhysSection whySteps={whySteps} />

    </div>
  )
}

export default RCAResult
