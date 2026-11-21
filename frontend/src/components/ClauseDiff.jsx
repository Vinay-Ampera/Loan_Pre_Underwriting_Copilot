import './ClauseDiff.css'

function Words({ words }) {
  return (
    <p className="cd-words">
      {words.map((w, i) =>
        w.k === 'same' ? (
          <span key={i}>{w.t} </span>
        ) : w.k === 'add' ? (
          <ins key={i}>
            <span className="sr-only">added: </span>
            {w.t}{' '}
          </ins>
        ) : (
          <del key={i}>
            <span className="sr-only">removed: </span>
            {w.t}{' '}
          </del>
        ),
      )}
    </p>
  )
}

/** What changes between two versions of one policy, clause by clause and word by word. */
export default function ClauseDiff({ changes, title = 'What changes' }) {
  if (!changes) return null
  const { added, removed, changed, unchanged, meta, details } = changes
  const nothing = !added.length && !removed.length && !changed.length
  return (
    <section className="clause-diff card" aria-label={title}>
      <h4>{title}</h4>
      <p className="small muted">
        {changes.from ? `From ${changes.from} to ${changes.to}: ` : ''}
        {changed.length} changed, {added.length} added, {removed.length} removed, {unchanged}{' '}
        unchanged.
      </p>
      {Object.entries(meta || {}).map(([k, v]) => (
        <p key={k} className="small">
          {k.replace('_', ' ')}: <del>{v.before}</del> <ins>{v.after}</ins>
        </p>
      ))}
      {nothing && <p className="muted">No clause changes.</p>}
      {details.changed.map((c) => (
        <div key={c.clause_id} className="cd-item cd-changed">
          <p className="cd-head">
            <span className="mono">{c.clause_id}</span> changed
            {c.title_before !== c.title_after && (
              <>
                {' '}
                · title <del>{c.title_before}</del> <ins>{c.title_after}</ins>
              </>
            )}
            {c.source_before !== c.source_after && (
              <>
                {' '}
                · source <del>{c.source_before}</del> <ins>{c.source_after}</ins>
              </>
            )}
          </p>
          <Words words={c.words} />
        </div>
      ))}
      {details.added.map((c) => (
        <div key={c.clause_id} className="cd-item cd-added">
          <p className="cd-head">
            <span className="mono">{c.clause_id}</span> added · {c.title} ({c.source_tag})
          </p>
          <p>{c.text}</p>
        </div>
      ))}
      {details.removed.map((c) => (
        <div key={c.clause_id} className="cd-item cd-removed">
          <p className="cd-head">
            <span className="mono">{c.clause_id}</span> removed · {c.title}
          </p>
          <p className="muted">{c.text}</p>
        </div>
      ))}
    </section>
  )
}
