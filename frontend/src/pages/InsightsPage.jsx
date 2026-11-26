import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import BarChart from '../components/BarChart'
import StatusChip from '../components/StatusChip'
import { LOAN_TYPES, loanLabel } from '../components/LoanTypePicker'
import { SectionLoader } from '../components/Loading'
import { EmptyState, ErrorState } from '../components/States'
import { duration, formatDay } from '../lib/format'
import './InsightsPage.css'

// Wording: docs/DESIGN_SYSTEM.md 17.2. "Changed by the officer", never "overridden" alone or
// "approved". The admin's copy has case references and links; the auditor's has neither.
const BAND = { approve: 'Recommend approve', refer: 'Refer', reject: 'Recommend reject' }
const NO_FILTERS = { from: '', to: '', loan: '' }

const local = (day, plusDays = 0) => {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(y, m - 1, d + plusDays) // the reader's own midnight
}

function query({ from, to, loan }) {
  const q = new URLSearchParams()
  if (from) q.set('start', local(from).toISOString())
  if (to) q.set('end', local(to, 1).toISOString()) // the whole of the last day
  if (loan) q.set('loan_type', loan)
  const s = q.toString()
  return s ? `?${s}` : ''
}

function showing({ from, to, loan }) {
  const what = loan ? `${loanLabel(loan).toLowerCase()} cases` : 'cases'
  if (from && to)
    return `Showing ${what} created ${formatDay(local(from))} to ${formatDay(local(to))}.`
  if (from) return `Showing ${what} created from ${formatDay(local(from))}.`
  if (to) return `Showing ${what} created up to ${formatDay(local(to))}.`
  return `Showing all ${what}.`
}

const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0)
const direction = (from, to) => {
  const text = `${from} → ${to} (officer)`
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** The admin opens the cases behind a count; the auditor only sees the count. */
function CaseCount({ n, cases, admin, label }) {
  if (!admin || !cases?.length) return <span className="mono">{n}</span>
  return (
    <details className="ins-cases">
      <summary>
        {label ?? (
          <>
            <span className="mono">{n}</span>
            <span className="small"> · show cases</span>
          </>
        )}
      </summary>
      <ul>
        {cases.map((c) => (
          <li key={c.id}>
            <Link to={`/cases/${c.id}`} className="mono">
              {c.case_no}
            </Link>
          </li>
        ))}
      </ul>
    </details>
  )
}

function Clause({ row, admin }) {
  if (!row.clause_id) return <span className="muted">–</span>
  if (!admin || !row.clause_doc) return <span className="mono ref-id">{row.clause_id}</span>
  const to = `/admin/knowledge?doc=${row.clause_doc}&clause=${encodeURIComponent(row.clause_id)}`
  return (
    <Link to={to} className="mono ref-id" title="Open the clause in the knowledge base">
      {row.clause_id}
    </Link>
  )
}

function Stat({ label, seconds, slowest, n }) {
  return (
    <div className="ins-stat card">
      <span className="ins-stat-label">{label}</span>
      <span className="ins-stat-value">{n ? duration(seconds) : 'No cases yet'}</span>
      {n > 0 && (
        <span className="small muted">
          median of {n} case{n === 1 ? '' : 's'} · slowest: {duration(slowest)}
        </span>
      )}
    </div>
  )
}

function TimePanel({ t }) {
  return (
    <section className="ins-panel" aria-labelledby="ins-time">
      <h2 id="ins-time">Time to decide</h2>
      <div className="ins-stats">
        <Stat
          label="Report ready after"
          seconds={t.report_ready.median_s}
          slowest={t.report_ready.slowest_s}
          n={t.report_ready.n}
        />
        <Stat
          label="Officer decided after"
          seconds={t.officer_decided.median_s}
          slowest={t.officer_decided.slowest_s}
          n={t.officer_decided.n}
        />
      </div>
      <div className="charts">
        <BarChart
          title="Officer decision time by loan type (median)"
          empty="No decisions in this period."
          valueWidth="10ch"
          rows={t.by_loan_type.map((r) => ({
            label: `${loanLabel(r.loan_type)} (${r.n})`,
            value: r.median_s,
            display: duration(r.median_s),
          }))}
        />
        <BarChart
          title="Decision time by officer (median)"
          empty="No decisions in this period."
          valueWidth="10ch"
          rows={t.by_officer.map((r) => ({
            label: `${r.officer} (${r.n})`,
            value: r.median_s,
            display: duration(r.median_s),
          }))}
        />
      </div>
    </section>
  )
}

function FunnelPanel({ f }) {
  return (
    <section className="ins-panel" aria-labelledby="ins-funnel">
      <h2 id="ins-funnel">Where cases are</h2>
      <div className="charts">
        <BarChart
          title="From created to decided"
          foot="Submitted: the officer sent the file for assessment (documents complete)."
          rows={[
            { label: 'Created', value: f.created },
            { label: 'Submitted', value: f.submitted },
            { label: 'Report ready', value: f.report_ready },
            { label: 'Decided by the officer', value: f.decided },
            { label: 'Confirmed', value: f.confirmed },
            { label: 'Changed by the officer', value: f.changed },
          ]}
        />
        <BarChart
          title="Open now"
          empty="No open cases."
          rows={[
            { label: 'Not submitted', value: f.not_submitted },
            { label: 'Being assessed', value: f.running },
            { label: 'Stopped for a fix', value: f.stopped },
            { label: 'Waiting for the officer', value: f.waiting },
          ]}
        />
      </div>
    </section>
  )
}

function AgreementPanel({ a }) {
  const total = a.confirmed + a.changed
  const share = (r, label) => ({
    label,
    value: pct(r.confirmed, r.confirmed + r.changed),
    display: `${pct(r.confirmed, r.confirmed + r.changed)}% of ${r.confirmed + r.changed}`,
  })
  return (
    <section className="ins-panel" aria-labelledby="ins-agree">
      <h2 id="ins-agree">Officer agreement</h2>
      <p>
        {total === 0
          ? 'No officer decisions in this period.'
          : `Confirmed ${a.confirmed} (${pct(a.confirmed, total)}%) · Changed by the officer ${a.changed} (${pct(a.changed, total)}%)`}
      </p>
      <p className="small muted">Admin corrections: {a.admin_corrections}</p>
      <div className="charts">
        <BarChart
          title="Confirmed, by loan type"
          empty="No officer decisions in this period."
          max={100}
          valueWidth="9ch"
          rows={a.by_loan_type.map((r) => share(r, loanLabel(r.loan_type)))}
        />
        <BarChart
          title="Confirmed, by recommended band"
          empty="No officer decisions in this period."
          max={100}
          valueWidth="9ch"
          rows={a.by_band.map((r) => share(r, BAND[r.band] ?? r.band))}
        />
      </div>
    </section>
  )
}

function RulesPanel({ rows, admin }) {
  return (
    <section className="ins-panel" aria-labelledby="ins-rules">
      <h2 id="ins-rules">Rules in changed decisions</h2>
      {rows.length === 0 ? (
        <p className="muted">No decision was changed by an officer in this period.</p>
      ) : (
        <div className="card ins-wrap">
          <table className="ins-table">
            <thead>
              <tr>
                <th scope="col">Rule</th>
                <th scope="col">Clause</th>
                <th scope="col">Change</th>
                <th scope="col">Cases</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.rule_id}-${r.from}-${r.to}`}>
                  <td data-label="Rule">
                    <div>
                      <span className="mono ref-id">{r.rule_id}</span>
                      {r.clause_title && <span className="ins-title small">{r.clause_title}</span>}
                    </div>
                  </td>
                  <td data-label="Clause">
                    <Clause row={r} admin={admin} />
                  </td>
                  <td data-label="Change">
                    <StatusChip>{direction(r.from, r.to)}</StatusChip>
                  </td>
                  <td data-label="Cases">
                    <CaseCount n={r.n} cases={r.cases} admin={admin} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function StopsPanel({ rows, admin }) {
  return (
    <section className="ins-panel" aria-labelledby="ins-stops">
      <h2 id="ins-stops">Why runs stopped</h2>
      {rows.length === 0 ? (
        <p className="muted">No run stopped in this period.</p>
      ) : (
        <div className="card ins-wrap">
          <table className="ins-table">
            <thead>
              <tr>
                <th scope="col">Stage</th>
                <th scope="col">Rule</th>
                <th scope="col">What it checks</th>
                <th scope="col">Cases</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.stage}-${r.rule_id}`}>
                  <td data-label="Stage">{r.stage_label}</td>
                  <td data-label="Rule">
                    <span className="mono ref-id">{r.rule_id}</span>
                  </td>
                  <td data-label="What it checks">
                    <div>
                      {r.clause_title && <span className="ins-title">{r.clause_title}</span>}
                      <Clause row={r} admin={admin} />
                    </div>
                  </td>
                  <td data-label="Cases">
                    <CaseCount n={r.n} cases={r.cases} admin={admin} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function PrecedentPanel({ p, admin }) {
  return (
    <section className="ins-panel" aria-labelledby="ins-prec">
      <h2 id="ins-prec">Precedents</h2>
      <p>
        {p.reached === 0
          ? "No approved precedent's bonus reached a case in this period."
          : `A precedent's bonus reached ${p.reached} case${p.reached === 1 ? '' : 's'}; it moved ${p.moved} of them to another band.`}
      </p>
      {admin && p.moved > 0 && (
        <CaseCount
          n={p.moved}
          cases={p.moved_cases}
          admin={admin}
          label={p.moved === 1 ? 'Show the case it moved' : `Show the ${p.moved} cases it moved`}
        />
      )}
    </section>
  )
}

/** Insights for the admin (full, with links) or the auditor (counts only). No AI on this page. */
export default function InsightsPage({ audience = 'admin' }) {
  const admin = audience === 'admin'
  const [draft, setDraft] = useState(NO_FILTERS)
  const backwards = draft.from && draft.to && draft.to < draft.from
  const [filters, setFilters] = useState(NO_FILTERS)
  const qs = query(filters)
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/${audience}/insights${qs}`),
    [audience, qs],
  )

  const change = (key) => (e) => {
    const next = { ...draft, [key]: e.target.value }
    setDraft(next)
    if (!(next.from && next.to && next.to < next.from)) setFilters(next)
  }
  const clear = () => {
    setDraft(NO_FILTERS)
    setFilters(NO_FILTERS)
  }
  const empty = data && data.funnel.created === 0

  return (
    <div className="insights">
      <header className="page-head">
        <div>
          <h1>Insights</h1>
          <p className="muted">Counted from the case records. No AI is used on this page.</p>
          {!admin && <p className="small muted">Counts only. Cases cannot be opened from here.</p>}
        </div>
      </header>

      <form className="card ins-filters" onSubmit={(e) => e.preventDefault()} aria-label="Filters">
        <div className="field">
          <label htmlFor="ins-from">From</label>
          <input
            id="ins-from"
            type="date"
            className="input"
            value={draft.from}
            onChange={change('from')}
          />
        </div>
        <div className="field">
          <label htmlFor="ins-to">To</label>
          <input
            id="ins-to"
            type="date"
            className="input"
            value={draft.to}
            onChange={change('to')}
            aria-invalid={backwards ? 'true' : undefined}
            aria-describedby={backwards ? 'ins-to-error' : undefined}
          />
        </div>
        <div className="field">
          <label htmlFor="ins-loan">Loan type</label>
          <select id="ins-loan" className="select" value={draft.loan} onChange={change('loan')}>
            <option value="">All loan types</option>
            {LOAN_TYPES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn btn-ghost" onClick={clear}>
          Clear filters
        </button>
        {backwards && (
          <p id="ins-to-error" className="field-error ins-filter-error" role="alert">
            The end date is before the start date.
          </p>
        )}
      </form>
      <p className="small muted">{showing(filters)}</p>

      {loading && !data && <SectionLoader label="Counting the cases" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {empty && (
        <EmptyState title="No cases in this period">
          Try a longer period or another loan type.
        </EmptyState>
      )}
      {data && !empty && (
        <div className={`ins-body${loading ? ' ins-stale' : ''}`} aria-busy={loading}>
          <TimePanel t={data.time_to_decide} />
          <FunnelPanel f={data.funnel} />
          <AgreementPanel a={data.agreement} />
          <RulesPanel rows={data.changed_rules} admin={admin} />
          <StopsPanel rows={data.stop_reasons} admin={admin} />
          <PrecedentPanel p={data.precedents} admin={admin} />
        </div>
      )}
    </div>
  )
}
