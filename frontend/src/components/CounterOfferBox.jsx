import Icon from './Icons'
import './CounterOfferBox.css'

// Wording: docs/DESIGN_SYSTEM.md 17.1. The sentences themselves come from the backend
// (app/scoring/counter_offer.py) so the screen and the PDF say the same thing.
const TITLE = 'Other amounts or tenures (estimate)'
const INTRO =
  "Worked out in code from this case's checked figures. For you to discuss with the applicant; it does not change the score or the recommendation."
const FOOTER =
  "Rate from the bank's rules file. Your decision is still needed. Not for customer messages."
const PRODUCT_ICON = { vehicle: 'car', education: 'cap', business: 'briefcase', home: 'home' }

function iconFor(line) {
  if (line.kind === 'tenure' || line.kind === 'age_tenure') return 'clock'
  if (line.kind === 'amount') return 'wallet'
  return PRODUCT_ICON[line.loan_type] || 'info'
}

/** Other amounts or tenures worked out in code (Stage 12 Part A). No box, no card. */
export default function CounterOfferBox({ box }) {
  if (!box?.lines?.length) return null
  return (
    <section className="card report-block offer" aria-label={TITLE}>
      <h3>{TITLE}</h3>
      <p className="small muted">{INTRO}</p>
      <ul className="offer-lines">
        {box.lines.map((line, i) => (
          <li key={`${line.kind}-${i}`} className="offer-line">
            <Icon name={iconFor(line)} className="offer-icon" />
            <span>{line.text}</span>
            {line.tags?.length > 0 && (
              <span className="offer-tags">
                {line.tags.map((t) => (
                  <code key={t} className="offer-tag">
                    {t}
                  </code>
                ))}
              </span>
            )}
          </li>
        ))}
      </ul>
      <p className="small muted">{FOOTER}</p>
    </section>
  )
}
