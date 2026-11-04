import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useSession } from '../App'
import { useAsync } from '../hooks/useAsync'
import { usePolling } from '../hooks/usePolling'
import ApplicationForm, { stateFromCase, stateFromDesk } from '../components/ApplicationForm'
import ApplicantRequest from '../components/ApplicantRequest'
import IntakeDesk from '../components/IntakeDesk'
import AdminChanges from '../components/AdminChanges'
import AdminCorrection from '../components/AdminCorrection'
import AuditTimeline from '../components/AuditTimeline'
import CaseStepper from '../components/CaseStepper'
import ConfirmBar from '../components/ConfirmBar'
import ConfirmDialog from '../components/ConfirmDialog'
import CustomerContact from '../components/CustomerContact'
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
  // an admin opens the same page without the officer's actions: only the admin's own (SECURITY.md D3)
  const isAdmin = useSession().session.user.role === 'admin'
  const { data: c, error, loading, reload } = useAsync(() => api.get(`/cases/${id}`), [id])
  const [tab, setTab] = useState(null)
  const [selected, setSelected] = useState(null)
  const [live, setLive] = useState([])
  const [actionError, setActionError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [docToRemove, setDocToRemove] = useState(null)
  const [removingDoc, setRemovingDoc] = useState(false)
  const [step, setStep] = useState('desk') // desk | form: where a case opened at the desk is
  const [inventory, setInventory] = useState(null)
  const [offer, setOffer] = useState(null)
  const audit = useAsync(
    () => (tab === 'audit' ? api.get(`/cases/${id}/audit`) : Promise.resolve(null)),
    [id, tab, c?.status, c?.admin_actions?.length, c?.officer],
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
  // the inventory belongs to every case that is still being put together, and is read-only for
  // the admin; the identity values the cards offer are the officer's, for the form
  const deskCase = c && !c.report && !['running'].includes(c.status)
  useEffect(() => {
    if (!c || !deskCase) return
    api
      .get(`/cases/${id}/inventory`)
      .then((inv) => setInventory(inv?.counts ? inv : null))
      .catch(() => setInventory(null))
  }, [id, c?.documents?.length, c?.status, deskCase]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!c || isAdmin || !(step === 'form' || editing)) return
    api
      .get(`/cases/${id}/prefill`)
      .then(setOffer)
      .catch(() => setOffer(null))
  }, [id, step, editing, isAdmin, c?.documents?.length]) // eslint-disable-line react-hooks/exhaustive-deps
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
  const BEFORE = ['draft', 'uploaded', 'applicant_submitted']
  const editable = !isAdmin && (BEFORE.includes(c.status) || fixStop)
  const roles = c.people ?? c.applicants.map((a) => a.role)
  const first = c.applicants[0]
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
  async function saveForm(body) {
    setActionError(null)
    try {
      await api.put(`/cases/${id}/form`, body)
      setEditing(false)
      setStep('desk')
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
  async function removeDoc() {
    setRemovingDoc(true)
    try {
      await api.del(`/cases/${id}/documents/${docToRemove.id}`)
      setDocToRemove(null)
      reload()
    } catch (e) {
      setActionError(e.message)
      setDocToRemove(null)
    } finally {
      setRemovingDoc(false)
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
            {loanLabel(c.loan_type)} · {first ? first.full_name : 'details not entered yet'}
            {c.applicants.length > 1 && ` with ${c.applicants[1].full_name}`}
            {isAdmin && c.officer && ` · officer ${c.officer}`}
          </p>
          {isAdmin && (
            <p className="readonly-note small">
              <strong>Admin view.</strong> You can read everything on this case. You correct a
              decision after the officer has made it, and you cannot confirm, upload or submit.
            </p>
          )}
        </div>
        <CaseStatusChip status={c.status} band={c.band} />
      </header>

      <CaseStepper
        caseData={{ ...c, stages: live.length ? live : c.stages }}
        stopText={report?.stop_text}
      />

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
                initial={{ ...stateFromCase(c), identityConfirmed: Boolean(c.identity?.confirmed) }}
                editing
                offer={offer}
                submitLabel={fixStop ? 'Save and resume assessment' : 'Save the form'}
                onSubmit={(body) => (fixStop ? resume({ case: body }) : saveForm(body))}
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
                  {c.origin === 'applicant' && <ApplicantRequest c={c} />}
                  {c.intake_stage && step === 'form' && !isAdmin ? (
                    <div className="card edit-card">
                      <h2>Application form</h2>
                      {offer ? (
                        <ApplicationForm
                          key={`desk-${c.documents.length}-${Boolean(offer)}`}
                          loanType={c.loan_type}
                          meta={{
                            fields: { [c.loan_type]: c.loan_fields },
                            co_applicant: { [c.loan_type]: c.co_applicant },
                          }}
                          initial={stateFromDesk(c, offer, inventory)}
                          offer={offer}
                          submitLabel="Save the form"
                          onSubmit={saveForm}
                          serverError={actionError}
                        />
                      ) : (
                        <Skeleton lines={4} />
                      )}
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => setStep('desk')}
                      >
                        Back to the documents
                      </button>
                    </div>
                  ) : inventory ? (
                    <>
                      <IntakeDesk
                        caseId={id}
                        inventory={inventory}
                        setInventory={setInventory}
                        docTypes={c.doc_types}
                        editable={editable}
                        recipient={first?.email}
                        onContinue={c.intake_stage && editable ? () => setStep('form') : undefined}
                        onChanged={reload}
                      />
                      {editable && (
                        <details className="label-yourself">
                          <summary>Add one file and label it yourself</summary>
                          <UploadZone
                            caseId={id}
                            roles={roles}
                            docTypes={c.doc_types}
                            onUploaded={reload}
                          />
                        </details>
                      )}
                    </>
                  ) : editable ? (
                    <UploadZone
                      caseId={id}
                      roles={roles}
                      docTypes={c.doc_types}
                      onUploaded={reload}
                    />
                  ) : null}
                  {c.documents.length > 0 && (
                    <>
                      <h3 className="files-title">All files</h3>
                      <ul className="doc-list card">
                        {c.documents.map((d) => (
                          <li key={d.id}>
                            <div>
                              <p>
                                <strong>{d.name}</strong>{' '}
                                <span className="muted">
                                  {d.role === 'co'
                                    ? 'co-applicant'
                                    : d.role === 'primary'
                                      ? 'applicant'
                                      : 'no person yet'}{' '}
                                  · {d.doc_type.replaceAll('_', ' ')}
                                </span>
                              </p>
                              {d.status === 'rejected' ? (
                                <StatusChip tone="reject">
                                  Rejected{d.message ? `: ${d.message}` : ''}
                                </StatusChip>
                              ) : d.status === 'ignored' ? (
                                <StatusChip tone="neutral">Repeat, ignored</StatusChip>
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
                                  onClick={() => setDocToRemove(d)}
                                  aria-label={`Remove ${d.name}`}
                                >
                                  Remove
                                </button>
                              )}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </>
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
                      readOnly={isAdmin}
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

          {!isAdmin && c.last_failure && !running && (
            <div className="failed-note" role="alert">
              <strong>The assessment failed.</strong> Please try again, or contact an admin if it
              keeps failing.
              <span className="small muted">
                Error type: {c.last_failure.error} · {new Date(c.last_failure.at).toLocaleString()}
              </span>
            </div>
          )}

          {!isAdmin && BEFORE.includes(c.status) && (
            <div className="ws-actions">
              {!c.intake_stage && (
                <button type="button" className="btn" onClick={() => setEditing(true)}>
                  Edit the application form
                </button>
              )}
              <button
                type="button"
                className="btn btn-primary"
                disabled={!c.kyc_ready || c.intake_stage}
                onClick={submit}
              >
                Submit for assessment
              </button>
              {c.intake_stage && (
                <p className="small muted">
                  Fill in the application form first. Use “Continue to the application form” on the
                  Documents tab.
                </p>
              )}
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

          {!isAdmin && fixStop && !editing && (
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

          {!isAdmin && c.status === 'awaiting_confirmation' && (
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
          <AdminChanges actions={c.admin_actions} />
          {isAdmin && <AdminCorrection c={c} onDone={reload} />}

          {!isAdmin && ['confirmed', 'overridden', 'stopped'].includes(c.status) && (
            <CustomerContact caseId={id} recipient={first?.email} />
          )}
        </aside>
      </div>
      {docToRemove && (
        <ConfirmDialog
          title="Remove this document?"
          confirmLabel="Yes, remove"
          busy={removingDoc}
          onClose={() => setDocToRemove(null)}
          onConfirm={removeDoc}
        >
          <p>
            <strong>{docToRemove.name}</strong> will be removed from this case. You can upload it
            again before the assessment is submitted.
          </p>
        </ConfirmDialog>
      )}
    </div>
  )
}
