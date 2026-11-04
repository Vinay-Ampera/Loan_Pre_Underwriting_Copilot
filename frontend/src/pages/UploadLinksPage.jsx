import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useSession } from '../App'
import { linkUrl } from '../components/AskApplicantDialog'
import ConfirmDialog from '../components/ConfirmDialog'
import Dialog from '../components/Dialog'
import { loanLabel, LOAN_TYPES } from '../components/LoanTypePicker'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import StatusChip from '../components/StatusChip'
import { useAsync } from '../hooks/useAsync'
import './UploadLinksPage.css'

const STATE = {
  active: ['approve', 'Open'],
  expired: ['stopped', 'Expired'],
  disabled: ['reject', 'Disabled'],
}
const day = (t) => new Date(t).toLocaleDateString([], { dateStyle: 'medium' })

/**
 * Create a link, then show its address once. Creating it is outward-facing, so the dialog's
 * button is the second click. Only a scrambled form of the token is kept, so there is no way to
 * show it again later.
 */
function CreateLinkDialog({ isAdmin, onClose, onCreated }) {
  const officers = useAsync(
    () => (isAdmin ? api.get('/admin/users') : Promise.resolve([])),
    [isAdmin],
  )
  const [loanType, setLoanType] = useState('')
  const [officerId, setOfficerId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [made, setMade] = useState(null)
  const [copied, setCopied] = useState(false)

  const choices = (officers.data || []).filter((u) => u.role === 'officer' && u.active)

  async function create() {
    setBusy(true)
    setError(null)
    try {
      const body = { second_click: true }
      if (loanType) body.loan_type = loanType
      if (isAdmin) body.officer_id = officerId
      setMade(await api.post('/links', body))
      onCreated()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(linkUrl(made.path))
      setCopied(true)
    } catch {
      setError('Copying did not work. Select the address and copy it by hand.')
    }
  }

  if (made) {
    return (
      <Dialog title="The applicant's link" onClose={onClose} labelledBy="made-link-title">
        <p>
          Copy this address now. It cannot be shown again, because only a scrambled form of it is
          kept. It works for {Math.round((new Date(made.expires_at) - Date.now()) / 86400000)} days.
        </p>
        <input
          className="input mono"
          readOnly
          aria-label="Upload link address"
          value={linkUrl(made.path)}
          onFocus={(e) => e.target.select()}
        />
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={copy} data-autofocus>
            {copied ? 'Copied' : 'Copy the link'}
          </button>
          <button type="button" className="btn btn-primary" onClick={onClose}>
            Done
          </button>
        </div>
      </Dialog>
    )
  }
  return (
    <ConfirmDialog
      title="Create an upload link?"
      confirmLabel="Create the link"
      danger={false}
      busy={busy || (isAdmin && !officerId)}
      error={error}
      onClose={onClose}
      onConfirm={create}
    >
      <p>
        The applicant opens it without an account, states their request and adds documents. They see
        a checklist and nothing else: no score, no status, no outcome. You will see the address
        once.
      </p>
      {isAdmin && (
        <div className="field">
          <label htmlFor="link-officer">Officer this link is for</label>
          <select
            id="link-officer"
            className="select"
            value={officerId}
            onChange={(e) => setOfficerId(e.target.value)}
          >
            <option value="">Choose an officer…</option>
            {choices.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="field">
        <label htmlFor="link-loan">
          Kind of loan <span className="opt">(optional)</span>
        </label>
        <select
          id="link-loan"
          className="select"
          value={loanType}
          onChange={(e) => setLoanType(e.target.value)}
        >
          <option value="">The applicant chooses</option>
          {LOAN_TYPES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </div>
    </ConfirmDialog>
  )
}

export default function UploadLinksPage() {
  const isAdmin = useSession().session.user.role === 'admin'
  const links = useAsync(() => api.get('/links'), [])
  const [creating, setCreating] = useState(false)
  const [toDisable, setToDisable] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function disable() {
    setBusy(true)
    try {
      await api.post(`/links/${toDisable.id}/disable`, { second_click: true })
      setToDisable(null)
      links.reload()
    } catch (e) {
      setError(e.message)
      setToDisable(null)
    } finally {
      setBusy(false)
    }
  }
  async function extend(l) {
    setError(null)
    try {
      await api.post(`/links/${l.id}/extend`, {})
      links.reload()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="links-page">
      <header className="links-head">
        <div>
          <h1>Upload links</h1>
          <p className="muted">
            A link lets an applicant send their request and documents without an account. It is tied
            to one officer, expires on its own and can be disabled at any time.
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
          Create a link
        </button>
      </header>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      {links.loading && !links.data && <Skeleton lines={4} />}
      {links.error && <ErrorState error={links.error} onRetry={links.reload} />}
      {links.data && links.data.length === 0 && (
        <EmptyState title="No links yet">Create one to ask an applicant for documents.</EmptyState>
      )}
      {links.data && links.data.length > 0 && (
        <div className="card links-wrap">
          <table className="links-table">
            <thead>
              <tr>
                <th>Created</th>
                {isAdmin && <th>Officer</th>}
                <th>Loan</th>
                <th>Case</th>
                <th>Files</th>
                <th>Expires</th>
                <th>State</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {links.data.map((l) => {
                const [tone, label] = STATE[l.state]
                return (
                  <tr key={l.id}>
                    <td data-label="Created">{day(l.created_at)}</td>
                    {isAdmin && <td data-label="Officer">{l.officer}</td>}
                    <td data-label="Loan">{l.loan_type ? loanLabel(l.loan_type) : 'Any'}</td>
                    <td data-label="Case">
                      {l.case_id ? (
                        <Link to={`/cases/${l.case_id}`} className="mono">
                          {l.case_no}
                        </Link>
                      ) : (
                        <span className="muted">Not started</span>
                      )}
                      {l.sent && <span className="small muted"> · sent</span>}
                    </td>
                    <td data-label="Files">{l.files_count}</td>
                    <td data-label="Expires">{day(l.expires_at)}</td>
                    <td data-label="State">
                      <StatusChip tone={tone}>{label}</StatusChip>
                    </td>
                    <td className="links-actions">
                      {l.state !== 'disabled' && (
                        <button type="button" className="btn" onClick={() => extend(l)}>
                          Extend
                        </button>
                      )}
                      {l.state !== 'disabled' && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => setToDisable(l)}
                        >
                          Disable
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {creating && (
        <CreateLinkDialog
          isAdmin={isAdmin}
          onClose={() => setCreating(false)}
          onCreated={links.reload}
        />
      )}
      {toDisable && (
        <ConfirmDialog
          title="Disable this link?"
          confirmLabel="Yes, disable it"
          busy={busy}
          onClose={() => setToDisable(null)}
          onConfirm={disable}
        >
          <p>
            The applicant will no longer be able to open it or add files. Files already received
            stay on the case. This cannot be undone; you can create a new link.
          </p>
        </ConfirmDialog>
      )}
    </div>
  )
}
