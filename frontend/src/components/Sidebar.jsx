import { NavLink } from 'react-router-dom'
import BrandMark from './BrandMark'
import Icon from './Icons'
import { useUnread } from './UnreadProvider'
import './Sidebar.css'

const NAV = {
  officer: [
    ['/', 'Home', 'home', true],
    ['/inbox', 'Inbox', 'inbox', false],
    ['/cases', 'Cases', 'cases', true],
    ['/cases/new', 'New case', 'plus', true],
    ['/links', 'Upload links', 'link', false],
    ['/messages', 'Sent items', 'mail', false],
    ['/problems', 'Report a problem', 'flag', false],
    ['/help', 'Help', 'help', false],
  ],
  auditor: [
    ['/', 'Overview', 'chart', true],
    ['/auditor/cases', 'Cases', 'cases', false],
    ['/auditor/audit-log', 'Audit log', 'shield', false],
    ['/auditor/users', 'Users', 'users', false],
    ['/help', 'Help', 'help', false],
  ],
  admin: [
    ['/', 'Home', 'home', true],
    ['/admin/inbox', 'Inbox', 'inbox', false],
    ['/admin/precedents', 'Precedents', 'precedent', false],
    ['/admin/links', 'Upload links', 'link', false],
    ['/admin/messages', 'Messages', 'mail', false],
    ['/admin/issues', 'Issues', 'flag', false],
    ['/admin/users', 'Users', 'users', false],
    ['/admin/ai', 'AI control', 'sliders', false],
    ['/help', 'Help', 'help', false],
  ],
}

/** Left navigation. Icons only on tablet widths; the text stays for screen readers. */
export default function Sidebar({ user }) {
  const { count } = useUnread()
  return (
    <aside className="sidebar">
      <NavLink to="/" className="sidebar-brand" aria-label="Pramaan home">
        <BrandMark />
      </NavLink>
      <nav className="sidebar-nav" aria-label="Main">
        {NAV[user.role].map(([to, label, icon, end]) => (
          <NavLink key={to} to={to} end={end} title={label}>
            <Icon name={icon} />
            <span className="nav-label">{label}</span>
            {label === 'Inbox' && count > 0 && (
              <>
                <span className="nav-badge" aria-hidden="true">
                  {count > 99 ? '99+' : count}
                </span>
                <span className="sr-only">, {count} unread</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
