import { useState } from 'react'

/**
 * Clean text coming from the LLM — strip markdown bold/italic markers.
 */
function cleanText(raw) {
    if (!raw) return ''
    return raw
        .replace(/\*{0,2}SUPPORTING[_ ]DOCUMENTS:?\*{0,2}[^\n]*/gi, '')
        .replace(/\*{0,2}CONFIDENCE:?\*{0,2}\s*\d+%?/gi, '')
        .replace(/\*{1,2}([^*]+?)\*{1,2}/g, '$1')
        .replace(/\n{3,}/g, '\n\n')
        .trim()
}

/**
 * Build CSV string from report data.
 */
function buildCSV(data) {
    const r = data.result?.five_whys_analysis || data.result || {}
    const meta = data._formMeta || {}

    const rows = [
        ['RCA Report'],
        [],
        ['Department', meta.department || ''],
        ['Equipment name / Place of occurrence', data.equipment_name || ''],
        ['Occurrence (From)', meta.occurrence_from || ''],
        ['Occurrence (To)', meta.occurrence_to || ''],
        ['Total down time', meta.total_downtime || ''],
        ['Production loss', meta.production_loss || ''],
        ['Impact of top line', meta.impact_top_line || ''],
        ['Problem statement', cleanText(data.failure_description || r.failure_description || '')],
        [],
        ['5 Why Analysis'],
    ]

    const whySteps = r.why_steps || []
    whySteps.forEach((step, i) => {
        rows.push([`Why ${i + 1}`, cleanText(step.answer)])
    })

    rows.push([])
    rows.push(['Root Cause', cleanText(r.root_cause || '')])
    rows.push([])
    rows.push(['Corrective and Preventive Actions (CAPA)'])
    rows.push(['S No', 'Preventive action to be taken', 'Responsibility', 'Target end date'])

    const actions = r.corrective_actions || []
    if (actions.length === 0) {
        // Add 3 empty rows for manual fill
        rows.push(['1', '', '', ''])
        rows.push(['2', '', '', ''])
        rows.push(['3', '', '', ''])
    } else {
        actions.slice(0, 5).forEach((action, i) => {
            rows.push([i + 1, cleanText(action), '', ''])
        })
    }

    return rows
        .map(cols =>
            cols
                .map(cell => `"${String(cell).replace(/"/g, '""')}"`)
                .join(',')
        )
        .join('\n')
}

function downloadCSV(data) {
    const csv = buildCSV(data)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `RCA_Report_${data.equipment_name || 'report'}_${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)
}

export default function RCAReportTable({ data }) {
    const [capaRows, setCapaRows] = useState([
        { action: '', responsibility: '', targetDate: '' },
        { action: '', responsibility: '', targetDate: '' },
        { action: '', responsibility: '', targetDate: '' },
    ])

    if (!data || !data.result) return null

    const r = data.result?.five_whys_analysis || data.result
    const meta = data._formMeta || {}
    const whySteps = r.why_steps || []
    const actions = r.corrective_actions || []

    // Pre-fill CAPA rows from corrective_actions but allow editing
    const initialCapa = actions.length > 0
        ? actions.slice(0, 5).map(a => ({ action: cleanText(a), responsibility: '', targetDate: '' }))
        : capaRows

    const handleCapaChange = (idx, field, value) => {
        setCapaRows(prev => {
            const updated = [...prev]
            updated[idx] = { ...updated[idx], [field]: value }
            return updated
        })
    }

    const [localCapa, setLocalCapa] = useState(
        actions.length > 0
            ? actions.slice(0, 5).map(a => ({ action: cleanText(a), responsibility: '', targetDate: '' }))
            : [
                { action: '', responsibility: '', targetDate: '' },
                { action: '', responsibility: '', targetDate: '' },
                { action: '', responsibility: '', targetDate: '' },
            ]
    )

    const handleLocalCapaChange = (idx, field, value) => {
        setLocalCapa(prev => {
            const updated = [...prev]
            updated[idx] = { ...updated[idx], [field]: value }
            return updated
        })
    }

    const handleDownload = () => {
        const exportData = { ...data, _localCapa: localCapa }
        downloadCSV(exportData)
    }

    return (
        <div className="rca-report-table-wrapper">
            {/* Header row */}
            <div className="rca-report-header-bar">
                <h2 className="rca-report-title">RCA Report</h2>
                <button className="btn-download-csv" onClick={handleDownload}>
                    ⬇ Download CSV
                </button>
            </div>

            <table className="rca-report-table">
                <tbody>

                    {/* Row 1: Department | Total down time */}
                    <tr>
                        <td className="rca-label">Department</td>
                        <td className="rca-value">{meta.department || '—'}</td>
                        <td className="rca-label">Total down time</td>
                        <td className="rca-value">{meta.total_downtime || '—'}</td>
                    </tr>

                    {/* Row 2: Equipment | Production loss */}
                    <tr>
                        <td className="rca-label">Equipment name / Place of occurrence</td>
                        <td className="rca-value">{data.equipment_name || '—'}</td>
                        <td className="rca-label">Production loss</td>
                        <td className="rca-value">{meta.production_loss || '—'}</td>
                    </tr>

                    {/* Row 3: Occurrence From | Impact of top line */}
                    <tr>
                        <td className="rca-label">Occurrence — Date &amp; time (From)</td>
                        <td className="rca-value">{meta.occurrence_from || '—'}</td>
                        <td className="rca-label">Impact of top line</td>
                        <td className="rca-value">{meta.impact_top_line || '—'}</td>
                    </tr>

                    {/* Row 4: Occurrence To | Team list (blank placeholder) */}
                    <tr>
                        <td className="rca-label">Occurrence — Date &amp; time (To)</td>
                        <td className="rca-value">{meta.occurrence_to || '—'}</td>
                        <td className="rca-label">Team list</td>
                        <td className="rca-value rca-value--muted">—</td>
                    </tr>

                    {/* Row 5: Problem statement (full width) */}
                    <tr>
                        <td className="rca-label">Problem statement</td>
                        <td colSpan={3} className="rca-value">{meta.failure_description || '—'}</td>
                    </tr>

                    {/* ── 5 Why Analysis section header ── */}
                    <tr>
                        <td colSpan={4} className="rca-section-header">5 Why Analysis</td>
                    </tr>

                    {/* Why steps */}
                    {whySteps.length > 0
                        ? whySteps.map((step, i) => (
                            <tr key={i}>
                                <td className="rca-why-label">Why {i + 1}</td>
                                <td colSpan={3} className="rca-value">{cleanText(step.answer)}</td>
                            </tr>
                        ))
                        : [1, 2, 3, 4, 5].map(n => (
                            <tr key={n}>
                                <td className="rca-why-label">Why {n}</td>
                                <td colSpan={3} className="rca-value rca-value--muted"></td>
                            </tr>
                        ))}

                    {/* Root Cause */}
                    <tr>
                        <td className="rca-label rca-label--highlight">Root Cause</td>
                        <td colSpan={3} className="rca-value rca-value--highlight">{cleanText(r.root_cause || '—')}</td>
                    </tr>

                    {/* ── CAPA section header ── */}
                    <tr>
                        <td colSpan={4} className="rca-section-header">Corrective and Preventive Actions (CAPA)</td>
                    </tr>

                    {/* CAPA table subheaders */}
                    <tr className="rca-capa-header">
                        <td className="rca-label">S No</td>
                        <td className="rca-label">Preventive action to be taken</td>
                        <td className="rca-label">Responsibility</td>
                        <td className="rca-label">Target end date</td>
                    </tr>

                    {/* CAPA rows */}
                    {localCapa.map((row, i) => (
                        <tr key={i} className="rca-capa-row">
                            <td className="rca-capa-num">{i + 1}</td>
                            <td>
                                <input
                                    className="rca-capa-input"
                                    type="text"
                                    value={row.action}
                                    onChange={e => handleLocalCapaChange(i, 'action', e.target.value)}
                                    placeholder="Describe action…"
                                />
                            </td>
                            <td>
                                <input
                                    className="rca-capa-input"
                                    type="text"
                                    value={row.responsibility}
                                    onChange={e => handleLocalCapaChange(i, 'responsibility', e.target.value)}
                                    placeholder="Owner"
                                />
                            </td>
                            <td>
                                <input
                                    className="rca-capa-input"
                                    type="text"
                                    value={row.targetDate}
                                    onChange={e => handleLocalCapaChange(i, 'targetDate', e.target.value)}
                                    placeholder="DD/MM/YYYY"
                                />
                            </td>
                        </tr>
                    ))}

                </tbody>
            </table>

            <p className="rca-footer-note">Strictly private and confidential</p>
        </div>
    )
}
