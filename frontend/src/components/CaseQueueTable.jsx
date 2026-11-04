import { Link } from 'react-router-dom'
import { CaseStatusChip } from './StatusChip'
import { loanLabel } from './LoanTypePicker'
import './CaseQueueTable.css'

const money = (n) =>
  n == null
    ? '–'
    : new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 0,
      }).format(n)

export default function CaseQueueTable({ cases }) {
  return (
    <div className="queue-wrap card">
      <table className="queue">
        <thead>
          <tr>
            <th>Case no</th>
            <th>Applicant</th>
            <th>Loan</th>
            <th>Status</th>
            <th className="num">Score</th>
            <th className="num">Age</th>
            <th>Officer</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id}>
              <td data-label="Case no">
                <Link to={`/cases/${c.id}`} className="mono">
                  {c.case_no}
                </Link>
                {c.origin === 'applicant' && (
                  <span className="from-applicant" title="Sent in through an upload link">
                    From applicant
                  </span>
                )}
              </td>
              <td data-label="Applicant">
                {c.applicant || <span className="muted">Details not entered yet</span>}
              </td>
              <td data-label="Loan">
                {loanLabel(c.loan_type)} <span className="muted">{money(c.loan_amount)}</span>
              </td>
              <td data-label="Status">
                <CaseStatusChip status={c.status} band={c.band} />
              </td>
              <td data-label="Score" className="num">
                {c.total_score == null ? <span className="muted">–</span> : c.total_score}
              </td>
              <td data-label="Age" className="num">
                {c.age_days === 0 ? 'today' : `${c.age_days} d`}
              </td>
              <td data-label="Officer">{c.officer}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
