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
 * button is the second click. The owning officer and the admin can copy the address again later
 * from the list (an encrypted copy is kept, every look is audited).
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
          Copy this address. You can copy it again later from the Upload links page. It works for{' '}
          {Math.round((new Date(made.expires_at) - Date.now()) / 86400000)} days.
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

const DAY_CHOICES = [1, 3, 7, 14, 30]

/** Set how many days from now the link stays open: longer or shorter. Shortening is the
 * second-click kind, so the button says what it does. */
function SetDaysDialog({ link, onClose, onDone }) {
  const left = Math.max(1, Math.ceil((new Date(link.expires_at) - Date.now()) / 86400000))
  const [days, setDays] = useState(DAY_CHOICES.includes(left) ? String(left) : 'custom')
  const [custom, setCustom] = useState(String(Math.min(left, 30)))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const n = days === 'custom' ? Number(custom) : Number(days)
  const valid = Number.isInteger(n) && n >= 1 && n <= 30
  const shorter = valid && Date.now() + n * 86400000 < new Date(link.expires_at).getTime()

  async function save() {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/links/${link.id}/expiry`, { days: n, second_click: true })
      onDone()
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }
  return (
    <ConfirmDialog
      title="Set how long the link stays open"
      confirmLabel={shorter ? 'Shorten the link' : 'Save'}
      danger={shorter}
      busy={busy || !valid}
      error={error}
      onClose={onClose}
      onConfirm={save}
    >
      <p>
        The link is open until {day(link.expires_at)}. Choose how many days from today it should
        stay open (1 to 30).
      </p>
      <div className="field">
        <label htmlFor="link-days">Days from today</label>
        <select
          id="link-days"
          className="select"
          value={days}
          onChange={(e) => setDays(e.target.value)}
        >
          {DAY_CHOICES.map((d) => (
            <option key={d} value={d}>
              {d} {d === 1 ? 'day' : 'days'}
            </option>
          ))}
          <option value="custom">Another number…</option>
        </select>
      </div>
      {days === 'custom' && (
        <div className="field">
          <label htmlFor="link-days-custom">Number of days (1 to 30)</label>
          <input
            id="link-days-custom"
            className="input"
            type="number"
            min="1"
            max="30"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
          />
        </div>
      )}
      {shorter && <p className="small muted">This makes the link end sooner than it does now.</p>}
    </ConfirmDialog>
  )
}

export default function UploadLinksPage() {
  const isAdmin = useSession().session.user.role === 'admin'
  const links = useAsync(() => api.get('/links'), [])
  const [creating, setCreating] = useState(false)
  const [toDisable, setToDisable] = useState(null)
  const [toSet, setToSet] = useState(null)
  const [toRegen, setToRegen] = useState(null)
  const [copiedId, setCopiedId] = useState(null)
  const [regenerated, setRegenerated] = useState(null)
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
  async function copy(l) {
    setError(null)
    try {
      const { path } = await api.get(`/links/${l.id}/address`)
      await navigator.clipboard.writeText(linkUrl(path))
      setCopiedId(l.id)
    } catch (e) {
      setError(e.message || 'Copying did not work.')
    }
  }
  async function regenerate() {
    setBusy(true)
    try {
      const out = await api.post(`/links/${toRegen.id}/regenerate`, { second_click: true })
      setRegenerated(out)
      setToRegen(null)
      links.reload()
    } catch (e) {
      setError(e.message)
      setToRegen(null)
    } finally {
      setBusy(false)
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
                    <td data-label="Expires">
                      {day(l.expires_at)}
                      {l.state === 'active' && (
                        <span className="small muted">
                          {' '}
                          ·{' '}
                          {Math.max(
                            1,
                            Math.ceil((new Date(l.expires_at) - Date.now()) / 86400000),
                          )}{' '}
                          d left
                        </span>
                      )}
                    </td>
                    <td data-label="State">
                      <StatusChip tone={tone}>{label}</StatusChip>
                    </td>
                    <td className="links-actions">
                      {l.state !== 'disabled' && (
                        <button type="button" className="btn" onClick={() => copy(l)}>
                          {copiedId === l.id ? 'Copied' : 'Copy link'}
                        </button>
                      )}
                      {l.state !== 'disabled' && (
                        <button type="button" className="btn" onClick={() => setToSet(l)}>
                          Set days
                        </button>
                      )}
                      {l.state !== 'disabled' && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => setToRegen(l)}
                        >
                          New address
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
      {toSet && (
        <SetDaysDialog
          link={toSet}
          onClose={() => setToSet(null)}
          onDone={() => {
            setToSet(null)
            links.reload()
          }}
        />
      )}
      {toRegen && (
        <ConfirmDialog
          title="Make a new address for this link?"
          confirmLabel="Yes, make a new address"
          danger
          busy={busy}
          onClose={() => setToRegen(null)}
          onConfirm={regenerate}
        >
          <p>
            The old address stops working at once, for anyone who has it. The case, the files and
            the expiry stay as they are. You will copy the new address next.
          </p>
        </ConfirmDialog>
      )}
      {regenerated && (
        <Dialog
          title="The new address"
          onClose={() => setRegenerated(null)}
          labelledBy="regen-link-title"
        >
          <p>Copy it and send it to the applicant. The old address no longer works.</p>
          <input
            className="input mono"
            readOnly
            aria-label="New upload link address"
            value={linkUrl(regenerated.path)}
            onFocus={(e) => e.target.select()}
          />
          <div className="dialog-actions">
            <button
              type="button"
              className="btn"
              data-autofocus
              onClick={() => navigator.clipboard?.writeText(linkUrl(regenerated.path))}
            >
              Copy the link
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setRegenerated(null)}>
              Done
            </button>
          </div>
        </Dialog>
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
