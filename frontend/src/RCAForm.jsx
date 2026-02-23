import { useState } from 'react'

const INITIAL_STATE = {
  equipment_name: '',
  failure_description: '',
  failure_timestamp: '',
  symptoms: [''],
  error_codes: [''],
  operator_observations: ''
}

function RCAForm({ onResult, onDomainInsights, onStatusChange, onStatusMessage }) {
  const [form, setForm] = useState(INITIAL_STATE)
  const [status, setStatus] = useState(null) // null | 'sending' | 'success' | 'error'
  const [statusMsg, setStatusMsg] = useState('')
  const [statusLog, setStatusLog] = useState([])
  const [includeDomain, setIncludeDomain] = useState(true)

  const handleChange = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }))
  }

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

  const setStatusAll = (s) => {
    setStatus(s)
    onStatusChange?.(s)
  }

  // ── SSE stream reader ──────────────────────────────────────────────────────
  const readSSEStream = async (url, payload, { onStatus, onResult, onError, onDomainInsightsEvt }) => {
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

        try {
          const parsed = JSON.parse(data)
          if (eventType === 'status') onStatus(parsed)
          if (eventType === 'result') onResult(parsed)
          if (eventType === 'error') onError(parsed)
          if (eventType === 'domain_insights' && onDomainInsightsEvt) {
            console.log('[SSE] domain_insights received:', parsed)
            onDomainInsightsEvt(parsed)
          }
        } catch (parseErr) {
          console.warn('[SSE] JSON parse error:', eventType, parseErr, data.slice(0, 200))
        }
      }
    }
  }

  // ── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault()
    setStatusAll('sending')
    onResult?.(null)
    onDomainInsights?.(null)
    setStatusMsg('Connecting to server...')
    setStatusLog([])

    const payload = {
      ...form,
      symptoms: form.symptoms.filter(s => s.trim()),
      error_codes: form.error_codes.filter(c => c.trim())
    }

    try {
      if (includeDomain) {
        await readSSEStream('http://localhost:8000/analyze-integrated-stream', payload, {
          onStatus: (d) => {
            setStatusMsg(d.message)
            setStatusLog(prev => [...prev, d.message])
            onStatusMessage?.(d.message)
          },
          onDomainInsightsEvt: (d) => {
            onDomainInsights?.(d.domain_insights)
            const msg = '🎯 Domain analysis complete — running 5 Whys...'
            setStatusMsg(msg)
            onStatusMessage?.(msg)
          },
          onResult: (d) => {
            onResult?.(d)
            setStatusAll('success')
          },
          onError: (d) => { throw new Error(d.detail || 'Analysis failed') },
        })
      } else {
        await readSSEStream('http://localhost:8000/analyze-stream', payload, {
          onStatus: (d) => {
            setStatusMsg(d.message)
            setStatusLog(prev => [...prev, d.message])
            onStatusMessage?.(d.message)
          },
          onResult: (d) => { onResult?.(d); setStatusAll('success') },
          onError: (d) => { throw new Error(d.detail || 'Analysis failed') },
        })
      }
    } catch (err) {
      console.error(err)
      onResult?.({ error: err.message })
      setStatusAll('error')
    }
  }

  const handleReset = () => {
    setForm(INITIAL_STATE)
    setStatusAll(null)
    onResult?.(null)
    onDomainInsights?.(null)
    setStatusMsg('')
    setStatusLog([])
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

        {/* Symptoms */}
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

        {/* Error Codes */}
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
          <button type="submit" className="btn-submit" disabled={status === 'sending'}>
            {status === 'sending' ? 'Analyzing...' : 'Run RCA Analysis'}
          </button>
          <button type="button" className="btn-reset" onClick={handleReset}>
            Reset
          </button>
        </div>
      </form>

      {/* Minimal sidebar spinner — just the current step, no log */}
      {status === 'sending' && (
        <div className="sidebar-status">
          <div className="status-spinner" />
          <span>{statusMsg}</span>
        </div>
      )}
    </div>
  )
}

export default RCAForm
