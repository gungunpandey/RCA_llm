function DomainSummary({ insights }) {
    if (!insights || !insights.key_findings || insights.key_findings.length === 0) {
        return null
    }

    return (
        <div className="domain-summary-card">
            <div className="domain-summary-header">
                <h3>🔬 Domain Expert Analysis Summary</h3>
                <div className="domain-meta">
                    <span>{insights.agents_analyzed?.join(', ').toUpperCase() || 'N/A'} EXPERTS</span>
                    <span className="dot" />
                    <span>Confidence: {Math.round((insights.overall_confidence || 0) * 100)}%</span>
                </div>
            </div>

            {/* Key Findings */}
            <div className="domain-section">
                <h4>Key Findings</h4>
                <ul className="domain-findings-list">
                    {insights.key_findings.slice(0, 5).map((finding, i) => (
                        <li key={i} className="domain-finding-item">
                            {finding}
                        </li>
                    ))}
                </ul>
            </div>

            {/* Suspected Root Causes */}
            {insights.suspected_root_causes && insights.suspected_root_causes.length > 0 && (
                <div className="domain-section">
                    <h4>Suspected Root Causes (from domain experts)</h4>
                    <ul className="domain-hypotheses-list">
                        {insights.suspected_root_causes.map((cause, i) => (
                            <li key={i} className="domain-hypothesis-item">
                                <span className="domain-badge">{cause.domain?.toUpperCase()}</span>
                                <span className="hypothesis-text">{cause.hypothesis}</span>
                                <span className="hypothesis-confidence">{Math.round((cause.confidence || 0) * 100)}%</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Recommended Checks */}
            {insights.recommended_checks && insights.recommended_checks.length > 0 && (
                <div className="domain-section">
                    <h4>Recommended Verification Checks</h4>
                    <ul className="domain-checks-list">
                        {insights.recommended_checks.slice(0, 5).map((check, i) => (
                            <li key={i}>{check}</li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    )
}

export default DomainSummary
