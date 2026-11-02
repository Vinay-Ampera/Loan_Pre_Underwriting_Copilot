import { NavLink } from 'react-router-dom'
import BrandMark from './BrandMark'
import Icon from './Icons'
import ThemeToggle from './ThemeToggle'
import './Sidebar.css'

const NAV = {
  officer: [
    ['/', 'Home', 'home', true],
    ['/cases', 'Cases', 'cases', true],
    ['/cases/new', 'New case', 'plus', true],
    ['/messages', 'Sent items', 'mail', false],
    ['/problems', 'Report a problem', 'flag', false],
    ['/help', 'Help', 'help', false],
  ],
  admin: [
    ['/', 'Home', 'home', true],
    ['/admin/precedents', 'Precedents', 'precedent', false],
    ['/admin/users', 'Users', 'users', false],
    ['/admin/issues', 'Issues', 'flag', false],
    ['/help', 'Help', 'help', false],
  ],
}

/** Left navigation. Icons only on tablet widths; the text stays for screen readers. */
export default function Sidebar({ user, onSignOut }) {
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
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-foot">
        <ThemeToggle />
        <div className="sidebar-user">
          <span className="user-name">{user.name}</span>
          <span className="role-tag">{user.role}</span>
        </div>
        <button type="button" className="btn btn-ghost sign-out" onClick={onSignOut}>
          <Icon name="signout" />
          <span className="nav-label">Sign out</span>
        </button>
      </div>
    </aside>
  )
}
