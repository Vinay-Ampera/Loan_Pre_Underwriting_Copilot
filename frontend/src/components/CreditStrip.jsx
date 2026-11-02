import { threeC } from '../lib/conditions'
import './CreditStrip.css'

/** Credit / Capacity / Collateral: a display-only regrouping of the existing stage scores. */
export default function CreditStrip({ report }) {
  const c = threeC(report)
  const cells = [
    ['Credit', c.credit, 'Credit and behaviour'],
    ['Capacity', c.capacity, 'Income and FOIR'],
    ['Collateral', c.collateral, null],
  ]
  return (
    <section className="credit-strip card" aria-label="Credit, Capacity and Collateral">
      {cells.map(([name, v, from]) => (
        <div key={name} className="c-cell">
          <h3>{name}</h3>
          {name === 'Collateral' ? (
            <p className="c-value muted">Not scored in v1</p>
          ) : v ? (
            <p className="c-value">
              {Number(v.score)} <span className="muted">/ {Number(v.max)}</span>
            </p>
          ) : (
            <p className="c-value muted">Stage not run</p>
          )}
          <p className="small muted">{from ? `From: ${from}` : 'No points in the score'}</p>
        </div>
      ))}
    </section>
  )
}
