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


function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100)
  const color =
    pct >= 85 ? '#34d399' :
    pct >= 60 ? '#fbbf24' :
    '#f87171'

  return (
    <div className="confidence-bar">
      <div className="confidence-track">
        <div
          className="confidence-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="confidence-label" style={{ color }}>{pct}%</span>
    </div>
  )
}

function RCAResult({ data }) {
  const r = data.result
  const validDocs = filterDocs(r.documents_used)

  return (
    <div className="rca-result">

      {/* ── Header ── */}
      <div className="rca-header">
        <div className="rca-header-left">
          <h2>{data.equipment_name}</h2>
          <span className="rca-badge">{data.analysis_type.replace('_', ' ')}</span>
        </div>
        <div className="rca-meta">
          <span>{data.execution_time_seconds}s</span>
          <span className="dot" />
          <span>{validDocs.length || 0} docs referenced</span>
        </div>
      </div>

      {/* ── Root Cause Card ── */}
      <div className="root-cause-card">
        <div className="root-cause-header">
          <h3>Root Cause</h3>
          <ConfidenceBar value={r.root_cause_confidence} />
        </div>
        <p className="root-cause-text">{cleanText(r.root_cause)}</p>
      </div>

      {/* ── 5 Why Steps ── */}
      <div className="whys-section">
        <h3>5 Whys Analysis</h3>
        <div className="whys-timeline">
          {r.why_steps.map((step) => {
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
                    <ConfidenceBar value={step.confidence} />
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
      </div>

      {/* ── Documents Used ── */}
      {validDocs.length > 0 && (
        <div className="docs-section">
          <h3>Documents Referenced</h3>
          <div className="doc-list">
            {validDocs.map((doc, i) => (
              <span className="doc-tag" key={i}>{doc}</span>
            ))}
          </div>
        </div>
      )}

      {/* ── Corrective Actions ── */}
      {r.corrective_actions?.length > 0 && (
        <div className="actions-section">
          <h3>Corrective Actions</h3>
          <ol>
            {r.corrective_actions.map((action, i) => (
              <li key={i}>{cleanText(action)}</li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}

export default RCAResult
