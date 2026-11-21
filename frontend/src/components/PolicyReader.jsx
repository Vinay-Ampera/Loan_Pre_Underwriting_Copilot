import StatusChip from './StatusChip'
import { day, originLabel, ruleText, versionTone, when } from '../lib/policy'
import './PolicyReader.css'

/**
 * One policy version, clause by clause, with the rules from the rules file that point at each
 * clause. `admin` adds who published it, why, and how often each clause was cited lately.
 */
export default function PolicyReader({ version, admin = false }) {
  if (!version) return null
  const [tone, label] = versionTone(version.status)
  return (
    <article className="policy-reader" aria-label={`${version.title}, version ${version.version}`}>
      <header className="pr-head">
        <div>
          <h3>{version.title}</h3>
          <p className="small muted">
            Version <span className="mono">{version.version}</span> · effective{' '}
            {day(version.effective_from)} · {version.clauses} clauses
          </p>
        </div>
        <StatusChip tone={tone}>{label}</StatusChip>
      </header>
      {admin && (
        <p className="small muted">
          {originLabel(version.origin)}
          {version.published_by ? ` · published by ${version.published_by}` : ''}
          {version.published_at ? ` on ${when(version.published_at)}` : ''}
          {version.reason ? ` · "${version.reason}"` : ''}
          {version.retired_reason ? ` · retired: "${version.retired_reason}"` : ''}
        </p>
      )}
      {version.intro && <p className="pr-intro">{version.intro}</p>}
      <ol className="pr-clauses">
        {version.clause_list.map((c) => (
          <li key={c.clause_id} className="pr-clause" id={`clause-${c.clause_id}`}>
            <div className="pr-clause-head">
              <span className="mono ref-id">{c.clause_id}</span>
              <strong>{c.title}</strong>
              <span className="pr-source small">{c.source_tag}</span>
            </div>
            <p>{c.text}</p>
            {c.rules.length > 0 && (
              <ul className="pr-rules small" aria-label={`Rules that use ${c.clause_id}`}>
                {c.rules.map((r) => (
                  <li key={r.rule_id}>
                    <span className="mono">{r.rule_id}</span> {ruleText(r)}
                  </li>
                ))}
              </ul>
            )}
            {admin && c.cited_30d > 0 && (
              <p className="small muted">
                Cited in {c.cited_30d} case{c.cited_30d === 1 ? '' : 's'} in the last 30 days.
              </p>
            )}
          </li>
        ))}
      </ol>
    </article>
  )
}
