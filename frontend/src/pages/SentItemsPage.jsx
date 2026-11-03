import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import Dialog from '../components/Dialog'
import ConfirmDialog from '../components/ConfirmDialog'
import MessageDialog from '../components/MessageDialog'
import StatusChip from '../components/StatusChip'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import { filterMessages, isFiltered, NO_FILTER, STATUS_FILTERS } from '../lib/messageFilter'
import './SentItemsPage.css'

export const MESSAGE_STATUS = {
  sent: ['done', 'Sent'],
  failed: ['reject', 'Failed'],
  blocked: ['refer', 'Blocked'],
  draft: ['neutral', 'Draft'],
}

export function MessageChip({ status }) {
  const [tone, label] = MESSAGE_STATUS[status] || ['neutral', status]
  return <StatusChip tone={tone}>{label}</StatusChip>
}

/** Read one message. A failed one can be sent again: the button here is the second click. */
function ViewDialog({ id, onClose, onChanged }) {
  const { data: m, error, loading } = useAsync(() => api.get(`/messages/${id}`), [id])
  const [busy, setBusy] = useState(false)
  const [sendError, setSendError] = useState(null)

  async function again() {
    setBusy(true)
    setSendError(null)
    try {
      await api.post(`/messages/${id}/send`, { second_click: true })
      onChanged()
      onClose()
    } catch (e) {
      setSendError(e.message)
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog title="Message" onClose={onClose} labelledBy="view-msg-title">
      {loading && <Skeleton lines={5} />}
      {error && (
        <p className="field-error" role="alert">
          {error.message}
        </p>
      )}
      {m && (
        <>
          <p className="small muted">
            <span className="mono">{m.case_no}</span> · To {m.recipient} ·{' '}
            <MessageChip status={m.status} />
          </p>
          <pre className="msg-final">{m.text}</pre>
          {m.status === 'failed' && (
            <p className="small">This message could not be sent. You can send it again.</p>
          )}
          {m.status === 'blocked' && (
            <p className="small">Blocked: {m.block_reason}. Edit it to continue.</p>
          )}
          {sendError && (
            <p className="field-error" role="alert">
              {sendError}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={onClose}>
              Close
            </button>
            {m.status === 'failed' && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={again}
                data-autofocus
              >
                Yes, send again
              </button>
            )}
          </div>
        </>
      )}
    </Dialog>
  )
}

export default function SentItemsPage() {
  const { data, error, loading, reload } = useAsync(() => api.get('/messages'), [])
  const [view, setView] = useState(null)
  const [edit, setEdit] = useState(null)
  const [remove, setRemove] = useState(null)
  const [removing, setRemoving] = useState(false)
  const [removeError, setRemoveError] = useState(null)
  const [filter, setFilter] = useState(NO_FILTER)
  const set = (patch) => setFilter((f) => ({ ...f, ...patch }))
  const shown = data ? filterMessages(data, filter) : []

  async function confirmDelete() {
    setRemoving(true)
    setRemoveError(null)
    try {
      await api.del(`/messages/${remove.id}`)
      setRemove(null)
      reload()
    } catch (e) {
      setRemoveError(e.message)
    } finally {
      setRemoving(false)
    }
  }

  return (
    <div className="sent-items">
      <header>
        <h1>Sent items</h1>
        <p className="muted">
          Your messages to customers. In this version they are printed in the backend terminal
          instead of being emailed. You see only your own messages.
        </p>
      </header>
      {loading && <Skeleton lines={4} height={40} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <EmptyState title="No messages yet">
          Open a confirmed or stopped case and choose Contact the customer.
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <div className="card sent-filters">
          <div className="sent-status" role="group" aria-label="Filter by status">
            {STATUS_FILTERS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`btn sent-pill${filter.status === key ? ' is-on' : ''}`}
                aria-pressed={filter.status === key}
                onClick={() => set({ status: key })}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="sent-fields">
            <div className="field">
              <label htmlFor="sent-q">Case number</label>
              <input
                id="sent-q"
                className="input"
                type="search"
                placeholder="CASE-2026-0003"
                value={filter.query}
                onChange={(e) => set({ query: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="sent-from">From</label>
              <input
                id="sent-from"
                className="input"
                type="date"
                value={filter.from}
                max={filter.to || undefined}
                onChange={(e) => set({ from: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="sent-to">To</label>
              <input
                id="sent-to"
                className="input"
                type="date"
                value={filter.to}
                min={filter.from || undefined}
                onChange={(e) => set({ to: e.target.value })}
              />
            </div>
            <button
              type="button"
              className="btn"
              disabled={!isFiltered(filter)}
              onClick={() => setFilter(NO_FILTER)}
            >
              Clear filters
            </button>
          </div>
          <p className="small muted" role="status">
            Showing {shown.length} of {data.length}
          </p>
        </div>
      )}
      {data && data.length > 0 && shown.length === 0 && (
        <EmptyState title="No messages match">Change or clear the filters to see more.</EmptyState>
      )}
      {data && shown.length > 0 && (
        <div className="card sent-wrap">
          <table className="sent">
            <thead>
              <tr>
                <th>Date</th>
                <th>Case</th>
                <th>Template</th>
                <th>To</th>
                <th>Status</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((m) => (
                <tr key={m.id}>
                  <td data-label="Date">{new Date(m.sent_at || m.created_at).toLocaleString()}</td>
                  <td data-label="Case">
                    <Link to={`/cases/${m.case_id}`} className="mono">
                      {m.case_no}
                    </Link>
                  </td>
                  <td data-label="Template">{m.template_label}</td>
                  <td data-label="To">{m.recipient}</td>
                  <td data-label="Status">
                    <MessageChip status={m.status} />
                  </td>
                  <td className="row-actions">
                    <button type="button" className="btn" onClick={() => setView(m.id)}>
                      {m.status === 'failed' ? 'Retry' : 'Open'}
                      <span className="sr-only"> message to {m.recipient}</span>
                    </button>
                    {(m.status === 'draft' || m.status === 'blocked') && (
                      <button type="button" className="btn" onClick={() => setEdit(m)}>
                        Edit
                      </button>
                    )}
                    {(m.status === 'draft' || m.status === 'blocked') && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => {
                          setRemoveError(null)
                          setRemove(m)
                        }}
                      >
                        Delete
                        <span className="sr-only"> message to {m.recipient}</span>
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {view && <ViewDialog id={view} onClose={() => setView(null)} onChanged={reload} />}
      {remove && (
        <ConfirmDialog
          title="Delete this draft?"
          confirmLabel="Yes, delete"
          busy={removing}
          error={removeError}
          onClose={() => setRemove(null)}
          onConfirm={confirmDelete}
        >
          <p>
            The unsent {remove.status === 'blocked' ? 'blocked message' : 'draft'} for{' '}
            <span className="mono">{remove.case_no}</span> will be removed. Nothing has been sent to
            the customer, and this cannot be undone.
          </p>
        </ConfirmDialog>
      )}
      {edit && (
        <MessageDialog
          caseId={edit.case_id}
          existing={edit}
          onClose={() => setEdit(null)}
          onDone={reload}
        />
      )}
    </div>
  )
}
