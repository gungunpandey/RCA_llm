import { useState } from 'react'
import RCAResult from './RCAResult'
import DomainResult from './DomainResult'
import DomainSummary from './DomainSummary'

const INITIAL_STATE = {
  equipment_name: '',
  failure_description: '',
  failure_timestamp: '',
  symptoms: [''],
  error_codes: [''],
  operator_observations: ''
}

function RCAForm() {
  const [form, setForm] = useState(INITIAL_STATE)
  const [status, setStatus] = useState(null) // null | 'sending' | 'success' | 'error'
  const [result, setResult] = useState(null)
  const [statusMsg, setStatusMsg] = useState('')
  const [statusLog, setStatusLog] = useState([])
  const [includeDomain, setIncludeDomain] = useState(true)
  const [domainStatus, setDomainStatus] = useState(null) // null | 'sending' | 'success' | 'error'
  const [domainResult, setDomainResult] = useState(null)
  const [domainStatusMsg, setDomainStatusMsg] = useState('')

  const handleChange = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  // --- Dynamic list helpers (symptoms & error_codes) ---
  const handleListChange = (field, index, value) => {
    setForm(prev => {
      const updated = [...prev[field]]
      updated[index] = value
      return { ...prev, [field]: updated }
    })
  }

  const addListItem = (field) => {
    setForm(prev => ({ ...prev, [field]: [...prev[field], ''] }))
  }

  const removeListItem = (field, index) => {
    setForm(prev => {
      const updated = prev[field].filter((_, i) => i !== index)
      return { ...prev, [field]: updated.length ? updated : [''] }
    })
  }

  // --- SSE stream reader (reusable for both endpoints) ---
  const readSSEStream = async (url, payload, { onStatus, onResult, onError }) => {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!res.ok) throw new Error(`Server error: ${res.status}`)

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop()

      for (const part of parts) {
        const lines = part.trim().split('\n')
        let eventType = 'message'
        let data = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7)
          if (line.startsWith('data: ')) data = line.slice(6)
        }
        if (!data) continue

        if (eventType === 'status') onStatus(JSON.parse(data))
        if (eventType === 'result') onResult(JSON.parse(data))
        if (eventType === 'error') onError(JSON.parse(data))
      }
    }
  }

  // --- Submit via SSE stream (INTEGRATED PIPELINE) ---
  const handleSubmit = async (e) => {
    e.preventDefault()
    setStatus('sending')
    setResult(null)
    setDomainResult(null)
    setDomainStatus(null)
    setStatusMsg('Connecting to server...')
    setStatusLog([])

    const payload = {
      ...form,
      symptoms: form.symptoms.filter(s => s.trim()),
      error_codes: form.error_codes.filter(c => c.trim())
    }

    try {
      if (includeDomain) {
        // NEW: Use integrated pipeline (domain agents → 5 Whys)
        await readSSEStream('http://localhost:8000/analyze-integrated-stream', payload, {
          onStatus: (d) => {
            const msg = d.message
            setStatusMsg(msg)
            setStatusLog(prev => [...prev, msg])

            // Detect when domain analysis completes and 5 Whys starts
            if (msg.includes('Domain analysis complete')) {
              setDomainStatus('success')
            }
          },
          onResult: (d) => {
            // Integrated result contains both domain insights and 5 Whys
            setResult(d)
            setStatus('success')

            // Extract domain insights for separate display
            if (d.result && d.result.domain_insights) {
              setDomainResult({
                status: 'success',
                result: d.result.domain_insights
              })
            }
          },
          onError: (d) => { throw new Error(d.detail || 'Analysis failed') },
        })
      } else {
        // Fallback: Use standalone 5 Whys (no domain analysis)
        await readSSEStream('http://localhost:8000/analyze-stream', payload, {
          onStatus: (d) => { setStatusMsg(d.message); setStatusLog(prev => [...prev, d.message]) },
          onResult: (d) => { setResult(d); setStatus('success') },
          onError: (d) => { throw new Error(d.detail || 'Analysis failed') },
        })
      }
    } catch (err) {
      console.error(err)
      setResult({ error: err.message })
      setStatus('error')
    }
  }

  const handleReset = () => {
    setForm(INITIAL_STATE)
    setStatus(null)
    setResult(null)
    setStatusMsg('')
    setStatusLog([])
    setDomainStatus(null)
    setDomainResult(null)
    setDomainStatusMsg('')
  }

  return (
    <div className="form-container">
      <form onSubmit={handleSubmit}>

        {/* Equipment Name */}
        <div className="field">
          <label htmlFor="equipment_name">Equipment Name</label>
          <input
            id="equipment_name"
            type="text"
            placeholder="e.g. ID&HR Fan"
            value={form.equipment_name}
            onChange={e => handleChange('equipment_name', e.target.value)}
            required
          />
        </div>

        {/* Failure Description */}
        <div className="field">
          <label htmlFor="failure_description">Failure Description</label>
          <textarea
            id="failure_description"
            rows={3}
            placeholder="e.g. Fan motor stopped suddenly during operation"
            value={form.failure_description}
            onChange={e => handleChange('failure_description', e.target.value)}
            required
          />
        </div>

        {/* Failure Timestamp */}
        <div className="field">
          <label htmlFor="failure_timestamp">Failure Timestamp</label>
          <input
            id="failure_timestamp"
            type="text"
            placeholder="e.g. 2026-02-06T15:30:00Z"
            value={form.failure_timestamp}
            onChange={e => handleChange('failure_timestamp', e.target.value)}
          />
        </div>

        {/* Symptoms (dynamic list) */}
        <div className="field">
          <label>Symptoms</label>
          {form.symptoms.map((symptom, i) => (
            <div className="list-row" key={i}>
              <input
                type="text"
                placeholder={`Symptom ${i + 1}, e.g. motor overheating`}
                value={symptom}
                onChange={e => handleListChange('symptoms', i, e.target.value)}
              />
              <button
                type="button"
                className="btn-icon remove"
                onClick={() => removeListItem('symptoms', i)}
                title="Remove"
              >
                &times;
              </button>
            </div>
          ))}
          <button type="button" className="btn-add" onClick={() => addListItem('symptoms')}>
            + Add Symptom
          </button>
        </div>

        {/* Error Codes (dynamic list) */}
        <div className="field">
          <label>Error Codes</label>
          {form.error_codes.map((code, i) => (
            <div className="list-row" key={i}>
              <input
                type="text"
                placeholder={`Code ${i + 1}, e.g. E401`}
                value={code}
                onChange={e => handleListChange('error_codes', i, e.target.value)}
              />
              <button
                type="button"
                className="btn-icon remove"
                onClick={() => removeListItem('error_codes', i)}
                title="Remove"
              >
                &times;
              </button>
            </div>
          ))}
          <button type="button" className="btn-add" onClick={() => addListItem('error_codes')}>
            + Add Error Code
          </button>
        </div>

        {/* Operator Observations */}
        <div className="field">
          <label htmlFor="operator_observations">Operator Observations</label>
          <textarea
            id="operator_observations"
            rows={3}
            placeholder="e.g. Noticed burning smell before shutdown"
            value={form.operator_observations}
            onChange={e => handleChange('operator_observations', e.target.value)}
          />
        </div>

        {/* Domain toggle */}
        <div className="field toggle-field">
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={includeDomain}
              onChange={e => setIncludeDomain(e.target.checked)}
            />
            <span>Include Domain Expert Analysis</span>
          </label>
          <span className="toggle-hint">Runs specialized mechanical, electrical, or process agents</span>
        </div>

        {/* Actions */}
        <div className="form-actions">
          <button type="submit" className="btn-submit" disabled={status === 'sending' || domainStatus === 'sending'}>
            {status === 'sending' || domainStatus === 'sending' ? 'Analyzing...' : 'Run RCA Analysis'}
          </button>
          <button type="button" className="btn-reset" onClick={handleReset}>
            Reset
          </button>
        </div>
      </form>

      {/* Live Status Updates */}
      {status === 'sending' && (
        <div className="status-panel">
          <div className="status-current">
            <div className="status-spinner" />
            <span>{statusMsg}</span>
          </div>
          {statusLog.length > 1 && (
            <div className="status-log">
              {statusLog.slice(0, -1).map((msg, i) => (
                <div className="status-log-item" key={i}>
                  <span className="status-check">&#10003;</span>
                  {msg}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {status === 'error' && result && (
        <div className="result-box error">
          <strong>Error:</strong> {result.error}
          <p>Make sure the backend server is running on port 8000.</p>
        </div>
      )}

      {/* Show domain summary FIRST (if available) */}
      {status === 'success' && result && result.result && result.result.domain_insights && (
        <DomainSummary insights={result.result.domain_insights} />
      )}

      {/* Then show 5 Whys results */}
      {status === 'success' && result && (
        <>
          {result.result && result.result.domain_insights && (
            <div className="section-divider">
              <h3>🎯 Main Root Cause Analysis (5 Whys)</h3>
              <p className="section-subtitle">Building on domain expert insights...</p>
            </div>
          )}
          <RCAResult data={result} />
        </>
      )}

      {/* Domain analysis status */}
      {domainStatus === 'sending' && (
        <div className="status-panel">
          <div className="status-current">
            <div className="status-spinner" />
            <span>{domainStatusMsg}</span>
          </div>
        </div>
      )}

      {domainStatus === 'error' && domainResult && (
        <div className="result-box error">
          <strong>Domain Analysis Error:</strong> {domainResult.error}
        </div>
      )}

      {/* Old domain result display (keep for backward compatibility with old endpoint) */}
      {domainStatus === 'success' && domainResult && !result?.result?.domain_insights && (
        <DomainResult data={domainResult} />
      )}
    </div>
  )
}

export default RCAForm
