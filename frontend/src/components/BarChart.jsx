import './BarChart.css'

/** Horizontal bars drawn from counts. `rows` is [{ label, value, tone?, note? }]; a row with a
 *  `note` shows that text instead of a bar (for example "too few to show"). tone is a token name
 *  (approve, refer, reject, stopped) and defaults to the brand colour. The numbers are shown as
 *  text, so the chart reads without colour. */
export default function BarChart({ title, rows, empty = 'Nothing to show yet.' }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  const total = rows.reduce((n, r) => n + (r.note ? 0 : r.value), 0)
  return (
    <figure className="bar-chart card">
      <figcaption>{title}</figcaption>
      {total === 0 && !rows.some((r) => r.note) ? (
        <p className="muted small">{empty}</p>
      ) : (
        <ul>
          {rows.map((r) =>
            r.note ? (
              <li key={r.label} className="bar-note">
                <span className="bar-label">{r.label}</span>
                <span className="muted small">{r.note}</span>
              </li>
            ) : (
              <li key={r.label}>
                <span className="bar-label">{r.label}</span>
                <span className="bar-track" aria-hidden="true">
                  <span
                    className={`bar-fill${r.tone ? ` bar-${r.tone}` : ''}`}
                    style={{ width: `${(r.value / max) * 100}%` }}
                  />
                </span>
                <span className="bar-value">{r.value}</span>
              </li>
            ),
          )}
        </ul>
      )}
    </figure>
  )
}
