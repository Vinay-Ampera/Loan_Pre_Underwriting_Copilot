import StatusChip from './StatusChip'
import './ApplicantRequest.css'

const money = (n) =>
  n == null
    ? '–'
    : new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 0,
      }).format(n)
const EMP = { salaried: 'Salaried', self_employed: 'Self-employed' }

/**
 * What the applicant stated through their upload link. It is a claim like everything typed in
 * the form: shown as theirs, not checked, and correctable by the officer (every correction is
 * audited) until the applicant's request is locked.
 */
export default function ApplicantRequest({ c }) {
  const r = c.request
  const sent = c.applicant_sent
  return (
    <section className="card applicant-request" aria-label="From the applicant">
      <header className="ar-head">
        <h3>From the applicant</h3>
        {sent ? (
          <StatusChip tone={sent.incomplete ? 'refer' : 'approve'}>
            {sent.incomplete ? 'Sent, incomplete' : 'Sent, complete'}
          </StatusChip>
        ) : (
          <StatusChip tone="neutral">Applicant is still preparing</StatusChip>
        )}
      </header>
      <p className="muted">
        This is the applicant&apos;s own statement. It has not been checked.{' '}
        {c.request_locked
          ? 'You have taken over the form, so the applicant can no longer change the request.'
          : 'The applicant can change it until you save the application form.'}
      </p>
      {r ? (
        <dl className="ar-grid">
          <div>
            <dt>Loan amount</dt>
            <dd>{money(r.loan_amount)}</dd>
          </div>
          <div>
            <dt>Tenure</dt>
            <dd>{r.tenure_months} months</dd>
          </div>
          <div>
            <dt>Purpose</dt>
            <dd>{r.purpose || '–'}</dd>
          </div>
          <div>
            <dt>Employment ({r.earner_role === 'co' ? 'co-applicant' : 'applicant'})</dt>
            <dd>{EMP[r.employment_type] || '–'}</dd>
          </div>
          <div>
            <dt>Declared monthly income</dt>
            <dd>{money(r.declared_monthly_income)}</dd>
          </div>
          {sent?.reference && (
            <div>
              <dt>Reference the applicant was given</dt>
              <dd className="mono">{sent.reference}</dd>
            </div>
          )}
        </dl>
      ) : (
        <p className="muted">No request has been sent yet.</p>
      )}
    </section>
  )
}
