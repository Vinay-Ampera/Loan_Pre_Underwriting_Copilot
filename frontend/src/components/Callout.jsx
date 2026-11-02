import Icon from './Icons'
import './Callout.css'

const ICON = { info: 'info', warn: 'alert', ok: 'shield' }

/** A highlighted note inside a guide: an icon, a bold title and a line of text. */
export default function Callout({ tone = 'info', title, children }) {
  return (
    <aside className={`callout callout-${tone}`}>
      <span className="callout-icon">
        <Icon name={ICON[tone]} size={20} />
      </span>
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </aside>
  )
}
