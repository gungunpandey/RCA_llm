function SeverityBadge({ severity }) {
  const colors = {
    critical: { bg: '#3b1a1a', border: '#d44', text: '#f88' },
    warning:  { bg: '#2a2a1a', border: '#bb8800', text: '#fbbf24' },
    normal:   { bg: '#1a2a1a', border: '#336633', text: '#34d399' },
  }
  const c = colors[severity] || colors.warning

  return (
    <span
      className="severity-badge"
      style={{ background: c.bg, borderColor: c.border, color: c.text }}
    >
      {severity}
    </span>
  )
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

const DOMAIN_LABELS = {
  mechanical: { label: 'Mechanical', color: '#f97316' },
  electrical: { label: 'Electrical', color: '#3b82f6' },
  process:    { label: 'Process',    color: '#a855f7' },
}

function DomainResult({ data }) {
  if (!data || !data.domain_analyses || data.domain_analyses.length === 0) {
    return null
  }

  return (
    <div className="domain-results">
      <div className="domain-results-header">
        <h2>Domain Expert Analysis</h2>
        <span className="domain-agents-count">
          {data.agents_used.length} agent{data.agents_used.length > 1 ? 's' : ''} deployed
        </span>
      </div>

      {data.domain_analyses.map((analysis, idx) => {
        const r = analysis.result
        const info = DOMAIN_LABELS[r.domain] || DOMAIN_LABELS.mechanical

        return (
          <div className="domain-card" key={idx}>
            {/* Agent header */}
            <div className="domain-card-header">
              <div className="domain-card-title">
                <span
                  className="domain-dot"
                  style={{ background: info.color }}
                />
                <h3>{info.label} Agent</h3>
              </div>
              <ConfidenceBar value={r.confidence} />
            </div>

            {/* Hypothesis */}
            <div className="domain-hypothesis">
              <span className="domain-hypothesis-label">Hypothesis</span>
              <p>{r.root_cause_hypothesis}</p>
            </div>

            {/* Findings */}
            <div className="domain-findings">
              {r.findings.map((f, i) => (
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

            {/* Recommended checks */}
            {r.recommended_checks && r.recommended_checks.length > 0 && (
              <div className="domain-checks">
                <span className="domain-checks-label">Recommended Checks</span>
                <ul>
                  {r.recommended_checks.map((check, i) => (
                    <li key={i}>{check}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Footer meta */}
            <div className="domain-card-footer">
              <span>{analysis.execution_time_seconds}s</span>
              <span>{r.documents_used?.length || 0} docs</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default DomainResult
