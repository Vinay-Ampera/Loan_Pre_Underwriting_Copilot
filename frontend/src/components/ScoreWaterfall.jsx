import { useState } from 'react'
import './ScoreWaterfall.css'

// layout only (viewBox units): every number shown comes from the report
// narrow enough for the case pane at 1024 wide, so the band labels are never cut off
const WIDTH = 600
const PLOT_W = 526 // the band-line labels sit to the right of this
const TOP = 44 // room for the cap tag and the value above the tallest bar
const PLOT_H = 200
const HEIGHT = TOP + PLOT_H + 40
const BAR = 34

const word = (band) => band.charAt(0).toUpperCase() + band.slice(1)

const longest = (lines) => Math.max(...lines.map((l) => l.length))

/** A stage name on at most two lines under its bar. */
function twoLines(label) {
  const words = label.split(' ')
  if (label.length <= 10 || words.length === 1) return [label]
  // break where the longer line is shortest: columns are narrow
  return words
    .slice(1)
    .map((_, i) => [words.slice(0, i + 1).join(' '), words.slice(i + 1).join(' ')])
    .reduce((best, next) => (longest(next) < longest(best) ? next : best))
}

/** One bar per step: where it starts and ends on the score scale, and what it says. */
function steps(data) {
  const list = [
    { key: 'start', kind: 'total', from: 0, to: data.start, value: `${data.start}`, name: 'Start' },
  ]
  let level = data.start
  for (const s of data.stages) {
    list.push({
      key: s.stage,
      kind: 'lost',
      from: s.level_after,
      to: level,
      value: `−${s.lost}`,
      name: s.label,
      title: `${s.label}: lost ${s.lost}, earned ${s.earned} of ${s.max}`,
    })
    level = s.level_after
  }
  if (data.bonus > 0) {
    list.push({
      key: 'bonus',
      kind: 'bonus',
      from: level,
      to: data.final,
      value: `+${data.bonus}`,
      name: 'Precedent',
      title: `Precedent bonus: ${data.bonus} points added`,
    })
  }
  list.push({
    key: 'final',
    kind: 'total',
    from: 0,
    to: data.final,
    value: `${data.final}`,
    name: `Score ${data.final}`,
    second: word(data.band),
    title: `Final score ${data.final}, ${data.band}`,
  })
  return list
}

function sentence(data, capped) {
  const lost = data.stages.map((s) => `${s.label} lost ${s.lost}`).join(', ')
  const bonus = data.bonus > 0 ? `; a precedent bonus added ${data.bonus}` : ''
  const cap = capped ? `; capped at refer by ${data.cap_rule_ids.join(', ')}` : ''
  return `Score breakdown: starts at ${data.start}; ${lost}${bonus}; final score ${data.final}, ${data.band}${cap}.`
}

/**
 * How the score was reached (Stage 12 Part D): a waterfall from the start down to the final score.
 * The server sends every number; this only draws them. No chart for a stopped case.
 */
export default function ScoreWaterfall({ data }) {
  const [asTable, setAsTable] = useState(false)
  if (!data) return null
  const capped = data.cap_rule_ids.length > 0 && data.band === 'refer'
  const aboveLine = capped && data.final >= data.approve_min
  const bars = steps(data)
  const slot = PLOT_W / bars.length
  const y = (score) => TOP + PLOT_H * (1 - score / data.start)
  const lines = [
    [data.approve_min, ['recommend', 'approve']],
    [data.refer_min, ['refer']],
  ]

  return (
    <section className="card report-block waterfall" aria-labelledby="waterfall-h">
      <div className="waterfall-head">
        <div>
          <h3 id="waterfall-h">How the score was reached</h3>
          <p className="muted">Starts at {data.start}. Each step is the points lost in a stage.</p>
        </div>
        {/* the label names the other view */}
        <button type="button" className="btn btn-ghost" onClick={() => setAsTable((v) => !v)}>
          {asTable ? 'Show as a graph' : 'Show as a table'}
        </button>
      </div>

      {!asTable && (
        <div className="waterfall-scroll" tabIndex={0}>
          <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={sentence(data, capped)}>
            {lines.map(([at, words]) => (
              <g key={at}>
                <line className="wf-band" x1="0" x2={PLOT_W} y1={y(at)} y2={y(at)} />
                {[`${at}`, ...words].map((w, i) => (
                  <text key={w} className="wf-note" x={PLOT_W + 6} y={y(at) + 4 + i * 14}>
                    {w}{' '}
                  </text>
                ))}
              </g>
            ))}
            <line className="wf-axis" x1="0" x2={PLOT_W} y1={y(0)} y2={y(0)} />
            {bars.map((b, i) => {
              const middle = slot * i + slot / 2
              const top = y(b.to)
              const height = Math.max(2, y(b.from) - top) // a stage that lost nothing: a tick
              const names = b.second ? [b.name, b.second] : twoLines(b.name)
              return (
                <g key={b.key} data-step={b.key}>
                  {b.title && <title>{b.title}</title>}
                  <rect
                    className={`wf-${b.kind}`}
                    x={middle - BAR / 2}
                    y={top}
                    width={BAR}
                    height={height}
                    rx="2"
                  />
                  <text className="wf-value" x={middle} y={top - 6}>
                    {b.value}
                  </text>
                  {names.map((n, j) => (
                    <text key={j} className="wf-name" x={middle} y={y(0) + 16 + j * 14}>
                      {n}
                    </text>
                  ))}
                </g>
              )
            })}
            {capped && (
              <foreignObject x={PLOT_W - 360} y="0" width="360" height="24">
                <p className="wf-cap">
                  <span>Capped at refer · {data.cap_rule_ids.join(', ')}</span>
                </p>
              </foreignObject>
            )}
          </svg>
        </div>
      )}

      {/* always in the page for screen readers; shown to everyone on request */}
      <div className={asTable ? 'waterfall-table' : 'sr-only'}>
        <table>
          <caption>
            Starts at {data.start}.{data.bonus > 0 && ` Precedent bonus +${data.bonus}.`} Final
            score {data.final}, {data.band}.
          </caption>
          <thead>
            <tr>
              <th scope="col">Stage</th>
              <th scope="col">Out of</th>
              <th scope="col">Earned</th>
              <th scope="col">Lost</th>
            </tr>
          </thead>
          <tbody>
            {data.stages.map((s) => (
              <tr key={s.stage}>
                <th scope="row">{s.label}</th>
                <td>{s.max}</td>
                <td>{s.earned}</td>
                <td>{s.lost}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {aboveLine && (
        <p className="waterfall-note">
          The score is {data.final > data.approve_min ? 'above' : 'at'} {data.approve_min}, but a
          rule keeps this case at refer.
        </p>
      )}
      {capped && asTable && (
        <p className="waterfall-note">
          Capped at refer · <code className="ref-id">{data.cap_rule_ids.join(', ')}</code>
        </p>
      )}
    </section>
  )
}
