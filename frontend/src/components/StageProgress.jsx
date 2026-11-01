import './StageProgress.css'

const STEPS = [
  { id: 'extraction', label: 'Reading documents' },
  { id: 'kyc', label: 'KYC checks' },
  { id: 'policy_risk', label: 'Policy and risk', needs: ['policy', 'risk'] },
  { id: 'decision', label: 'Writing the report' },
]

/** Progress by stage, not a spinner alone (DESIGN_SYSTEM section 6). */
export default function StageProgress({ stages }) {
  const done = new Set(stages.map((s) => s.stage))
  let active = null
  const rows = STEPS.map((s) => {
    const complete = (s.needs || [s.id]).every((n) => done.has(n))
    if (!complete && active === null) active = s.id
    return { ...s, complete }
  })
  return (
    <ol className="progress" aria-label="Assessment progress">
      {rows.map((s) => (
        <li key={s.id} className={s.complete ? 'done' : s.id === active ? 'active' : ''}>
          <span className="pg-mark" aria-hidden="true">
            {s.complete ? '✓' : s.id === active ? '⟳' : '○'}
          </span>
          {s.label}
          <span className="sr-only">
            {s.complete ? ' done' : s.id === active ? ' in progress' : ' waiting'}
          </span>
        </li>
      ))}
    </ol>
  )
}
