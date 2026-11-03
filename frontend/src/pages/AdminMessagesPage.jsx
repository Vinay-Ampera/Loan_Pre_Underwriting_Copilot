import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import Dialog from '../components/Dialog'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import { filterMessages, isFiltered, NO_FILTER } from '../lib/messageFilter'
import '../components/MessageDialog.css'
import './SentItemsPage.css'

const unique = (rows, key, label) => {
  const seen = new Map()
  for (const r of rows) if (!seen.has(r[key])) seen.set(r[key], r[label])
  return [...seen].sort((a, b) => a[1].localeCompare(b[1]))
}

/** Messages the officers sent to customers. Sent ones only (no drafts), read-only, filterable. */
export default function AdminMessagesPage() {
  const { data, error, loading, reload } = useAsync(() => api.get('/admin/messages'), [])
  const [filter, setFilter] = useState(NO_FILTER)
  const [open, setOpen] = useState(null)
  const set = (patch) => setFilter((f) => ({ ...f, ...patch }))
  const shown = data ? filterMessages(data, { ...filter, status: 'all' }) : []
  const officers = data ? unique(data, 'officer_id', 'officer') : []
  const templates = data ? unique(data, 'template', 'template_label') : []
  return (
    <div className="sent-items">
      <header>
        <h1>Messages</h1>
        <p className="muted">
          Contact requests that officers sent to customers. Only sent messages are listed, and
          nothing can be sent or changed here.
        </p>
      </header>
      {loading && <Skeleton lines={4} height={40} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <EmptyState title="No messages sent yet">Sent messages appear here.</EmptyState>
      )}
      {data && data.length > 0 && (
        <div className="card sent-filters">
          <div className="sent-fields">
            <div className="field">
              <label htmlFor="adm-officer">Officer</label>
              <select
                id="adm-officer"
                className="select"
                value={filter.officer}
                onChange={(e) => set({ officer: e.target.value })}
              >
                <option value="">All officers</option>
                {officers.map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="adm-template">Template</label>
              <select
                id="adm-template"
                className="select"
                value={filter.template}
                onChange={(e) => set({ template: e.target.value })}
              >
                <option value="">All templates</option>
                {templates.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="adm-q">Case number</label>
              <input
                id="adm-q"
                className="input"
                type="search"
                placeholder="CASE-2026-0003"
                value={filter.query}
                onChange={(e) => set({ query: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="adm-from">From</label>
              <input
                id="adm-from"
                className="input"
                type="date"
                value={filter.from}
                max={filter.to || undefined}
                onChange={(e) => set({ from: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="adm-to">To</label>
              <input
                id="adm-to"
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
              disabled={!isFiltered({ ...filter, status: 'all' })}
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
      {shown.length > 0 && (
        <div className="card sent-wrap">
          <table className="sent">
            <thead>
              <tr>
                <th>Sent</th>
                <th>Case</th>
                <th>Officer</th>
                <th>Template</th>
                <th>To</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((m) => (
                <tr key={m.id}>
                  <td data-label="Sent">{new Date(m.sent_at).toLocaleString()}</td>
                  <td data-label="Case">
                    <Link to={`/cases/${m.case_id}`} className="mono">
                      {m.case_no}
                    </Link>
                  </td>
                  <td data-label="Officer">{m.officer}</td>
                  <td data-label="Template">{m.template_label}</td>
                  <td data-label="To">{m.recipient}</td>
                  <td className="row-actions">
                    <button type="button" className="btn" onClick={() => setOpen(m)}>
                      Open
                      <span className="sr-only"> message to {m.recipient}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && (
        <Dialog title="Message" onClose={() => setOpen(null)} labelledBy="adm-msg-title">
          <p className="small muted">
            <span className="mono">{open.case_no}</span> · {open.officer} to {open.recipient}
          </p>
          <pre className="msg-final">{open.text}</pre>
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => setOpen(null)} data-autofocus>
              Close
            </button>
          </div>
        </Dialog>
      )}
    </div>
  )
}
