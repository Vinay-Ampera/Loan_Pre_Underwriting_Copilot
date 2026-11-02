import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useSession } from '../App'
import { useAsync } from '../hooks/useAsync'
import CaseQueueTable from '../components/CaseQueueTable'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import { VIEWS, tileCounts } from '../lib/views'
import './HomePage.css'

const TILES = ['awaiting', 'referred', 'stopped', 'progress']
const HINT = {
  awaiting: 'Ready for your decision',
  referred: 'Recommended: refer',
  stopped: 'Need a correction or are ineligible',
  progress: 'Draft, uploaded or being assessed',
}

export default function HomePage() {
  const { session } = useSession()
  const { data, error, loading, reload } = useAsync(() => api.get('/cases'), [])
  const counts = data ? tileCounts(data) : null
  return (
    <div className="home">
      <header className="home-head">
        <div>
          <h1>Home</h1>
          <p className="muted">Welcome, {session.user.name}. A human confirms every case.</p>
        </div>
        <Link to="/cases/new" className="btn btn-primary">
          New case
        </Link>
      </header>
      {loading && <Skeleton lines={4} height={56} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <>
          <ul className="tiles" aria-label="Case summary">
            {TILES.map((key) => (
              <li key={key}>
                <Link to={`/cases?view=${key}`} className="tile card rise">
                  <span className="tile-count">{counts[key]}</span>
                  <span className="tile-label">{VIEWS[key].label}</span>
                  <span className="tile-hint small muted">{HINT[key]}</span>
                </Link>
              </li>
            ))}
          </ul>
          <section className="recent">
            <div className="recent-head">
              <h2>Recent cases</h2>
              <Link to="/cases">All cases</Link>
            </div>
            {data.length === 0 ? (
              <EmptyState
                title="No cases yet"
                action={
                  <Link to="/cases/new" className="btn">
                    Start a new case
                  </Link>
                }
              >
                Cases you create appear here.
              </EmptyState>
            ) : (
              <CaseQueueTable cases={data.slice(0, 6)} />
            )}
          </section>
        </>
      )}
    </div>
  )
}
