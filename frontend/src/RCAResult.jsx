import { useState } from 'react'

/**
 * Clean text coming from the LLM:
 *  1. Strip markdown bold/italic markers (** and *)
 *  2. Remove "SUPPORTING_DOCUMENTS:" lines and everything after them
 *  3. Remove "CONFIDENCE:" lines that leak into the text
 */
function cleanText(raw) {
  if (!raw) return ''
  let text = raw

  // Remove SUPPORTING_DOCUMENTS section (and everything after it in the same block)
  text = text.replace(/\*{0,2}SUPPORTING[_ ]DOCUMENTS:?\*{0,2}[^\n]*/gi, '')

  // Remove CONFIDENCE lines that leak in
  text = text.replace(/\*{0,2}CONFIDENCE:?\*{0,2}\s*\d+%?/gi, '')

  // Strip markdown bold ** and italic *
  text = text.replace(/\*{1,2}([^*]+?)\*{1,2}/g, '$1')

  // Clean leftover double newlines
  text = text.replace(/\n{3,}/g, '\n\n').trim()

  return text
}

/**
 * Filter out garbage doc tags (fragments like "5", "7b", "7m)", "Items 4", single letters, etc.)
 * Only keep tags that look like real document names (>10 chars and contain a letter sequence).
 */
function filterDocs(docs) {
  if (!docs) return []
  return docs.filter(d => {
    const trimmed = d.trim().replace(/^[-–\s]+/, '')
    return trimmed.length > 10 && /[a-zA-Z]{3,}/.test(trimmed)
  })
}

/**
 * Determine evidence badge based on confidence and answer text
 */
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

/**
 * Extract immediate action items from 5 Whys steps
 */
function extractActionItems(whySteps) {
  const actions = []

  whySteps.forEach(step => {
    const text = step.answer.toLowerCase()

    // Extract check/inspect/verify actions
    if (text.includes('check') || text.includes('inspect') || text.includes('verify')) {
      const sentences = step.answer.split(/[.!?]/)
      sentences.forEach(s => {
        if (s.toLowerCase().includes('check') || s.toLowerCase().includes('inspect') || s.toLowerCase().includes('verify')) {
          actions.push(s.trim())
        }
      })
    }
  })

  return actions.slice(0, 3) // Top 3 actions
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

function RCAResult({ data }) {
  const [whysExpanded, setWhysExpanded] = useState(false)

  // Handle both old format (5 Whys only) and new format (integrated pipeline)
  const r = data.result.five_whys_analysis || data.result
  const validDocs = filterDocs(r.documents_used)
  const actionItems = extractActionItems(r.why_steps || [])

  // Extract "why it tripped" from Why #1
  const whyItTripped = r.why_steps?.[0]?.answer || r.root_cause

  return (
    <div className="rca-result">

      {/* ══════════════════════════════════════════════════════
          TOP SUMMARY CARD (Operator-Friendly)
          ══════════════════════════════════════════════════════ */}
      <div className="summary-card-top">
        <div className="summary-section">
          <h3 className="summary-label">MOST LIKELY CAUSE</h3>
          <p className="summary-main-text">{cleanText(r.root_cause)}</p>
          <EvidenceBadge
            confidence={r.root_cause_confidence}
            answer={r.root_cause}
          />
        </div>

        <div className="summary-section">
          <h3 className="summary-label">WHY IT TRIPPED</h3>
          <p className="summary-text">{cleanText(whyItTripped)}</p>
        </div>

        {actionItems.length > 0 && (
          <div className="summary-section">
            <h3 className="summary-label">WHAT TO CHECK NOW</h3>
            <ul className="action-checklist">
              {actionItems.map((action, i) => (
                <li key={i}>{cleanText(action)}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="summary-meta">
          <span>{data.equipment_name}</span>
          <span className="dot" />
          <span>{data.execution_time_seconds}s analysis</span>
          <span className="dot" />
          <span>{validDocs.length || 0} docs</span>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════
          DETAILED ANALYSIS (Collapsible)
          ══════════════════════════════════════════════════════ */}
      <div className="detailed-analysis">
        <button
          className="expand-toggle"
          onClick={() => setWhysExpanded(!whysExpanded)}
        >
          <span className="toggle-icon">{whysExpanded ? '▼' : '▶'}</span>
          {whysExpanded ? 'Hide' : 'Show'} Detailed 5 Whys Analysis
        </button>

        {whysExpanded && (
          <div className="whys-timeline">
            {r.why_steps?.map((step) => {
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
                      <EvidenceBadge
                        confidence={step.confidence}
                        answer={step.answer}
                      />
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

      {/* ── Documents Referenced (Collapsed by default) ── */}
      {validDocs.length > 0 && whysExpanded && (
        <div className="docs-section">
          <h3>Documents Referenced</h3>
          <div className="doc-list">
            {validDocs.map((doc, i) => (
              <span className="doc-tag" key={i}>{doc}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default RCAResult
