import ScoreBadge from './ScoreBadge'
import { topReasons } from '../lib/glance'
import { conditionsFrom } from '../lib/conditions'
import './AtAGlance.css'

const SEVERITY = { hard_fail: 'Hard fail', cap: 'Caps the band', points_lost: 'Points lost' }

/** A short read of the report: outcome, score, the top reasons and what to do next. */
export default function AtAGlance({ report }) {
  const reasons = topReasons(report)
  const missing = conditionsFrom(report).length
  const next =
    report.status === 'stopped'
      ? report.stop_text
      : missing > 0
        ? `Obtain or fix ${missing} item${missing === 1 ? '' : 's'} listed under Conditions, then review and confirm.`
        : 'Review the findings and confirm or override the recommendation.'
  return (
    <section className="card glance" aria-label="At a glance">
      <ScoreBadge
        score={report.total_score}
        band={report.band}
        indicative={report.indicative_score}
      />
      <div className="glance-body">
        <h3>At a glance</h3>
        {reasons.length > 0 ? (
          <ol className="glance-reasons">
            {reasons.map((f, i) => (
              <li key={i}>
                <span className="glance-sev small">{SEVERITY[f.severity]}</span> {f.message}{' '}
                <code>{f.rule_id}</code>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">No findings cost points.</p>
        )}
        <p className="glance-next">
          <strong>Next:</strong> {next}
        </p>
      </div>
    </section>
  )
}
