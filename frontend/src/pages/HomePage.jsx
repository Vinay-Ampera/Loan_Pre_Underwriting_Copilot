import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import CaseQueueTable from '../components/CaseQueueTable'
import { EmptyState, ErrorState } from '../components/States'
import { VIEWS, tileCounts } from '../lib/views'
import { duration } from '../lib/format'
import './HomePage.css'
import { SectionLoader } from '../components/Loading'

const TILES = ['awaiting', 'referred', 'stopped', 'progress']
const HINT = {
  awaiting: 'Ready for your decision',
  referred: 'Recommended: refer',
  stopped: 'Need a correction or are ineligible',
  progress: 'Draft, uploaded or being assessed',
}

/** The officer's own pace (Stage 12 Part B, `/me/insights`); never another officer's numbers. */
function YourPace({ mine }) {
  const decided = mine.decided_30d > 0
  return (
    <ul className="tiles" aria-label="Your pace">
      <li>
        <div className="tile tile-static card">
          <span className={decided ? 'tile-count tile-time' : 'tile-empty'}>
            {decided ? duration(mine.median_decision_s) : 'No decisions yet'}
          </span>
          <span className="tile-label">Your median time to decide</span>
          <span className="tile-hint small muted">Report ready to your decision, last 30 days</span>
        </div>
      </li>
      <li>
        <Link to="/cases?due=overdue" className="tile card">
          <span className="tile-count">{mine.overdue}</span>
          <span className="tile-label">Overdue</span>
          <span className="tile-hint small muted">
            Past the {mine.sla_working_days} working day target
          </span>
        </Link>
      </li>
    </ul>
  )
}

export default function HomePage() {
  const { data, error, loading, reload } = useAsync(() => api.get('/cases'), [])
  const mine = useAsync(() => api.get('/me/insights'), [])
  const counts = data ? tileCounts(data) : null
  return (
    <div className="home">
      <header className="home-head">
        <div>
          <h1>Home</h1>
          <p className="muted">
            Your cases and what is waiting on you. A human confirms every case.
          </p>
        </div>
        <Link to="/cases/new" className="btn btn-primary">
          New case
        </Link>
      </header>
      {loading && <SectionLoader label="Loading your cases" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <>
          {counts.applicant > 0 && (
            <p className="corrected-note" role="status">
              {counts.applicant === 1
                ? 'An applicant has sent documents for you to review.'
                : `${counts.applicant} applicants have sent documents for you to review.`}{' '}
              <Link to="/cases?view=applicant">Review them</Link>
            </p>
          )}
          {counts.corrected > 0 && (
            <p className="corrected-note" role="status">
              An admin changed the decision on {counts.corrected} of your cases.{' '}
              <Link to="/cases?view=corrected">See which</Link>
            </p>
          )}
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
          {mine.data && <YourPace mine={mine.data} />}
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
