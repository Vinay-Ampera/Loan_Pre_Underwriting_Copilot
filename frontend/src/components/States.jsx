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

export function Skeleton({ lines = 3, height = 16 }) {
  return (
    <div className="skeleton-block" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ height, width: `${100 - (i % 3) * 14}%` }} />
      ))}
    </div>
  )
}
