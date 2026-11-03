import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import { CaseStatusChip } from '../components/StatusChip'
import { ErrorState, Skeleton } from '../components/States'
import './AdminOfficerPage.css'

const STATUS = [
  ['draft', 'Draft'],
  ['uploaded', 'Uploaded'],
  ['running', 'Assessing'],
  ['stopped', 'Stopped'],
  ['awaiting_confirmation', 'Awaiting confirmation'],
  ['confirmed', 'Confirmed'],
  ['overridden', 'Overridden'],
]
const BAND = [
  ['approve', 'Recommended approve'],
  ['refer', 'Refer'],
  ['reject', 'Recommended reject'],
]
const PRECEDENT = ['pending', 'approved', 'rejected', 'held', 'expired']
const when = (v) => (v ? new Date(v).toLocaleString() : 'Never')

function Counts({ title, rows }) {
  return (
    <section className="card officer-block">
      <h2>{title}</h2>
      <ul className="officer-counts">
        {rows.map(([label, n]) => (
          <li key={label}>
            <span className="officer-n">{n}</span> <span className="muted">{label}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Officer profile for the admin: counts and case numbers only, no applicant data. */
export default function AdminOfficerPage() {
  const { id } = useParams()
  const { data, error, loading, reload } = useAsync(
    () => api.get(`/admin/users/${id}/activity`),
    [id],
  )
  return (
    <div className="officer-page">
      <Link to="/admin/users">← Users</Link>
      {loading && <Skeleton lines={4} height={48} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <>
          <header>
            <h1>{data.user.name}</h1>
            <p className="muted">
              {data.user.email} · {data.user.role} · {data.user.active ? 'Active' : 'Disabled'} ·
              Last sign-in: {when(data.last_login)}
            </p>
          </header>
          <div className="officer-grid">
            <Counts
              title={`Cases (${data.cases_total})`}
              rows={STATUS.map(([k, l]) => [l, data.cases_by_status[k] ?? 0])}
            />
            <Counts
              title="Recommendations"
              rows={BAND.map(([k, l]) => [l, data.cases_by_band[k] ?? 0])}
            />
            <Counts
              title="Officer decisions"
              rows={[
                ['Confirmed', data.confirmed],
                ['Overridden', data.overridden],
              ]}
            />
            <Counts
              title="Precedents proposed"
              rows={PRECEDENT.map((k) => [k, data.precedents_by_status[k] ?? 0])}
            />
          </div>
          <section className="card officer-block">
            <h2>Recent cases</h2>
            {data.recent_cases.length === 0 ? (
              <p className="muted">No cases yet.</p>
            ) : (
              <table className="officer-cases">
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Loan type</th>
                    <th>Status</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_cases.map((c) => (
                    <tr key={c.case_no}>
                      <td data-label="Case">{c.case_no}</td>
                      <td data-label="Loan type">{c.loan_type}</td>
                      <td data-label="Status">
                        <CaseStatusChip status={c.status} band={c.band} />
                      </td>
                      <td data-label="Updated">{when(c.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="small muted">
              Admins see counts and case numbers only. Applicant details stay with the officer.
            </p>
          </section>
        </>
      )}
    </div>
  )
}
