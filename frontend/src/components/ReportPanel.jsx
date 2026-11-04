import { useState } from 'react'
import { api } from '../api/client'
import StageCard from './StageCard'
import FindingList from './FindingList'
import CreditStrip from './CreditStrip'
import AtAGlance from './AtAGlance'
import TypedText from './TypedText'
import { conditionsFrom } from '../lib/conditions'
import { filterCitations } from '../lib/glance'
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

function Citations({ report }) {
  const [q, setQ] = useState('')
  const [stage, setStage] = useState('')
  const shown = filterCitations(report, { q, stage })
  return (
    <>
      <div className="citation-filters" role="search">
        <div className="field">
          <label htmlFor="cite-q">Search clauses</label>
          <input
            id="cite-q"
            className="input"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Clause ID or wording"
          />
        </div>
        <div className="field">
          <label htmlFor="cite-stage">Cited by stage</label>
          <select
            id="cite-stage"
            className="select"
            value={stage}
            onChange={(e) => setStage(e.target.value)}
          >
            <option value="">All stages</option>
            {report.stage_scores.map((s) => (
              <option key={s.stage} value={s.stage}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="small muted" aria-live="polite">
        Showing {shown.length} of {report.citations.length}
      </p>
      {shown.length === 0 ? (
        <p className="muted">No clauses match.</p>
      ) : (
        <ul className="citations">
          {shown.map((c) => (
            <li key={c.clause_id} id={`clause-${c.clause_id}`}>
              <code>{c.clause_id}</code>
              <p>{c.text}</p>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

/** Summary, stage cards, findings by person, citations, rejection reason and PDF export. */
export default function ReportPanel({ caseId, caseNo, report, officerAction, readOnly = false }) {
  const [pdfError, setPdfError] = useState(null)
  const byStage = (stage) => report.findings.filter((f) => f.stage === stage)
  const known = new Set(report.stage_scores.map((s) => s.stage))
  const other = report.findings.filter((f) => !known.has(f.stage))
  const multi = report.sections.co.length > 0
  const unverifiedStages = new Set(report.unverified.map((u) => u.stage))
  const conditions = conditionsFrom(report)

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
        {!readOnly && (
          <button
            type="button"
            className="btn"
            onClick={() => downloadPdf(caseId, caseNo).catch((e) => setPdfError(e.message))}
          >
            Export PDF
          </button>
        )}
      </div>
      {pdfError && (
        <p className="field-error" role="alert">
          {pdfError}
        </p>
      )}

      {report.status !== 'stopped' && report.stop_text && (
        <p className="stop-note">{report.stop_text}</p>
      )}

      <AtAGlance report={report} />

      {Object.keys(report.identity_from_documents || {}).length > 0 && (
        <aside
          className="card report-block source-note"
          aria-label="Where the form values came from"
        >
          <h3>Identity details read from the cards</h3>
          <p className="muted">
            Some identity details on the form were read from the applicant&apos;s PAN and Aadhaar
            cards and confirmed by the officer:{' '}
            {Object.entries(report.identity_from_documents)
              .map(
                ([role, fields]) =>
                  `${role === 'co' ? 'co-applicant' : 'applicant'}: ${fields
                    .map(
                      (f) =>
                        ({
                          full_name: 'name',
                          dob: 'date of birth',
                          aadhaar_last4: 'Aadhaar last four',
                        })[f] || f,
                    )
                    .join(', ')}`,
              )
              .join('; ')}
            . A match against those same cards is{' '}
            <strong>from document, not an independent check</strong>. The other documents were still
            compared with the form.
          </p>
        </aside>
      )}

      <section className="card report-block">
        <h3>Summary</h3>
        <p>
          <TypedText id={`${caseId}:${report.summary}`} text={report.summary} />
        </p>
        <p className="small muted">
          {report.summary_source === 'model'
            ? 'Wording written by a model from the rules engine results; every number comes from code.'
            : 'Wording written by code from the rules engine results.'}
        </p>
      </section>

      {report.status !== 'stopped' && <CreditStrip report={report} />}

      <section className="card report-block conditions">
        <h3>Conditions</h3>
        {conditions.length === 0 ? (
          <p className="muted">No missing items. Nothing is waiting on the applicant.</p>
        ) : (
          <>
            <p className="muted">Items to obtain or fix before relying on this case:</p>
            <ul>
              {conditions.map((f, i) => (
                <li key={i}>
                  {f.message} <code>{f.rule_id}</code>
                </li>
              ))}
            </ul>
          </>
        )}
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
          <Citations report={report} />
        )}
        <p className="small muted">
          Rules version {report.versions?.rules ?? '–'}. Synthetic data; the recommendation is for
          the officer to confirm.
        </p>
      </section>
    </div>
  )
}
