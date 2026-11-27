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

/** One figure in the strip. The hint is kept for screen readers and as the hover text. */
function Stat({ label, value, hint, to, quiet = false }) {
  const inside = (
    <>
      <span className="stat-label">{label}</span>
      <span className={quiet ? 'stat-empty' : 'stat-value'}>{value}</span>
      <span className="sr-only">{hint}</span>
    </>
  )
  return (
    <li>
      {to ? (
        <Link to={to} className="stat" title={hint}>
          {inside}
        </Link>
      ) : (
        <div className="stat" title={hint}>
          {inside}
        </div>
      )}
    </li>
  )
}

/**
 * The officer's counts in one strip, then their own pace (Stage 12, `/me/insights`; never another
 * officer's numbers).
 */
function Summary({ counts, mine }) {
  const decided = mine?.decided_30d > 0
  return (
    <ul className="stats" aria-label="Case summary">
      {TILES.map((key) => (
        <Stat
          key={key}
          to={`/cases?view=${key}`}
          label={VIEWS[key].label}
          value={counts[key]}
          hint={HINT[key]}
        />
      ))}
      {mine && (
        <>
          <Stat
            label="Your median time to decide"
            value={decided ? duration(mine.median_decision_s) : 'No decisions yet'}
            quiet={!decided}
            hint="Report ready to your decision, last 30 days"
          />
          <Stat
            to="/cases?due=overdue"
            label="Overdue"
            value={mine.overdue}
            hint={`Past the ${mine.sla_working_days} working day target`}
          />
        </>
      )}
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
          <Summary counts={counts} mine={mine.data} />
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
