import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import Dialog from './Dialog'
import Icon from './Icons'
import './UserMenu.css'

const ROLE = { officer: 'Loan officer', admin: 'Admin', auditor: 'Auditor' }

/** Top-right account menu: who is signed in, and Sign out (which asks first). */
export default function UserMenu({ user, onSignOut }) {
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [emails, setEmails] = useState(null) // notice emails on or off; null until read
  const [prefError, setPrefError] = useState(null)
  const root = useRef(null)
  const hasInbox = user.role === 'officer' || user.role === 'admin'

  // read the person's choice the first time the menu opens
  useEffect(() => {
    if (!open || !hasInbox || emails !== null) return
    api
      .get('/me/preferences')
      .then((p) => setEmails(p.notice_emails))
      .catch(() => setPrefError('Could not read your email setting.'))
  }, [open, hasInbox, emails])

  async function toggleEmails() {
    const next = !emails
    setPrefError(null)
    try {
      const saved = await api.put('/me/preferences', { notice_emails: next })
      setEmails(saved.notice_emails)
    } catch {
      setPrefError('Could not save. Try again.')
    }
  }

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
          {hasInbox && emails !== null && (
            <button
              type="button"
              role="menuitemcheckbox"
              aria-checked={emails}
              className="user-menu-check"
              onClick={toggleEmails}
            >
              <Icon name={emails ? 'check' : 'minus'} />
              Email me about new notices
            </button>
          )}
          {prefError && (
            <p className="small field-error user-menu-note" role="alert">
              {prefError}
            </p>
          )}
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
