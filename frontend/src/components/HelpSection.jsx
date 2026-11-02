import Icon from './Icons'
import './HelpSection.css'

/** One card of a guide. `id` is the anchor the "On this page" menu and the quick cards link to. */
export default function HelpSection({ id, icon, title, children }) {
  return (
    <section id={id} className="help-section card" aria-labelledby={`${id}-h`}>
      <header>
        <span className="help-section-icon">
          <Icon name={icon} size={20} />
        </span>
        <h2 id={`${id}-h`}>{title}</h2>
      </header>
      <div className="help-section-body">{children}</div>
    </section>
  )
}
