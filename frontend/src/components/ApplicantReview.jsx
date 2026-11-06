import { useState } from 'react'
import AskApplicantDialog from './AskApplicantDialog'
import Inventory from './Inventory'
import StatusChip from './StatusChip'
import './ApplicantReview.css'

/**
 * The first screen for a case an applicant sent in through a link: what they sent, what is
 * still missing, and one decision about the submission itself. The applicant's request is shown
 * above this screen as a claim. Nothing here is a credit decision: "Accept and continue" only
 * moves the officer on to the form (which then takes the request over), and "Ask for more" shares
 * the same upload link again.
 */
export default function ApplicantReview({
  c,
  inventory,
  docTypes,
  recipient,
  onView,
  onAccept,
  onChanged,
}) {
  const [ask, setAsk] = useState(false)
  const sent = c.applicant_sent
  const counts = inventory?.counts
  const live = c.documents.filter((d) => d.status === 'accepted')
  const missing = counts ? counts.missing + inventory.depends_on_employment.length : 0
  const attention = counts ? counts.unassigned + counts.unrecognised : 0

  return (
    <section className="card review-card" aria-label="Review the applicant's submission">
      <header className="review-head">
        <div>
          <h2>Review what the applicant sent</h2>
          <p className="muted">
            Sent {sent?.at}
            {sent?.reference && (
              <>
                {' '}
                · reference <span className="mono">{sent.reference}</span>
              </>
            )}
          </p>
        </div>
        <StatusChip tone={sent?.incomplete || missing > 0 ? 'refer' : 'approve'}>
          {sent?.incomplete || missing > 0 ? 'Incomplete' : 'Everything on the list is in'}
        </StatusChip>
      </header>

      <ul className="review-counts" aria-label="Summary">
        <li>
          <strong>{live.length}</strong> received
        </li>
        <li>
          <strong>{missing}</strong> still missing
        </li>
        <li>
          <strong>{attention}</strong> need your attention
        </li>
      </ul>

      {live.length > 0 && (
        <ul className="review-files" aria-label="Files received">
          {live.map((d) => (
            <li key={d.id}>
              <span>
                <strong>{d.name}</strong>{' '}
                <span className="muted">
                  {d.role === 'co'
                    ? 'co-applicant'
                    : d.role === 'primary'
                      ? 'applicant'
                      : 'no person yet'}{' '}
                  · {d.doc_type.replaceAll('_', ' ')}
                </span>
              </span>
              <button type="button" className="btn" onClick={() => onView(d.id)}>
                View<span className="sr-only"> {d.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {inventory && (
        <Inventory
          caseId={c.id}
          inventory={inventory}
          docTypes={docTypes}
          editable={false}
          onChange={() => {}}
          onError={() => {}}
        />
      )}

      <div className="review-actions">
        <button type="button" className="btn" onClick={() => setAsk(true)}>
          Ask for more
        </button>
        <button type="button" className="btn btn-primary" onClick={onAccept}>
          Accept and continue
        </button>
      </div>
      <p className="small muted">
        Accepting does not decide anything about the loan. It opens the intake desk or the form,
        where you correct the request and file the documents. The applicant can no longer change the
        request once you save the form.
      </p>
      {ask && (
        <AskApplicantDialog
          caseId={c.id}
          recipient={recipient}
          onClose={() => setAsk(false)}
          onDone={onChanged}
        />
      )}
    </section>
  )
}
