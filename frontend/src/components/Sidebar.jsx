import { useEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
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
    ['/policies', 'Policies', 'book', false],
    ['/problems', 'Report a problem', 'flag', false],
    ['/help', 'Help', 'help', false],
  ],
  auditor: [
    ['/', 'Overview', 'chart', true],
    ['/auditor/insights', 'Insights', 'trend', false],
    ['/auditor/cases', 'Cases', 'cases', false],
    ['/auditor/audit-log', 'Audit log', 'shield', false],
    ['/auditor/users', 'Users', 'users', false],
    ['/help', 'Help', 'help', false],
  ],
  admin: [
    ['/', 'Home', 'home', true],
    ['/admin/insights', 'Insights', 'trend', false],
    ['/admin/inbox', 'Inbox', 'inbox', false],
    ['/admin/precedents', 'Precedents', 'precedent', false],
    ['/admin/knowledge', 'Knowledge base', 'book', false],
    ['/admin/links', 'Upload links', 'link', false],
    ['/admin/messages', 'Messages', 'mail', false],
    ['/admin/issues', 'Issues', 'flag', false],
    ['/admin/users', 'Users', 'users', false],
    ['/admin/ai', 'AI control', 'sliders', false],
    ['/help', 'Help', 'help', false],
  ],
}

/**
 * Left navigation. Icons only on tablet widths (the text stays for screen readers). On a phone it
 * is a bar with the brand and a Menu button that opens the pages, with their names, as a list.
 */
export default function Sidebar({ user }) {
  const { count } = useUnread()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const root = useRef(null)

  useEffect(() => setOpen(false), [pathname]) // a page was chosen
  useEffect(() => {
    if (!open) return undefined
    const away = (e) => !root.current?.contains(e.target) && setOpen(false)
    const esc = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  return (
    <aside className="sidebar" ref={root}>
      <NavLink to="/" className="sidebar-brand" aria-label="Pramaan home">
        <BrandMark />
      </NavLink>
      <button
        type="button"
        className="sidebar-menu-btn"
        aria-expanded={open}
        aria-controls="main-nav"
        onClick={() => setOpen((o) => !o)}
      >
        <Icon name={open ? 'x' : 'menu'} />
        Menu
        {count > 0 && (
          <>
            <span className="nav-badge" aria-hidden="true">
              {count > 99 ? '99+' : count}
            </span>
            <span className="sr-only">, {count} unread</span>
          </>
        )}
      </button>
      <nav id="main-nav" className={`sidebar-nav${open ? ' open' : ''}`} aria-label="Main">
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
