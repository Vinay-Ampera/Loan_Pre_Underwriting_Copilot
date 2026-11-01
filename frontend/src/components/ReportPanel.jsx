import { useState } from 'react'
import { api } from '../api/client'
import StageCard from './StageCard'
import FindingList from './FindingList'
import './ReportPanel.css'

const SECTION = { primary: 'Applicant', co: 'Co-applicant', case: 'Case-level' }

async function downloadPdf(caseId, caseNo) {
  const blob = await api.blob(`/cases/${caseId}/report.pdf`)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${caseNo}-report.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

/** Summary, stage cards, findings by person, citations, rejection reason and PDF export. */
export default function ReportPanel({ caseId, caseNo, report, officerAction }) {
  const [pdfError, setPdfError] = useState(null)
  const byStage = (stage) => report.findings.filter((f) => f.stage === stage)
  const known = new Set(report.stage_scores.map((s) => s.stage))
  const other = report.findings.filter((f) => !known.has(f.stage))
  const multi = report.sections.co.length > 0
  const unverifiedStages = new Set(report.unverified.map((u) => u.stage))

  return (
    <div className="report">
      <div className="report-head">
        <div>
          <h2>{report.recommendation_text}</h2>
          {!officerAction && report.status !== 'stopped' && (
            <p className="muted">{report.awaiting}</p>
          )}
          {report.status === 'stopped' && <p className="muted">{report.stop_text}</p>}
        </div>
        <button
          type="button"
          className="btn"
          onClick={() => downloadPdf(caseId, caseNo).catch((e) => setPdfError(e.message))}
        >
          Export PDF
        </button>
      </div>
      {pdfError && (
        <p className="field-error" role="alert">
          {pdfError}
        </p>
      )}

      {report.status !== 'stopped' && report.stop_text && (
        <p className="stop-note">{report.stop_text}</p>
      )}

      <section className="card report-block">
        <h3>Summary</h3>
        <p>{report.summary}</p>
        <p className="small muted">
          {report.summary_source === 'model'
            ? 'Wording written by a model from the rules engine results; every number comes from code.'
            : 'Wording written by code from the rules engine results.'}
        </p>
      </section>

      {report.rejection_reason && (
        <section className="card report-block reason">
          <h3>Reason for the recommendation to reject</h3>
          <p>{report.rejection_reason}</p>
        </section>
      )}

      {report.unverified.length > 0 && (
        <section className="card report-block unverified">
          <h3>Could not be verified automatically</h3>
          <p>Please check manually.</p>
          <ul>
            {report.unverified.map((u, i) => (
              <li key={i}>
                <strong>{u.stage}</strong>: {u.reason}
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="stage-cards">
        {report.stage_scores.map((row) => (
          <StageCard
            key={row.stage}
            row={row}
            findings={byStage(row.stage)}
            clauses={report.citations}
            unverified={unverifiedStages.has(row.stage === 'documents' ? 'extraction' : row.stage)}
          />
        ))}
      </div>

      {other.length > 0 && (
        <section className="card report-block">
          <h3>Other findings</h3>
          <FindingList findings={other} clauses={report.citations} />
        </section>
      )}

      {multi && (
        <section className="card report-block">
          <h3>Findings by person</h3>
          {['primary', 'co', 'case'].map(
            (key) =>
              report.sections[key].length > 0 && (
                <div key={key} className="by-person">
                  <h4>{SECTION[key]}</h4>
                  <FindingList
                    findings={report.sections[key].map((i) => report.findings[i])}
                    clauses={report.citations}
                  />
                </div>
              ),
          )}
        </section>
      )}

      {report.precedents.length > 0 && (
        <section className="card report-block">
          <h3>Similar approved precedents</h3>
          <ul>
            {report.precedents.map((p) => (
              <li key={p.id}>
                {p.summary}{' '}
                <span className="muted">
                  (similarity {p.similarity}, outcome {p.final_decision})
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card report-block">
        <h3>Policy citations</h3>
        {report.citations.length === 0 ? (
          <p className="muted">No clauses cited.</p>
        ) : (
          <ul className="citations">
            {report.citations.map((c) => (
              <li key={c.clause_id} id={`clause-${c.clause_id}`}>
                <code>{c.clause_id}</code>
                <p>{c.text}</p>
              </li>
            ))}
          </ul>
        )}
        <p className="small muted">
          Rules version {report.versions?.rules ?? '–'}. Synthetic data; the recommendation is for
          the officer to confirm.
        </p>
      </section>
    </div>
  )
}
