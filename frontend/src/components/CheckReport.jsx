import Icon from './Icons'
import './CheckReport.css'

function Issue({ i }) {
  return (
    <li>
      {i.line ? <span className="mono small cr-line">line {i.line}</span> : null}
      {i.clause_id && !i.line ? <span className="mono small cr-line">{i.clause_id}</span> : null}
      <span>{i.message}</span>
    </li>
  )
}

/**
 * The format check of a draft: errors block publishing, warnings need a tick, and the fixes
 * auto-fix would make (formatting only, never the words or numbers) can be applied in one go.
 */
export default function CheckReport({ check, onApplyFixes, busy = false }) {
  if (!check) return null
  const { errors, warnings, fixes, summary } = check
  return (
    <section className="check-report card" aria-label="Format check">
      <h4>
        <Icon name={errors.length ? 'alert' : 'shield-check'} />
        {errors.length
          ? `${errors.length} error${errors.length === 1 ? '' : 's'} to fix before publishing`
          : 'The format check passed'}
      </h4>
      {summary && (
        <p className="small muted">
          Version <span className="mono">{summary.version}</span> · {summary.clauses} clauses ·{' '}
          {summary.takes_effect === 'scheduled'
            ? `scheduled for ${summary.effective_from}`
            : 'takes effect when published'}
        </p>
      )}
      {errors.length > 0 && (
        <ul className="cr-list cr-errors" aria-label="Errors">
          {errors.map((i, n) => (
            <Issue key={n} i={i} />
          ))}
        </ul>
      )}
      {warnings.length > 0 && (
        <>
          <h5>
            {warnings.length} warning{warnings.length === 1 ? '' : 's'} (you tick these when you
            publish)
          </h5>
          <ul className="cr-list cr-warnings" aria-label="Warnings">
            {warnings.map((i, n) => (
              <Issue key={n} i={i} />
            ))}
          </ul>
        </>
      )}
      {fixes.length > 0 && onApplyFixes && (
        <div className="cr-fixes">
          <h5>Auto-fix can correct the formatting</h5>
          <ul className="cr-list" aria-label="Fixes">
            {fixes.map((f, n) => (
              <li key={n}>
                {f.line ? <span className="mono small cr-line">line {f.line}</span> : null}
                <span>
                  {f.why}
                  {f.before && f.after && (
                    <span className="mono small cr-change">
                      <del>{f.before}</del> → <ins>{f.after}</ins>
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
          <button type="button" className="btn" disabled={busy} onClick={onApplyFixes}>
            Apply these fixes to the draft
          </button>
          <p className="small muted">Fixes change formatting only, never a clause&apos;s words.</p>
        </div>
      )}
    </section>
  )
}
