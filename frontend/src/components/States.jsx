import './States.css'

export function EmptyState({ title, children, action }) {
  return (
    <div className="state card">
      <h3>{title}</h3>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="state card state-error" role="alert">
      <h3>Something went wrong</h3>
      <p>{error?.message || 'Unknown error.'}</p>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

/** `delayed` keeps it invisible for the first moments, so a quick tab switch shows no flash. */
export function Skeleton({ lines = 3, height = 16, delayed = false }) {
  return (
    <div
      className={`skeleton-block${delayed ? ' skeleton-delayed' : ''}`}
      aria-busy="true"
      aria-label="Loading"
    >
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ height, width: `${100 - (i % 3) * 14}%` }} />
      ))}
    </div>
  )
}
