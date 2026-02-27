import { useState } from 'react'
import RCAForm from './RCAForm'
import RCAResult from './RCAResult'
import RCAReportTable from './RCAReportTable'

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
          onResult={(r) => { setResult(r); if (r) setStatusLog([]) }}
          onDomainInsights={setDomainInsights}
          onStatusChange={handleStatusChange}
          onStatusMessage={handleStatusMessage}
        />
      </aside>

      {/* ── Right Main: results canvas ── */}
      <main className="app-main">
        {analysisStatus === null && !result && <EmptyState />}

        {/* ── Live Status Panel (shown during analysis only) ── */}
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

        {/* ── SUCCESS: render everything together in correct order ── */}
        {analysisStatus === 'success' && result && (
          <>
            {/* 1. Final RCA Report Table (upfront) */}
            <RCAReportTable data={result} />

            {/* 2. Fishbone diagram (with collapse) — rendered inside RCAResult */}
            {/* 3. Domain + 5 Whys details (with expand) — rendered inside RCAResult */}
            <RCAResult data={result} domainInsights={domainInsights} />
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
