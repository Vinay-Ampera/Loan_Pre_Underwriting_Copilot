import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import Dialog from '../components/Dialog'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import { CATEGORIES, IssueChip } from './IssuesPage'
import './AdminIssuesPage.css'

const FILTERS = [
  ['open', 'Open'],
  ['read', 'Read'],
  ['closed', 'Closed'],
  ['', 'All'],
]
const categoryLabel = (c) => CATEGORIES.find((x) => x[0] === c)?.[1] || c

/** The admin's inbox. It holds no case data: only a plain case reference, a category and text. */
export default function AdminIssuesPage() {
  const [filter, setFilter] = useState('open')
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/admin/issues${filter ? `?status=${filter}` : ''}`),
    [filter],
  )
  const [open, setOpen] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)

  async function view(issue) {
    setActionError(null)
    try {
      setOpen(await api.post(`/admin/issues/${issue.id}/read`))
      reload()
    } catch (e) {
      setActionError(e.message)
    }
  }
  async function close() {
    setBusy(true)
    try {
      await api.post(`/admin/issues/${open.id}/close`)
      setOpen(null)
      reload()
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="admin-issues">
      <header>
        <h1>Issues</h1>
        <p className="muted">
          Problems reported by officers. Opening one marks it read. Reports hold no case data.
        </p>
      </header>
      <div className="tabs" role="tablist" aria-label="Issue status">
        {FILTERS.map(([key, label]) => (
          <button
            key={label}
            role="tab"
            type="button"
            aria-selected={filter === key}
            className={`tab${filter === key ? ' on' : ''}`}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {loading && <Skeleton lines={3} height={48} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <EmptyState title="Nothing here">No issues in this list.</EmptyState>
      )}
      {data && data.length > 0 && (
        <ul className="card issue-rows">
          {data.map((i) => (
            <li key={i.id}>
              <div>
                <p className="issue-title">
                  {i.body.length > 120 ? `${i.body.slice(0, 120)}…` : i.body}
                </p>
                <p className="small muted">
                  {i.reporter} · {categoryLabel(i.category)}
                  {i.case_ref && ` · ${i.case_ref}`} · {new Date(i.created_at).toLocaleString()}
                </p>
              </div>
              <IssueChip status={i.status} />
              <button type="button" className="btn" onClick={() => view(i)}>
                Open<span className="sr-only"> report from {i.reporter}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {actionError && !open && (
        <p className="field-error" role="alert">
          {actionError}
        </p>
      )}
      {open && (
        <Dialog title="Issue report" onClose={() => setOpen(null)} labelledBy="issue-title">
          <p className="small muted">
            {open.reporter} · {categoryLabel(open.category)}
            {open.case_ref && ` · ${open.case_ref}`} · <IssueChip status={open.status} />
          </p>
          <p className="issue-body">{open.body}</p>
          {actionError && (
            <p className="field-error" role="alert">
              {actionError}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => setOpen(null)} data-autofocus>
              Close window
            </button>
            {open.status !== 'closed' && (
              <button type="button" className="btn btn-primary" disabled={busy} onClick={close}>
                Mark as closed
              </button>
            )}
          </div>
        </Dialog>
      )}
    </div>
  )
}
