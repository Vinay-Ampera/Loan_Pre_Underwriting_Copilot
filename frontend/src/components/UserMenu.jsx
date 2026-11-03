import { useEffect, useRef, useState } from 'react'
import Dialog from './Dialog'
import Icon from './Icons'
import './UserMenu.css'

const ROLE = { officer: 'Loan officer', admin: 'Admin', auditor: 'Auditor' }

/** Top-right account menu: who is signed in, and Sign out (which asks first). */
export default function UserMenu({ user, onSignOut }) {
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const root = useRef(null)

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
    <div className="user-menu" ref={root}>
      <button
        type="button"
        className="user-menu-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="avatar" aria-hidden="true">
          {user.name.trim().charAt(0).toUpperCase()}
        </span>
        <span className="user-menu-name">{user.name}</span>
        <span className="role-tag">{user.role === 'auditor' ? 'Auditor' : user.role}</span>
        {user.role === 'auditor' && <span className="readonly-badge">Read-only</span>}
      </button>
      {open && (
        <div className="user-menu-list card" role="menu">
          <div className="user-menu-who">
            <strong>{user.name}</strong>
            <span className="small muted">{user.email}</span>
            <span className="small muted">{ROLE[user.role] ?? user.role}</span>
            {user.role === 'auditor' && (
              <span className="readonly-badge">Read-only: this account changes nothing</span>
            )}
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              setConfirming(true)
            }}
          >
            <Icon name="signout" />
            Sign out
          </button>
        </div>
      )}
      {confirming && (
        <Dialog title="Sign out?" onClose={() => setConfirming(false)} labelledBy="signout-title">
          <p>You will need your email and password to sign in again.</p>
          <div className="dialog-actions">
            <button
              type="button"
              className="btn"
              onClick={() => setConfirming(false)}
              data-autofocus
            >
              Stay signed in
            </button>
            <button type="button" className="btn btn-primary" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </Dialog>
      )}
    </div>
  )
}
