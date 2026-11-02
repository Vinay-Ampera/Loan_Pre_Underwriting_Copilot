import { useEffect, useState } from 'react'
import { applyTheme, readTheme, saveTheme } from '../lib/theme'
import Icon from './Icons'
import './ThemeToggle.css'

const OPTIONS = [
  ['system', 'monitor', 'System theme'],
  ['dark', 'moon', 'Dark theme'],
  ['light', 'sun', 'Light theme'],
]

/** Three-way pill: system (default), dark, light. The active one is ringed. */
export default function ThemeToggle() {
  const [choice, setChoice] = useState(readTheme)
  useEffect(() => applyTheme(choice), [choice])

  function pick(value) {
    saveTheme(value)
    setChoice(value)
  }

  return (
    <div className="theme-toggle" role="radiogroup" aria-label="Colour theme">
      {OPTIONS.map(([value, icon, label]) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={choice === value}
          aria-label={label}
          title={label}
          className={choice === value ? 'on' : ''}
          onClick={() => pick(value)}
        >
          <Icon name={icon} size={16} />
        </button>
      ))}
    </div>
  )
}
