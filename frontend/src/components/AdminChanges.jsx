import './AdminCorrection.css'

const WORD = { approve: 'approve', refer: 'refer', reject: 'reject' }

/**
 * What an admin changed after the officer decided: who, when, from what to what, and why. The
 * officer's own decision stays on the case beneath it. Shown to the officer and to the admin.
 */
export default function AdminChanges({ actions }) {
  if (!actions?.length) return null
  const latest = actions.length - 1
  return (
    <div className="admin-changes">
      {actions.map((a, i) => (
        <div
          key={`${a.at}-${i}`}
          className={`card admin-change${i === latest ? ' is-latest' : ''}`}
        >
          <h3>{i === latest ? 'Changed by an admin' : 'Earlier admin change'}</h3>
          <p>
            {a.admin} changed the decision from <strong>{WORD[a.previous_decision]}</strong> to{' '}
            <strong>{WORD[a.final_decision]}</strong> on {new Date(a.at).toLocaleString()}.
          </p>
          <p className="muted">Reason: {a.reason}</p>
        </div>
      ))}
    </div>
  )
}
