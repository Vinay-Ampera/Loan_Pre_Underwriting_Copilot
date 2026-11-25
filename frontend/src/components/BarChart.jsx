import './BarChart.css'

/** Horizontal bars drawn from counts. `rows` is [{ label, value, tone?, note?, display? }]; a row
 *  with a `note` shows that text instead of a bar (for example "too few to show"). tone is a token
 *  name (approve, refer, reject, stopped) and defaults to the brand colour. The numbers are shown
 *  as text (`display` when the value needs words, such as "13.5 hours" or "82%"), so the chart
 *  reads without colour, and each row repeats them as its hover title. `max` fixes the scale (100
 *  for shares); otherwise the longest bar is the largest value. `valueWidth` widens the number
 *  column for longer texts. `foot` is an optional line under the bars. */
export default function BarChart({
  title,
  rows,
  empty = 'Nothing to show yet.',
  foot,
  max,
  valueWidth,
}) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value))
  const total = rows.reduce((n, r) => n + (r.note ? 0 : r.value), 0)
  const style = valueWidth ? { '--bar-value-w': valueWidth } : undefined
  return (
    <figure className="bar-chart card" style={style}>
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
              <li key={r.label} title={`${r.label}: ${r.display ?? r.value}`}>
                <span className="bar-label">{r.label}</span>
                <span className="bar-track" aria-hidden="true">
                  <span
                    className={`bar-fill${r.tone ? ` bar-${r.tone}` : ''}`}
                    style={{ width: `${Math.min(100, (r.value / top) * 100)}%` }}
                  />
                </span>
                <span className="bar-value">{r.display ?? r.value}</span>
              </li>
            ),
          )}
        </ul>
      )}
      {foot && <p className="bar-foot muted small">{foot}</p>}
    </figure>
  )
}
