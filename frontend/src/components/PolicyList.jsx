import StatusChip from './StatusChip'
import { day, policyLabel } from '../lib/policy'
import './PolicyList.css'

/** The six policies (common plus one per loan type) with their version and any pending change. */
export default function PolicyList({ policies, selected, onSelect }) {
  return (
    <nav className="policy-list" aria-label="Policies">
      {policies.map((p) => (
        <button
          key={p.loan_type}
          type="button"
          className={`pl-item${selected === p.loan_type ? ' on' : ''}`}
          aria-current={selected === p.loan_type ? 'true' : undefined}
          onClick={() => onSelect(p.loan_type)}
        >
          <span className="pl-name">{policyLabel(p.loan_type)}</span>
          <span className="small muted">
            {p.active ? (
              <>
                <span className="mono">{p.active.version}</span> · {p.active.clauses} clauses
              </>
            ) : (
              'No version in force'
            )}
          </span>
          {(p.draft || p.scheduled || p.active?.missing_embeddings > 0) && (
            <span className="pl-flags">
              {p.draft && <StatusChip tone="neutral">Draft</StatusChip>}
              {p.scheduled && (
                <StatusChip tone="info">From {day(p.scheduled.effective_from)}</StatusChip>
              )}
              {p.active?.missing_embeddings > 0 && (
                <StatusChip tone="refer">Not fully indexed</StatusChip>
              )}
            </span>
          )}
        </button>
      ))}
    </nav>
  )
}
