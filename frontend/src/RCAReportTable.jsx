import { useState } from 'react'
import { jsPDF } from 'jspdf'

// ── Text helpers ──────────────────────────────────────────────────────────────

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
 * Strips non-Latin characters and converts smart quotes/dashes.
 * jsPDF's base fonts completely corrupt text if they hit CJK characters.
 */
function sanitizeForPDF(raw) {
    if (!raw) return ''
    return String(raw)
        .replace(/[\u2018\u2019]/g, "'")
        .replace(/[\u201C\u201D]/g, '"')
        .replace(/[\u2013\u2014]/g, '-')
        .replace(/[\u2026]/g, '...')
        .replace(/[^\x00-\xFF]/g, '') // Keep only ASCII and Latin-1 supplement
}

/**
 * Produce a report-card summary of a verbose LLM why-step answer.
 *
 * Strategy (character-budget):
 *   1. Always include the FIRST complete sentence (the direct answer to "why").
 *   2. Add more complete sentences one by one, stopping when the running total
 *      would exceed CHAR_BUDGET (~220 chars ≈ 2-3 visible lines in the table).
 *   3. Append '…' only if we omitted sentences because of the budget.
 *   4. If the answer is already short, show it entirely with no truncation.
 *
 * The FULL original text is always preserved in the hidden reasoning panel.
 */
const CHAR_BUDGET = 220

function condenseText(raw) {
    const text = cleanText(raw)
    if (!text) return ''

    // Split into complete sentences on ., !, ? delimiters.
    const rawSentences = text.match(/[^.!?]*[.!?]+(?=\s|$)/g) || [text]
    const sentences = rawSentences.map(s => s.trim()).filter(s => s.length > 4)

    if (sentences.length === 0) return text.trim()

    // Always include the first sentence (core "why" answer), regardless of length.
    let result = sentences[0]

    // Add subsequent sentences only while we stay within the character budget.
    for (let i = 1; i < sentences.length; i++) {
        const candidate = result + ' ' + sentences[i]
        if (candidate.length > CHAR_BUDGET) break
        result = candidate
    }

    // Add '…' only when we actually omitted sentences due to the budget.
    const hadMore = text.trim().length > result.length + 5
    return result.trim() + (hadMore ? '…' : '')
}

// ── CSV export ────────────────────────────────────────────────────────────────

function buildCSVRows(data, localCapa) {
    const r = data.result?.five_whys_analysis || data.result || {}
    const meta = data._formMeta || {}
    const whySteps = r.why_steps || []

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
        ['Problem statement', meta.failure_description || ''],
        [],
        ['5 Why Analysis'],
        ...whySteps.map((step, i) => [`Why ${i + 1}`, step.answer_summary || condenseText(step.answer)]),
        [],
        ['Root Cause', cleanText(r.root_cause || '')],
        [],
        ['Corrective and Preventive Actions (CAPA)'],
        ['S No', 'Preventive action to be taken', 'Responsibility', 'Target end date'],
        ...localCapa.map((row, i) => [i + 1, row.action, row.responsibility, row.targetDate]),
    ]

    return rows
        .map(cols => cols.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
        .join('\n')
}

function downloadCSV(data, localCapa) {
    const csv = buildCSVRows(data, localCapa)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `RCA_Report_${data.equipment_name || 'report'}_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
}

// ── PDF export ────────────────────────────────────────────────────────────────

function downloadPDF(data, localCapa) {
    const doc = new jsPDF({ unit: 'mm', format: 'a4' })
    const r = data.result?.five_whys_analysis || data.result || {}
    const meta = data._formMeta || {}
    const whySteps = r.why_steps || []

    const PAGE_W = 210
    const PAGE_H = 297
    const M = 12              // margin
    const TW = PAGE_W - M * 2 // total usable width = 186mm

    // Column sizes for the 4-column meta grid (label | val | label | val)
    const LBL = 42            // label column width
    const HALF = TW / 2       // each pair occupies 93mm
    const VAL = HALF - LBL    // value width = 51mm

    let y = M

    // Colours
    const C = {
        dark: [18, 20, 28],
        lbl: [26, 29, 39],
        val: [18, 20, 28],
        white: [255, 255, 255],
        muted: [150, 155, 175],
        blue: [125, 168, 255],
        red: [220, 60, 60],
        redDark: [32, 15, 15],
        rcBg: [23, 32, 44],
        border: [42, 45, 58],
        pink: [220, 120, 160],
        pinkTxt: [30, 10, 20],
    }

    // Fill page background
    doc.setFillColor(...C.dark)
    doc.rect(0, 0, PAGE_W, PAGE_H, 'F')

    function checkPage(need = 12) {
        if (y + need > PAGE_H - M) {
            doc.addPage()
            doc.setFillColor(...C.dark)
            doc.rect(0, 0, PAGE_W, PAGE_H, 'F')
            y = M
        }
    }

    /** Bordered+filled rectangle */
    function rect(x, yr, w, h, fill) {
        doc.setFillColor(...fill)
        doc.setDrawColor(...C.border)
        doc.rect(x, yr, w, h, 'F')
        doc.rect(x, yr, w, h)
    }

    /** Safely truncated single text line inside a cell */
    function cellText(x, yr, w, h, text, size, color, style = 'normal', align = 'left') {
        doc.setTextColor(...color)
        doc.setFontSize(size)
        doc.setFont('helvetica', style)
        const safe = doc.splitTextToSize(String(text || '—'), w - 4)
        const tx = align === 'center' ? x + w / 2 : x + 2.5
        doc.text(safe[0], tx, yr + h / 2 + size * 0.18, { align })
    }

    /**
     * Render wrapped text lines inside a cell.
     * Starts 3.5 mm from the top of the cell so text doesn't touch the border.
     * Line spacing = size * 0.352778 (pt→mm) * 1.35 leading ≈ 3.33 mm at 7pt.
     */
    function cellMulti(x, yr, w, lines, size, color, style = 'normal') {
        doc.setTextColor(...color)
        doc.setFontSize(size)
        doc.setFont('helvetica', style)
        const lineH = size * 0.352778 * 1.35   // ≈ 3.33 mm at 7pt
        const TOP_PAD = 3.5
        lines.forEach((line, idx) => {
            doc.text(line, x + 2.5, yr + TOP_PAD + idx * lineH + lineH * 0.75)
        })
    }

    /**
     * Compute safe cell height for N wrapped lines at a given font size.
     * Uses the same lineH formula as cellMulti so height ≥ actual text height.
     */
    function cellHeight(lineCount, size, minH = 8) {
        const lineH = size * 0.352778 * 1.35
        const TOP_PAD = 3.5
        const BOTTOM_PAD = 2
        return Math.max(minH, TOP_PAD + lineCount * lineH + BOTTOM_PAD)
    }

    // ── Title bar ──────────────────────────────────────────────────────────────
    rect(M, y, TW, 10, C.lbl)
    doc.setTextColor(...C.white)
    doc.setFontSize(12)
    doc.setFont('helvetica', 'bolditalic')
    doc.text('RCA Report', M + 3, y + 7)
    doc.setFontSize(6.5)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(...C.muted)
    doc.text('Strictly private and confidential', M + TW - 2, y + 7, { align: 'right' })
    y += 12

    // ── Meta row (4 columns) ───────────────────────────────────────────────────
    function metaRow4(l1, v1, l2, v2) {
        doc.setFontSize(7)
        doc.setFont('helvetica', 'normal')
        const lns1 = doc.splitTextToSize(String(v1 || '—'), VAL - 4)
        const lns2 = doc.splitTextToSize(String(v2 || '—'), VAL - 4)
        const h = cellHeight(Math.max(lns1.length, lns2.length), 7)
        checkPage(h)

        // Left label
        rect(M, y, LBL, h, C.lbl)
        cellText(M, y, LBL, h, l1, 6.5, C.muted, 'bold')
        // Left value — ALL wrapped lines
        rect(M + LBL, y, VAL, h, C.val)
        cellMulti(M + LBL, y, VAL, lns1, 7, C.white)

        // Right label
        rect(M + HALF, y, LBL, h, C.lbl)
        cellText(M + HALF, y, LBL, h, l2, 6.5, C.muted, 'bold')
        // Right value — ALL wrapped lines
        rect(M + HALF + LBL, y, VAL, h, C.val)
        cellMulti(M + HALF + LBL, y, VAL, lns2, 7, C.white)

        y += h
    }

    // ── Wide row (label + full-width value) ────────────────────────────────────
    function wideRow(label, value) {
        doc.setFontSize(7)
        const lns = doc.splitTextToSize(String(value || '—'), TW - LBL - 4)
        const h = cellHeight(lns.length, 7)
        checkPage(h)

        rect(M, y, LBL, h, C.lbl)
        cellText(M, y, LBL, h, label, 6.5, C.muted, 'bold')
        rect(M + LBL, y, TW - LBL, h, C.val)
        cellMulti(M + LBL, y, TW - LBL, lns, 7, C.white)

        y += h
    }

    // ── Section header (pink strip) ────────────────────────────────────────────
    function sectionHeader(title) {
        checkPage(9)
        doc.setFillColor(...C.pink)
        doc.rect(M, y, TW, 8, 'F')
        doc.setTextColor(...C.pinkTxt)
        doc.setFontSize(8)
        doc.setFont('helvetica', 'bold')
        doc.text(title.toUpperCase(), PAGE_W / 2, y + 5.5, { align: 'center' })
        y += 8
    }

    // ── Draw the meta grid ────────────────────────────────────────────────────
    metaRow4('Department', meta.department, 'Total down time', meta.total_downtime)
    metaRow4('Equipment / Place', data.equipment_name, 'Production loss', meta.production_loss)
    metaRow4('Occurrence (From)', meta.occurrence_from, 'Impact of top line', meta.impact_top_line)
    metaRow4('Occurrence (To)', meta.occurrence_to, 'Team list', '')
    wideRow('Problem statement', meta.failure_description)

    // ── 5 Why Analysis ────────────────────────────────────────────────────────
    sectionHeader('5 Why Analysis')

    const WHY_LW = 20          // "Why N" label width
    const WHY_VW = TW - WHY_LW  // value width

    whySteps.forEach((step, i) => {
        const text = sanitizeForPDF(step.answer_summary || condenseText(step.answer))
        doc.setFontSize(7)
        doc.setFont('helvetica', 'normal')
        const lns = doc.splitTextToSize(text, WHY_VW - 4)
        const h = cellHeight(lns.length, 7, 10)
        checkPage(h)

        // Label
        rect(M, y, WHY_LW, h, C.lbl)
        doc.setTextColor(...C.blue)
        doc.setFontSize(7)
        doc.setFont('helvetica', 'bold')
        doc.text(`Why ${i + 1}`, M + WHY_LW / 2, y + h / 2 + 1, { align: 'center' })

        // Value — all wrapped lines
        rect(M + WHY_LW, y, WHY_VW, h, C.val)
        cellMulti(M + WHY_LW, y, WHY_VW, lns, 7, C.white)

        y += h
    })

    // ── Root Cause ─────────────────────────────────────────────────────────────
    const rcText = sanitizeForPDF(cleanText(r.root_cause || '—'))
    doc.setFontSize(7)
    doc.setFont('helvetica', 'bolditalic')
    const rcLns = doc.splitTextToSize(rcText, TW - LBL - 4)
    const rcH = cellHeight(rcLns.length, 7, 12)
    checkPage(rcH)

    doc.setFillColor(...C.redDark)
    doc.setDrawColor(...C.red)
    doc.rect(M, y, LBL, rcH, 'F')
    doc.rect(M, y, LBL, rcH)
    doc.setTextColor(...C.red)
    doc.setFontSize(7.5)
    doc.setFont('helvetica', 'bold')
    doc.text('Root Cause', M + 2, y + rcH / 2 + 1)

    doc.setFillColor(...C.rcBg)
    doc.setDrawColor(...C.red)
    doc.rect(M + LBL, y, TW - LBL, rcH, 'F')
    doc.rect(M + LBL, y, TW - LBL, rcH)
    cellMulti(M + LBL, y, TW - LBL, rcLns, 7, C.white, 'bolditalic')

    y += rcH + 4

    // ── CAPA ──────────────────────────────────────────────────────────────────
    sectionHeader('Corrective and Preventive Actions (CAPA)')

    const SN_W = 10
    const RSP_W = 34
    const DT_W = 26
    const ACT_W = TW - SN_W - RSP_W - DT_W

    const xSn = M
    const xAct = xSn + SN_W
    const xRsp = xAct + ACT_W
    const xDt = xRsp + RSP_W

    checkPage(8)
        ;[['S No', SN_W, xSn], ['Preventive action to be taken', ACT_W, xAct],
        ['Responsibility', RSP_W, xRsp], ['Target end date', DT_W, xDt]
        ].forEach(([lbl, w, x]) => {
            rect(x, y, w, 8, C.lbl)
            cellText(x, y, w, 8, lbl, 6, C.muted, 'bold', 'center')
        })
    y += 8

    localCapa.forEach((row, i) => {
        doc.setFontSize(7)
        doc.setFont('helvetica', 'normal')
        const actionText = sanitizeForPDF(row.action || '—')
        const respText = sanitizeForPDF(row.responsibility || '—')
        const dateText = sanitizeForPDF(row.targetDate || '—')

        const actLns = doc.splitTextToSize(actionText, ACT_W - 4)
        const rh = cellHeight(actLns.length, 7, 10)
        checkPage(rh)

        rect(xSn, y, SN_W, rh, C.val); cellText(xSn, y, SN_W, rh, i + 1, 7, C.blue, 'bold', 'center')
        rect(xAct, y, ACT_W, rh, C.val); cellMulti(xAct, y, ACT_W, actLns, 7, C.white)
        rect(xRsp, y, RSP_W, rh, C.val); cellText(xRsp, y, RSP_W, rh, respText, 7, C.white, 'normal', 'center')
        rect(xDt, y, DT_W, rh, C.val); cellText(xDt, y, DT_W, rh, dateText, 7, C.white, 'normal', 'center')

        y += rh
    })

    doc.save(`RCA_Report_${data.equipment_name || 'report'}_${new Date().toISOString().slice(0, 10)}.pdf`)
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function RCAReportTable({ data }) {
    if (!data || !data.result) return null

    const r = data.result?.five_whys_analysis || data.result
    const meta = data._formMeta || {}
    const whySteps = r.why_steps || []
    const actions = r.corrective_actions || []

    const [localCapa, setLocalCapa] = useState(
        actions.length > 0
            ? actions.slice(0, 5).map(a => ({ action: cleanText(a), responsibility: '', targetDate: '' }))
            : [
                { action: '', responsibility: '', targetDate: '' },
                { action: '', responsibility: '', targetDate: '' },
                { action: '', responsibility: '', targetDate: '' },
            ]
    )

    const handleCapaChange = (idx, field, value) => {
        setLocalCapa(prev => {
            const updated = [...prev]
            updated[idx] = { ...updated[idx], [field]: value }
            return updated
        })
    }

    return (
        <div className="rca-report-table-wrapper">
            <div className="rca-report-header-bar">
                <h2 className="rca-report-title">RCA Report</h2>
                <div className="rca-download-btn-group">
                    <button className="btn-download-csv" onClick={() => downloadCSV(data, localCapa)}>
                        ⬇ CSV
                    </button>
                    <button className="btn-download-pdf" onClick={() => downloadPDF(data, localCapa)}>
                        ⬇ PDF
                    </button>
                </div>
            </div>

            <table className="rca-report-table">
                <tbody>

                    <tr>
                        <td className="rca-label">Department</td>
                        <td className="rca-value">{meta.department || '—'}</td>
                        <td className="rca-label">Total down time</td>
                        <td className="rca-value">{meta.total_downtime || '—'}</td>
                    </tr>

                    <tr>
                        <td className="rca-label">Equipment name / Place of occurrence</td>
                        <td className="rca-value">{data.equipment_name || '—'}</td>
                        <td className="rca-label">Production loss</td>
                        <td className="rca-value">{meta.production_loss || '—'}</td>
                    </tr>

                    <tr>
                        <td className="rca-label">Occurrence — Date &amp; time (From)</td>
                        <td className="rca-value">{meta.occurrence_from || '—'}</td>
                        <td className="rca-label">Impact of top line</td>
                        <td className="rca-value">{meta.impact_top_line || '—'}</td>
                    </tr>

                    <tr>
                        <td className="rca-label">Occurrence — Date &amp; time (To)</td>
                        <td className="rca-value">{meta.occurrence_to || '—'}</td>
                        <td className="rca-label">Team list</td>
                        <td className="rca-value rca-value--muted">—</td>
                    </tr>

                    <tr>
                        <td className="rca-label">Problem statement</td>
                        <td colSpan={3} className="rca-value">{meta.failure_description || '—'}</td>
                    </tr>

                    <tr>
                        <td colSpan={4} className="rca-section-header">5 Why Analysis</td>
                    </tr>

                    {whySteps.length > 0
                        ? whySteps.map((step, i) => (
                            <tr key={i}>
                                <td className="rca-why-label">Why {i + 1}</td>
                                <td colSpan={3} className="rca-value rca-value--condensed">
                                    {step.answer_summary || condenseText(step.answer)}
                                </td>
                            </tr>
                        ))
                        : [1, 2, 3, 4, 5].map(n => (
                            <tr key={n}>
                                <td className="rca-why-label">Why {n}</td>
                                <td colSpan={3} className="rca-value rca-value--muted"></td>
                            </tr>
                        ))}

                    <tr>
                        <td className="rca-label rca-label--highlight">Root Cause</td>
                        <td colSpan={3} className="rca-value rca-value--highlight">{cleanText(r.root_cause || '—')}</td>
                    </tr>

                    <tr>
                        <td colSpan={4} className="rca-section-header">Corrective and Preventive Actions (CAPA)</td>
                    </tr>

                    <tr className="rca-capa-header">
                        <td className="rca-label">S No</td>
                        <td className="rca-label">Preventive action to be taken</td>
                        <td className="rca-label">Responsibility</td>
                        <td className="rca-label">Target end date</td>
                    </tr>

                    {localCapa.map((row, i) => (
                        <tr key={i} className="rca-capa-row">
                            <td className="rca-capa-num">{i + 1}</td>
                            <td>
                                <input
                                    className="rca-capa-input"
                                    type="text"
                                    value={row.action}
                                    onChange={e => handleCapaChange(i, 'action', e.target.value)}
                                    placeholder="Describe action…"
                                />
                            </td>
                            <td>
                                <input
                                    className="rca-capa-input"
                                    type="text"
                                    value={row.responsibility}
                                    onChange={e => handleCapaChange(i, 'responsibility', e.target.value)}
                                    placeholder="Owner"
                                />
                            </td>
                            <td>
                                <input
                                    className="rca-capa-input"
                                    type="text"
                                    value={row.targetDate}
                                    onChange={e => handleCapaChange(i, 'targetDate', e.target.value)}
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
