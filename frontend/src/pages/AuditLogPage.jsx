import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { downloadFile, queryOf } from '../lib/download'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import './AuditorTable.css'

const PAGE = 100
const NONE = { action: '', actor: '', case_no: '', date_from: '', date_to: '' }

const detail = (r) => {
  const d = r.after ?? r.before
  return d ? JSON.stringify(d) : ''
}

/**
 * The append-only audit log, newest first, with filters and a CSV export. Only the auditor reads
 * it, with identifiers masked and without links into cases.
 */
export default function AuditLogPage() {
  const base = '/auditor'
  const [filter, setFilter] = useState(NONE)
  const [page, setPage] = useState(0)
  const [exportError, setExportError] = useState(null)
  const actions = useAsync(() => api.get(`${base}/audit-log/actions`), [base])
  const users = useAsync(() => api.get('/auditor/users'), [])
  const { data, error, loading, reload } = useAsync(
    () => api.get(`${base}/audit-log?${queryOf(filter, { limit: PAGE, offset: page * PAGE })}`),
    [base, filter, page],
  )
  const set = (patch) => {
    setFilter((f) => ({ ...f, ...patch }))
    setPage(0)
  }
  const filtered = Object.values(filter).some(Boolean)
  async function exportCsv() {
    setExportError(null)
    try {
      await downloadFile(`${base}/audit-log.csv?${queryOf(filter)}`, 'audit-log.csv')
    } catch (e) {
      setExportError(e.message)
    }
  }
  return (
    <div className="aud-page">
      <header>
        <h1>Audit log</h1>
        <p className="muted">
          Who did what, and when. Entries cannot be changed or removed. Identifiers are masked.
        </p>
      </header>
      <div className="card aud-filters" role="search">
        <div className="field">
          <label htmlFor="aud-action">Action</label>
          <select
            id="aud-action"
            className="select"
            value={filter.action}
            onChange={(e) => set({ action: e.target.value })}
          >
            <option value="">All actions</option>
            {(actions.data ?? []).map((a) => (
              <option key={a} value={a}>
                {a.replaceAll('_', ' ')}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="aud-user">User</label>
          <select
            id="aud-user"
            className="select"
            value={filter.actor}
            onChange={(e) => set({ actor: e.target.value })}
          >
            <option value="">All users</option>
            {(users.data ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="aud-case">Case reference</label>
          <input
            id="aud-case"
            className="input"
            type="search"
            placeholder="CASE-2026-0003"
            value={filter.case_no}
            onChange={(e) => set({ case_no: e.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="aud-from">From</label>
          <input
            id="aud-from"
            className="input"
            type="date"
            value={filter.date_from}
            max={filter.date_to || undefined}
            onChange={(e) => set({ date_from: e.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="aud-to">To</label>
          <input
            id="aud-to"
            className="input"
            type="date"
            value={filter.date_to}
            min={filter.date_from || undefined}
            onChange={(e) => set({ date_to: e.target.value })}
          />
        </div>
        <button type="button" className="btn" disabled={!filtered} onClick={() => set(NONE)}>
          Clear filters
        </button>
        <button type="button" className="btn" onClick={exportCsv}>
          Export CSV
        </button>
      </div>
      {exportError && (
        <p className="field-error" role="alert">
          {exportError}
        </p>
      )}
      {loading && <Skeleton lines={5} height={32} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.rows.length === 0 && (
        <EmptyState title="Nothing logged">No entries match.</EmptyState>
      )}
      {data && data.rows.length > 0 && (
        <>
          <div className="card aud-wrap">
            <table className="aud-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Case</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={`${r.at}-${i}`}>
                    <td data-label="When">{new Date(r.at).toLocaleString()}</td>
                    <td data-label="Actor">
                      {r.actor} {r.actor_role && <span className="muted">({r.actor_role})</span>}
                    </td>
                    <td data-label="Action">{r.action.replaceAll('_', ' ')}</td>
                    <td data-label="Case" className="mono">
                      {r.case_no}
                    </td>
                    <td data-label="Detail" className="aud-detail small muted">
                      {detail(r)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="aud-pager">
            <button
              type="button"
              className="btn"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              Newer
            </button>
            <span className="small muted">
              {page * PAGE + 1} to {page * PAGE + data.rows.length} of {data.total}
            </span>
            <button
              type="button"
              className="btn"
              disabled={(page + 1) * PAGE >= data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              Older
            </button>
          </div>
        </>
      )}
    </div>
  )
}
