import { useState } from 'react'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import './AuditorTable.css'

const PAGE = 100

const detail = (r) => {
  const d = r.after ?? r.before
  return d ? JSON.stringify(d) : ''
}

/** The append-only audit log, newest first, with a filter on the action. */
export default function AuditorAuditLogPage() {
  const [action, setAction] = useState('')
  const [page, setPage] = useState(0)
  const actions = useAsync(() => api.get('/auditor/audit-log/actions'), [])
  const { data, error, loading, reload } = useAsync(() => {
    const p = new URLSearchParams({ limit: PAGE, offset: page * PAGE })
    if (action) p.set('action', action)
    return api.get(`/auditor/audit-log?${p}`)
  }, [action, page])
  return (
    <div className="aud-page">
      <header>
        <h1>Audit log</h1>
        <p className="muted">Who did what, and when. Entries cannot be changed or removed.</p>
      </header>
      <div className="field aud-filter">
        <label htmlFor="aud-action">Action</label>
        <select
          id="aud-action"
          className="select"
          value={action}
          onChange={(e) => {
            setAction(e.target.value)
            setPage(0)
          }}
        >
          <option value="">All actions</option>
          {(actions.data ?? []).map((a) => (
            <option key={a} value={a}>
              {a.replaceAll('_', ' ')}
            </option>
          ))}
        </select>
      </div>
      {loading && <Skeleton lines={5} height={32} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.rows.length === 0 && (
        <EmptyState title="Nothing logged">No entries.</EmptyState>
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
                      {r.case_no ?? ''}
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
