import Icon from './Icons'
import './ChoiceCard.css'

/** One option of a card-style radio group: an icon tile, a name, a short line, a check mark. */
export default function ChoiceCard({ icon, title, children, checked, disabled, onSelect }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      disabled={disabled}
      className={`choice-card${checked ? ' selected' : ''}`}
      onClick={onSelect}
    >
      <span className="choice-top">
        {icon && (
          <span className="choice-icon">
            <Icon name={icon} size={20} />
          </span>
        )}
        <span className="choice-mark">{checked && <Icon name="check" size={12} />}</span>
      </span>
      <span className="choice-title">{title}</span>
      {children && <span className="choice-text">{children}</span>}
    </button>
  )
}
