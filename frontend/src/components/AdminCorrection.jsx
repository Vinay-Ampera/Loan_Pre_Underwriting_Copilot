import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import Dialog from './Dialog'
import './AdminCorrection.css'

export const MIN_REASON = 15
const DECISIONS = ['approve', 'refer', 'reject']
// a case the officer has not decided and that is not running can be handed to another officer
const REASSIGNABLE = ['draft', 'uploaded', 'stopped', 'awaiting_confirmation']

function ReasonField({ id, reason, onChange }) {
  const trimmed = reason.trim()
  return (
    <div className="field">
      <label htmlFor={id}>Reason (required)</label>
      <textarea
        id={id}
        className="textarea"
        value={reason}
        onChange={(e) => onChange(e.target.value)}
        aria-describedby={`${id}-help`}
        aria-invalid={reason.length > 0 && trimmed.length < MIN_REASON}
      />
      <span id={`${id}-help`} className="small muted">
        {trimmed.length < MIN_REASON
          ? `Write at least ${MIN_REASON} characters. ${trimmed.length}/${MIN_REASON}`
          : 'The reason is kept on the case and in the audit log.'}
      </span>
    </div>
  )
}

/** Run a request from a dialog; the dialog button is the second click. */
function useAction(path, onDone, onClose) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  async function run(body) {
    setBusy(true)
    setError(null)
    try {
      await api.post(path, { ...body, second_click: true })
      onClose()
      await onDone()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, run }
}

function OverrideDialog({ caseId, inForce, onClose, onDone }) {
  const [decision, setDecision] = useState('')
  const [reason, setReason] = useState('')
  const { busy, error, run } = useAction(`/admin/cases/${caseId}/override`, onDone, onClose)
  const valid = decision && decision !== inForce && reason.trim().length >= MIN_REASON
  return (
    <Dialog title="Change the decision" onClose={onClose} labelledBy="admin-override-title">
      <p>
        The decision in force is <strong>{inForce}</strong>. Your change is kept next to the
        officer&apos;s decision; nothing is removed.
      </p>
      <div className="field">
        <label htmlFor="admin-decision">New decision</label>
        <select
          id="admin-decision"
          className="select"
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
          data-autofocus
        >
          <option value="">Choose…</option>
          {DECISIONS.filter((d) => d !== inForce).map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>
      <ReasonField id="admin-reason" reason={reason} onChange={setReason} />
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      <div className="dialog-actions">
        <button type="button" className="btn" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-danger"
          disabled={!valid || busy}
          onClick={() => run({ final_decision: decision, reason: reason.trim() })}
        >
          Yes, change the decision
        </button>
      </div>
    </Dialog>
  )
}

function ReassignDialog({ caseId, ownerId, owner, onClose, onDone }) {
  const [officer, setOfficer] = useState('')
  const [reason, setReason] = useState('')
  const users = useAsync(() => api.get('/admin/users'), [])
  const { busy, error, run } = useAction(`/admin/cases/${caseId}/reassign`, onDone, onClose)
  const officers = (users.data ?? []).filter(
    (u) => u.role === 'officer' && u.active && u.id !== ownerId,
  )
  const valid = officer && reason.trim().length >= MIN_REASON
  return (
    <Dialog title="Reassign this case" onClose={onClose} labelledBy="admin-reassign-title">
      <p>
        The case is with <strong>{owner}</strong>. The new officer will make the decision; an admin
        never decides first.
      </p>
      <div className="field">
        <label htmlFor="admin-officer">New officer</label>
        <select
          id="admin-officer"
          className="select"
          value={officer}
          onChange={(e) => setOfficer(e.target.value)}
          data-autofocus
        >
          <option value="">Choose…</option>
          {officers.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
      </div>
      <ReasonField id="admin-reassign-reason" reason={reason} onChange={setReason} />
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      <div className="dialog-actions">
        <button type="button" className="btn" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!valid || busy}
          onClick={() => run({ officer_id: officer, reason: reason.trim() })}
        >
          Yes, reassign
        </button>
      </div>
    </Dialog>
  )
}

/**
 * The admin's two actions on a case. The admin corrects a decision only after the officer has
 * decided it (never over a hard rule), and may hand an undecided case to another officer.
 */
export default function AdminCorrection({ c, onDone }) {
  const [dialog, setDialog] = useState(null)
  const decided = ['confirmed', 'overridden'].includes(c.status)
  const canReassign = REASSIGNABLE.includes(c.status)
  return (
    <div className="admin-panel">
      <h3>Admin</h3>
      {decided && !c.admin_block && (
        <button type="button" className="btn btn-primary" onClick={() => setDialog('override')}>
          Change the decision
        </button>
      )}
      {c.admin_block && decided && <p className="small muted">{c.admin_block}</p>}
      {!decided && (
        <p className="small muted">
          An admin corrects a case only after the officer has decided it.
        </p>
      )}
      {canReassign && (
        <button type="button" className="btn" onClick={() => setDialog('reassign')}>
          Reassign to another officer
        </button>
      )}
      {dialog === 'override' && (
        <OverrideDialog
          caseId={c.id}
          inForce={c.decision_in_force}
          onClose={() => setDialog(null)}
          onDone={onDone}
        />
      )}
      {dialog === 'reassign' && (
        <ReassignDialog
          caseId={c.id}
          ownerId={c.officer_id}
          owner={c.officer}
          onClose={() => setDialog(null)}
          onDone={onDone}
        />
      )}
    </div>
  )
}
