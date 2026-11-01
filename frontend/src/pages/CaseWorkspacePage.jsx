import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { usePolling } from '../hooks/usePolling'
import ApplicationForm, { stateFromCase } from '../components/ApplicationForm'
import AuditTimeline from '../components/AuditTimeline'
import ConfirmBar from '../components/ConfirmBar'
import DocumentChecklist from '../components/DocumentChecklist'
import DocumentViewer from '../components/DocumentViewer'
import { loanLabel } from '../components/LoanTypePicker'
import ReportPanel from '../components/ReportPanel'
import ScoreBadge from '../components/ScoreBadge'
import StageProgress from '../components/StageProgress'
import StatusChip, { CaseStatusChip } from '../components/StatusChip'
import UploadZone from '../components/UploadZone'
import { ErrorState, Skeleton } from '../components/States'
import './CaseWorkspacePage.css'

const TABS = [
  ['documents', 'Documents'],
  ['fields', 'Extracted fields'],
  ['report', 'Report'],
  ['audit', 'Audit'],
]

function Decision({ action, report }) {
  const word = { approve: 'approve', refer: 'refer', reject: 'reject' }[action.final_decision]
  return (
    <div className="decision card">
      <h3>
        {action.action === 'confirm' ? 'Recommendation confirmed' : 'Recommendation overridden'}
      </h3>
      <p>
        {action.officer} {action.action === 'confirm' ? 'confirmed' : 'overrode'} the recommendation
        {action.action === 'override' && (
          <>
            {' '}
            to <strong>{word}</strong> (the system recommended {report?.band ?? 'no band'})
          </>
        )}{' '}
        on {new Date(action.at).toLocaleString()}.
      </p>
      {action.reason && <p className="muted">Reason: {action.reason}</p>}
    </div>
  )
}

export default function CaseWorkspacePage() {
  const { id } = useParams()
  const { data: c, error, loading, reload } = useAsync(() => api.get(`/cases/${id}`), [id])
  const [tab, setTab] = useState(null)
  const [selected, setSelected] = useState(null)
  const [live, setLive] = useState([])
  const [actionError, setActionError] = useState(null)
  const [editing, setEditing] = useState(false)
  const audit = useAsync(
    () => (tab === 'audit' ? api.get(`/cases/${id}/audit`) : Promise.resolve(null)),
    [id, tab, c?.status],
  )

  const running = c?.status === 'running'
  usePolling(
    async () => {
      try {
        const s = await api.get(`/cases/${id}/status`)
        setLive(s.stages)
        if (s.status !== 'running' && !s.running) reload()
      } catch {
        /* the next tick tries again */
      }
    },
    running,
    1500,
  )

  useEffect(() => {
    if (c && tab === null) setTab(c.report ? 'report' : 'documents')
  }, [c, tab])
  useEffect(() => {
    if (c?.report && !running)
      setTab((t) =>
        t === 'documents' && c.status !== 'draft' && c.status !== 'uploaded' ? 'report' : t,
      )
  }, [c?.status, c?.report, running])

  if (loading && !c) return <Skeleton lines={8} height={28} />
  if (error && !c) return <ErrorState error={error} onRetry={reload} />
  if (!c) return null

  const fixStop = c.status === 'stopped' && c.stop_class === 'fix'
  const editable = ['draft', 'uploaded'].includes(c.status) || fixStop
  const roles = c.applicants.map((a) => a.role)
  const report = c.report
  const recommendation = c.recommendation

  async function act(path, body) {
    setActionError(null)
    try {
      await api.post(`/cases/${id}/${path}`, body)
      await reload()
      setTab('report')
    } catch (e) {
      setActionError(e.message)
      throw e
    }
  }
  async function submit() {
    setActionError(null)
    try {
      await api.post(`/cases/${id}/submit`)
      setLive([])
      await reload()
    } catch (e) {
      setActionError(e.message)
    }
  }
  async function resume(body) {
    setActionError(null)
    try {
      await api.post(`/cases/${id}/resume`, body)
      setEditing(false)
      setLive([])
      await reload()
    } catch (e) {
      setActionError(e.message)
    }
  }
  async function removeDoc(docId) {
    try {
      await api.del(`/cases/${id}/documents/${docId}`)
      reload()
    } catch (e) {
      setActionError(e.message)
    }
  }
  const missingKyc = c.checklist.filter((i) => i.kyc && !i.met)

  return (
    <div className="workspace">
      <header className="ws-head">
        <div>
          <h1>
            <span className="mono">{c.case_no}</span>
          </h1>
          <p className="muted">
            {loanLabel(c.loan_type)} · {c.applicants[0].full_name}
            {c.applicants.length > 1 && ` with ${c.applicants[1].full_name}`}
          </p>
        </div>
        <CaseStatusChip status={c.status} band={c.band} />
      </header>

      <div className="ws-grid">
        <aside className="ws-left card">
          <h3>Documents</h3>
          <DocumentChecklist items={c.checklist} />
        </aside>

        <section className="ws-main">
          {running && (
            <div className="card running-card">
              <h3>Assessing this case</h3>
              <StageProgress stages={live.length ? live : c.stages} />
            </div>
          )}
          {editing ? (
            <div className="card edit-card">
              <h2>Correct the details</h2>
              <ApplicationForm
                loanType={c.loan_type}
                meta={{
                  fields: { [c.loan_type]: c.loan_fields },
                  co_applicant: { [c.loan_type]: c.co_applicant },
                }}
                initial={stateFromCase(c)}
                editing
                submitLabel="Save and resume assessment"
                onSubmit={(body) => resume({ case: body })}
                serverError={actionError}
              />
              <button type="button" className="btn btn-ghost" onClick={() => setEditing(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <>
              <div className="tabs" role="tablist" aria-label="Case sections">
                {TABS.map(([key, label]) => (
                  <button
                    key={key}
                    role="tab"
                    type="button"
                    aria-selected={tab === key}
                    className={`tab${tab === key ? ' on' : ''}`}
                    onClick={() => setTab(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {tab === 'documents' && (
                <div className="tab-body">
                  {editable && (
                    <UploadZone
                      caseId={id}
                      roles={roles}
                      docTypes={c.doc_types}
                      onUploaded={reload}
                    />
                  )}
                  {c.documents.length === 0 ? (
                    <p className="muted">No files yet.</p>
                  ) : (
                    <ul className="doc-list card">
                      {c.documents.map((d) => (
                        <li key={d.id}>
                          <div>
                            <p>
                              <strong>{d.name}</strong>{' '}
                              <span className="muted">
                                {d.role === 'co' ? 'co-applicant' : 'applicant'} ·{' '}
                                {d.doc_type.replaceAll('_', ' ')}
                              </span>
                            </p>
                            {d.status === 'rejected' ? (
                              <StatusChip tone="reject">
                                Rejected{d.message ? `: ${d.message}` : ''}
                              </StatusChip>
                            ) : d.warnings.length ? (
                              <StatusChip tone="refer">Accepted with a warning</StatusChip>
                            ) : (
                              <StatusChip tone="approve">Accepted</StatusChip>
                            )}
                          </div>
                          <div className="doc-actions">
                            {d.status === 'accepted' && (
                              <button
                                type="button"
                                className="btn"
                                onClick={() => {
                                  setSelected(d.id)
                                  setTab('fields')
                                }}
                              >
                                View
                              </button>
                            )}
                            {editable && (
                              <button
                                type="button"
                                className="btn btn-ghost"
                                onClick={() => removeDoc(d.id)}
                                aria-label={`Remove ${d.name}`}
                              >
                                Remove
                              </button>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {tab === 'fields' && (
                <div className="tab-body">
                  {c.documents.filter((d) => d.status === 'accepted').length === 0 ? (
                    <p className="muted">Upload documents first.</p>
                  ) : (
                    <>
                      <div className="field doc-pick">
                        <label htmlFor="doc-pick">Document</label>
                        <select
                          id="doc-pick"
                          className="select"
                          value={selected ?? ''}
                          onChange={(e) => setSelected(e.target.value)}
                        >
                          <option value="">Choose a document…</option>
                          {c.documents
                            .filter((d) => d.status === 'accepted')
                            .map((d) => (
                              <option key={d.id} value={d.id}>
                                {d.name}
                              </option>
                            ))}
                        </select>
                      </div>
                      <DocumentViewer
                        caseId={id}
                        doc={c.documents.find((d) => d.id === selected)}
                      />
                    </>
                  )}
                </div>
              )}

              {tab === 'report' && (
                <div className="tab-body">
                  {report ? (
                    <ReportPanel
                      caseId={id}
                      caseNo={c.case_no}
                      report={report}
                      officerAction={c.officer_action}
                    />
                  ) : (
                    <p className="muted">The report appears here after the case is assessed.</p>
                  )}
                </div>
              )}

              {tab === 'audit' && (
                <div className="tab-body card audit-card">
                  {audit.loading ? (
                    <Skeleton lines={4} />
                  ) : audit.data ? (
                    <AuditTimeline events={audit.data} />
                  ) : null}
                </div>
              )}
            </>
          )}
        </section>

        <aside className="ws-right">
          {report ? (
            <ScoreBadge score={c.total_score} band={c.band} indicative={report.indicative_score} />
          ) : (
            <ScoreBadge score={null} band={null} />
          )}
          {report && <p className="recommended">{report.recommendation_text}.</p>}

          {actionError && !editing && (
            <p className="field-error" role="alert">
              {actionError}
            </p>
          )}

          {['draft', 'uploaded'].includes(c.status) && (
            <div className="ws-actions">
              <button
                type="button"
                className="btn btn-primary"
                disabled={!c.kyc_ready}
                onClick={submit}
              >
                Submit for assessment
              </button>
              {!c.kyc_ready && (
                <p className="small muted">
                  Add the KYC documents first:{' '}
                  {missingKyc
                    .map(
                      (m) =>
                        `${m.type.replaceAll('_', ' ')} (${m.applicant === 'co' ? 'co-applicant' : 'applicant'})`,
                    )
                    .join(', ')}
                  .
                </p>
              )}
            </div>
          )}

          {fixStop && !editing && (
            <div className="ws-actions">
              <p className="stopped-note">{report?.stop_text}</p>
              <p className="small muted">
                Replace the file or correct the details, then resume. Nothing is scored until then.
              </p>
              <button type="button" className="btn" onClick={() => setEditing(true)}>
                Correct details
              </button>
              <button type="button" className="btn btn-primary" onClick={() => resume({})}>
                Resume assessment
              </button>
            </div>
          )}

          {c.status === 'awaiting_confirmation' && (
            <ConfirmBar
              recommendation={recommendation}
              recommendationText={report.recommendation_text}
              onConfirm={() => act('confirm', { second_click: true })}
              onOverride={({ final_decision, reason }) =>
                act('override', { second_click: true, final_decision, reason })
              }
            />
          )}

          {c.officer_action && <Decision action={c.officer_action} report={report} />}
        </aside>
      </div>
    </div>
  )
}
