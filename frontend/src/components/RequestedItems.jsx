import { useId } from 'react'
import { docLabel } from '../lib/docLabels'
import './RequestedItems.css'

export const NOTE_MAX = 200

/** The request is complete when at least one document is ticked or the note says something. */
export const isComplete = (value) => value.items.length > 0 || value.note.trim().length > 0

const clamp = (raw) => Math.min(12, Math.max(1, Math.trunc(Number(raw)) || 1))

/** The body sent to the server: `items` as {type, count} and the tidied note. A count that is
 * empty or out of range while the officer is still typing is brought into 1 to 12 here. */
export const toBody = (value) => ({
  items: value.items.map(({ type, count }) => ({ type, count: clamp(count) })),
  note: value.note.trim(),
})

/**
 * "What do you need?": tick the kinds of document, say how many, and add a short note. It is what
 * the applicant's page shows, in the officer's own words, so the note is checked by the server
 * for personal data and for anything that reads like an outcome.
 */
export default function RequestedItems({ docTypes, value, onChange }) {
  const id = useId()
  const choices = docTypes.filter((t) => t !== 'unknown')
  const ticked = (type) => value.items.find((i) => i.type === type)

  function toggle(type) {
    onChange({
      ...value,
      items: ticked(type)
        ? value.items.filter((i) => i.type !== type)
        : [...value.items, { type, count: 1 }],
    })
  }
  // the box may be empty while typing; it is brought into 1 to 12 when the officer leaves it
  function setCount(type, count) {
    onChange({ ...value, items: value.items.map((i) => (i.type === type ? { ...i, count } : i)) })
  }

  return (
    <div className="requested">
      <fieldset className="requested-items">
        <legend>What do you need?</legend>
        <ul>
          {choices.map((type) => {
            const on = ticked(type)
            return (
              <li key={type}>
                <label>
                  <input type="checkbox" checked={Boolean(on)} onChange={() => toggle(type)} />
                  <span>{docLabel(type)}</span>
                </label>
                {on && (
                  <span className="requested-count">
                    <label htmlFor={`${id}-${type}`} className="sr-only">
                      How many {docLabel(type)}
                    </label>
                    <input
                      id={`${id}-${type}`}
                      className="input"
                      type="number"
                      min="1"
                      max="12"
                      value={on.count}
                      onChange={(e) => setCount(type, e.target.value)}
                      onBlur={() => setCount(type, clamp(on.count))}
                    />
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      </fieldset>
      <div className="field">
        <label htmlFor={`${id}-note`}>
          Note for the applicant <span className="opt">(optional if you ticked something)</span>
        </label>
        <textarea
          id={`${id}-note`}
          className="input"
          rows={3}
          maxLength={NOTE_MAX}
          value={value.note}
          onChange={(e) => onChange({ ...value, note: e.target.value })}
        />
        <p className="small muted">
          {value.note.length} of {NOTE_MAX}. The applicant reads this on their page. Do not write
          personal numbers or anything about the result.
        </p>
      </div>
    </div>
  )
}
