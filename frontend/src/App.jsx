import { useState } from 'react'
import RCAForm from './RCAForm'
import RCAResult from './RCAResult'
import DomainSummary from './DomainSummary'

function EmptyState() {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">🔍</div>
      <h2>Ready to Analyze</h2>
      <p>Fill in the equipment failure details on the left and click <strong>Run RCA Analysis</strong> to see the full root cause breakdown here.</p>
      <ul className="empty-state-features">
        <li>⚡ Domain expert agents</li>
        <li>🦴 Ishikawa fishbone diagram</li>
        <li>📋 5 Whys causal chain</li>
        <li>📊 Evidence-graded causes</li>
      </ul>
    </div>
  )
}

function App() {
  const [result, setResult] = useState(null)
  const [domainInsights, setDomainInsights] = useState(null)
  const [analysisStatus, setAnalysisStatus] = useState(null)  // null | 'sending' | 'success' | 'error'
  const [statusLog, setStatusLog] = useState([])
  const [currentStatus, setCurrentStatus] = useState('')

  const handleStatusMessage = (msg) => {
    setCurrentStatus(msg)
    setStatusLog(prev => [...prev, msg])
  }

  const handleStatusChange = (s) => {
    setAnalysisStatus(s)
    if (s === null) { setResult(null); setDomainInsights(null); setStatusLog([]); setCurrentStatus('') }
  }

  return (
    <div className="app">
      {/* ── Left Sidebar: header + form ── */}
      <aside className="app-sidebar">
        <header className="app-header">
          <div className="app-logo">⚡ RCA</div>
          <h1>Root Cause Analysis</h1>
          <p>AI-powered failure diagnostics</p>
        </header>
        <RCAForm
          onResult={(r) => { setResult(r); if (r) setStatusLog([]); }}
          onDomainInsights={setDomainInsights}
          onStatusChange={handleStatusChange}
          onStatusMessage={handleStatusMessage}
        />
      </aside>

      {/* ── Right Main: results canvas ── */}
      <main className="app-main">
        {analysisStatus === null && !result && <EmptyState />}

        {/* ── Live Status Panel (right panel, shown during analysis) ── */}
        {analysisStatus === 'sending' && (
          <div className="main-status-panel">
            <div className="main-status-header">
              <div className="status-spinner" />
              <span className="main-status-current">{currentStatus || 'Connecting to server…'}</span>
            </div>
            {statusLog.length > 1 && (
              <div className="main-status-log">
                {statusLog.slice(0, -1).map((msg, i) => (
                  <div className="main-status-log-item" key={i}>
                    <span className="status-check">&#10003;</span>
                    <span>{msg}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Progressive domain insights appear first */}
        {domainInsights && (
          <DomainSummary insights={domainInsights} />
        )}

        {/* While 5 Whys is running, show divider */}
        {domainInsights && analysisStatus === 'sending' && (
          <div className="section-divider">
            <h3>🎯 Main Root Cause Analysis (5 Whys)</h3>
            <p className="section-subtitle">Running 5 Whys analysis using domain insights...</p>
          </div>
        )}

        {/* Final analysis result */}
        {analysisStatus === 'success' && result && (
          <>
            {domainInsights && (
              <div className="section-divider">
                <h3>🎯 Main Root Cause Analysis (5 Whys)</h3>
                <p className="section-subtitle">Building on domain expert insights...</p>
              </div>
            )}
            <RCAResult data={result} />
          </>
        )}

        {analysisStatus === 'error' && result?.error && (
          <div className="result-box error" style={{ margin: 0 }}>
            <strong>Error:</strong> {result.error}
            <p>Make sure the backend server is running on port 8000.</p>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
