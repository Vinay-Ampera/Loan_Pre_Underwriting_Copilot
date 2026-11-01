import { Link, NavLink } from 'react-router-dom'
import './TopBar.css'

export default function TopBar({ user, onSignOut }) {
  return (
    <header className="topbar">
      <Link to="/" className="brand">
        <span className="brand-mark" aria-hidden="true">
          ◆
        </span>
        Loan Copilot
      </Link>
      <nav className="topnav" aria-label="Main">
        {user.role === 'officer' && <NavLink to="/">Cases</NavLink>}
        {user.role === 'officer' && <NavLink to="/cases/new">New case</NavLink>}
        {user.role === 'admin' && <NavLink to="/admin/precedents">Precedent queue</NavLink>}
      </nav>
      <div className="who">
        <span>
          {user.name} <span className="role-tag">{user.role}</span>
        </span>
        <button type="button" className="btn btn-ghost" onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </header>
  )
}
