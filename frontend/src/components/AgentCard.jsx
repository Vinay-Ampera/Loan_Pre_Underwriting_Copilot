import './AgentCard.css'

/** One agent in plain words: what it does, which score points it feeds, and a "more" fold. */
export default function AgentCard({ name, points, does, more }) {
  return (
    <article className="agent-card card">
      <header>
        <h3>{name}</h3>
        <span className="agent-points">{points}</span>
      </header>
      <p>{does}</p>
      {more && (
        <details>
          <summary>More</summary>
          <p className="muted">{more}</p>
        </details>
      )}
    </article>
  )
}
