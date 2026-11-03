import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import BarChart from '../components/BarChart'
import { loanLabel } from '../components/LoanTypePicker'
import { ErrorState, Skeleton } from '../components/States'
import './HomePage.css'
import './AuditorOverviewPage.css'

const TILES = [
  ['cases', 'Cases', 'All officers', '/cases'],
  ['awaiting_confirmation', 'Awaiting confirmation', 'Not yet decided by an officer', '/cases'],
  ['overridden', 'Overrides', 'Officer decisions that differ', '/auditor/audit-log'],
  ['pending_precedents', 'Pending precedents', 'Waiting for an admin', '/auditor/precedents'],
]

const STATUS = {
  draft: 'Draft',
  uploaded: 'Documents uploaded',
  running: 'Assessing',
  stopped: 'Stopped',
  awaiting_confirmation: 'Awaiting confirmation',
  confirmed: 'Confirmed',
  overridden: 'Overridden',
}
const BAND = { approve: 'Recommend approve', refer: 'Refer', reject: 'Recommend reject' }

const ATTRIBUTE = { gender: 'Gender', age_band: 'Age band', city_tier: 'City tier' }

const fromMap = (map, names) =>
  Object.entries(map).map(([k, value]) => ({ label: names?.[k] ?? k, value }))

/** Charts are built from counts the server reads out of Postgres; no case-level rows are here. */
export default function AuditorOverviewPage() {
  const summary = useAsync(() => api.get('/auditor/summary'), [])
  const charts = useAsync(() => api.get('/auditor/charts'), [])
  const c = charts.data
  const groups = useAsync(() => api.get('/auditor/fairness'), [])
  const actions = {}
  for (const a of c?.officer_actions_by_loan_type ?? []) {
    actions[a.loan_type] ??= { confirm: 0, override: 0 }
    actions[a.loan_type][a.action] = a.count
  }
  return (
    <div className="home auditor-overview">
      <header className="home-head">
        <div>
          <h1>Overview</h1>
          <p className="muted">
            A read-only view of the whole system, built from our own database. Applicant names and
            identifiers are masked, and original documents are not available to this role.
          </p>
        </div>
      </header>
      {summary.loading && <Skeleton lines={3} height={56} />}
      {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}
      {summary.data && (
        <ul className="tiles tiles-4" aria-label="Summary">
          {TILES.map(([key, label, hint, to]) => (
            <li key={key}>
              <Link to={to} className="tile card rise">
                <span className="tile-count">{summary.data[key]}</span>
                <span className="tile-label">{label}</span>
                <span className="tile-hint small muted">{hint}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {charts.loading && <Skeleton lines={4} height={80} />}
      {charts.error && <ErrorState error={charts.error} onRetry={charts.reload} />}
      {c && (
        <div className="charts">
          <BarChart
            title="Recommended band"
            rows={fromMap(c.cases_by_band, BAND).map((r, i) => ({
              ...r,
              tone: ['approve', 'refer', 'reject'][i],
            }))}
          />
          <BarChart title="Cases by status" rows={fromMap(c.cases_by_status, STATUS)} />
          <BarChart
            title="Cases by loan type"
            rows={Object.entries(c.cases_by_loan_type).map(([k, value]) => ({
              label: loanLabel(k),
              value,
            }))}
          />
          <BarChart
            title="Score distribution"
            rows={c.score_histogram.map((b) => ({ label: `${b.from} to ${b.to}`, value: b.count }))}
          />
          <BarChart
            title="Confirmed by loan type"
            rows={Object.entries(actions).map(([k, v]) => ({
              label: loanLabel(k),
              value: v.confirm,
            }))}
          />
          <BarChart
            title="Overridden by loan type"
            rows={Object.entries(actions).map(([k, v]) => ({
              label: loanLabel(k),
              value: v.override,
              tone: 'refer',
            }))}
          />
          <BarChart
            title="Cases created per week (last 12 weeks)"
            rows={c.cases_per_week.map((w) => ({ label: w.week, value: w.count }))}
          />
          <BarChart
            title="Rules most often failed"
            rows={c.top_failed_rules.map((r) => ({
              label: r.rule_id,
              value: r.count,
              tone: r.kind === 'hard' ? 'reject' : 'refer',
            }))}
          />
        </div>
      )}
      {groups.data && (
        <section className="group-outcomes" aria-labelledby="group-title">
          <h2 id="group-title">Recommended-approve rate by group</h2>
          <p className="muted small">
            Monitoring only: it changes no rule, score or decision, and a gap is a prompt to look,
            not proof of bias. Groups with fewer than {groups.data.min_group} cases are not shown.
            These are percentages by group, never case rows.
          </p>
          <div className="charts">
            {Object.entries(groups.data.attributes).map(([attr, info]) => (
              <BarChart
                key={attr}
                title={`${ATTRIBUTE[attr] ?? attr}${info.flag ? ' · gap to review' : ''} (%)`}
                empty="No groups yet."
                rows={info.groups.map((g) =>
                  g.too_few
                    ? { label: g.group, value: 0, note: 'too few to show' }
                    : { label: `${g.group} (${g.n})`, value: Math.round(g.approve_rate * 100) },
                )}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
