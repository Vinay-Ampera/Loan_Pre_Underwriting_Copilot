import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { ErrorState, Skeleton } from '../components/States'
import './HomePage.css'

const TILES = [
  ['pending_precedents', 'Pending precedents', 'Waiting for your review', '/admin/precedents'],
  ['active_officers', 'Active officers', 'Can sign in and handle cases', '/admin/users'],
  ['disabled_accounts', 'Disabled accounts', 'Cannot sign in', '/admin/users'],
  ['open_issues', 'Open issues', 'Reported by officers', '/admin/issues'],
]

export default function AdminHomePage() {
  const { data, error, loading, reload } = useAsync(() => api.get('/admin/summary'), [])
  return (
    <div className="home">
      <header className="home-head">
        <div>
          <h1>Home</h1>
          <p className="muted">
            Review precedents, read issue reports and manage staff accounts. Admins have no access
            to case data. Messages sent by officers are shown here as counts only.
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
    </div>
  )
}
