import { collateralNote, threeC } from '../lib/conditions'
import './CreditStrip.css'

/** Credit / Capacity / Collateral: a display-only regrouping of the existing stage scores. */
export default function CreditStrip({ report, loanType }) {
  const c = threeC(report)
  const collateral = collateralNote(loanType)
  const cells = [
    ['Credit', c.credit, 'From: Credit and behaviour'],
    ['Capacity', c.capacity, 'From: Income and FOIR'],
    ['Collateral', c.collateral, collateral.note],
  ]
  return (
    <section className="credit-strip card" aria-label="Credit, Capacity and Collateral">
      {cells.map(([name, v, from]) => (
        <div key={name} className="c-cell">
          <h3>{name}</h3>
          {name === 'Collateral' ? (
            <p className="c-value muted">{collateral.value}</p>
          ) : v ? (
            <p className="c-value">
              {Number(v.score)} <span className="muted">/ {Number(v.max)}</span>
            </p>
          ) : (
            <p className="c-value muted">Stage not run</p>
          )}
          <p className="small muted">{from}</p>
        </div>
      ))}
    </section>
  )
}
