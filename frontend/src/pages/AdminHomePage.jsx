import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import StatusChip from '../components/StatusChip'
import { loanLabel } from '../components/LoanTypePicker'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import '../components/CaseQueueTable.css'
import './HomePage.css'

const TILES = [
  ['pending_precedents', 'Pending precedents', 'Waiting for your review', '/admin/precedents'],
  ['active_officers', 'Active officers', 'Can sign in and handle cases', '/admin/users'],
  ['disabled_accounts', 'Disabled accounts', 'Cannot sign in', '/admin/users'],
  ['open_issues', 'Open issues', 'Reported by officers', '/admin/issues'],
]

const STATUS = { confirmed: 'Confirmed', overridden: 'Overridden' }

/** The cases officers decided most recently, so the admin can find one to look at or correct. */
function RecentDecisions() {
  const { data, error, loading, reload } = useAsync(() => api.get('/admin/recent-decisions'), [])
  return (
    <section className="recent">
      <div className="recent-head">
        <h2>Recently decided by officers</h2>
      </div>
      {loading && <Skeleton lines={3} height={36} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <EmptyState title="Nothing decided yet">
          Cases appear here after an officer confirms or overrides them.
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <div className="card queue-wrap">
          <table className="queue">
            <thead>
              <tr>
                <th>Case no</th>
                <th>Loan</th>
                <th>Officer</th>
                <th>Officer decision</th>
                <th>Decided</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td data-label="Case no">
                    <Link to={`/cases/${c.id}`} className="mono">
                      {c.case_no}
                    </Link>
                  </td>
                  <td data-label="Loan">{loanLabel(c.loan_type)}</td>
                  <td data-label="Officer">{c.officer}</td>
                  <td data-label="Officer decision">
                    {STATUS[c.status]}{' '}
                    {c.corrected && <StatusChip tone="refer">Changed by an admin</StatusChip>}
                  </td>
                  <td data-label="Decided">{new Date(c.decided_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default function AdminHomePage() {
  const { data, error, loading, reload } = useAsync(() => api.get('/admin/summary'), [])
  return (
    <div className="home">
      <header className="home-head">
        <div>
          <h1>Home</h1>
          <p className="muted">
            Review precedents, read sent messages and issue reports, manage staff accounts, and open
            any officer&apos;s case. You correct a decision after the officer has made it.
          </p>
        </div>
      </header>
      {loading && <Skeleton lines={3} height={56} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <ul className="tiles tiles-4" aria-label="Admin summary">
          {TILES.map(([key, label, hint, to]) => (
            <li key={key}>
              <Link to={to} className="tile card rise">
                <span className="tile-count">{data[key]}</span>
                <span className="tile-label">{label}</span>
                <span className="tile-hint small muted">{hint}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <RecentDecisions />
    </div>
  )
}
