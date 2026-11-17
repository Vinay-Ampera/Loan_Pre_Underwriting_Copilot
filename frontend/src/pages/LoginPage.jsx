import { useState } from 'react'
import { login } from '../api/client'
import { takeNotice } from '../api/session'
import { useSession } from '../App'
import BrandMark from '../components/BrandMark'
import Icon from '../components/Icons'
import ThemeToggle from '../components/ThemeToggle'
import { JOURNEY } from '../lib/journey'
import './LoginPage.css'

function BrandPanel() {
  return (
    <section className="login-panel" aria-label="About Pramaan">
      <BrandMark />
      <div className="login-intro">
        <h1 className="login-headline">Proof before every decision</h1>
        <p className="login-lead">
          Pramaan checks a loan file stage by stage, scores it in code and cites the policy. The
          loan officer decides.
        </p>
      </div>
      <figure className="case-file">
        <figcaption className="case-file-head">
          <span>How every case moves</span>
          <span className="case-file-count">5 stages</span>
        </figcaption>
        <ol className="journey" aria-label="The five underwriting stages">
          {JOURNEY.map((s, i) => (
            <li key={s.id} className={s.id === 'signoff' ? 'journey-human' : undefined}>
              <span className="journey-n" aria-hidden="true">
                {s.id === 'signoff' ? <Icon name="shield-check" size={16} /> : `0${i + 1}`}
              </span>
              <span className="journey-text">
                <strong>{s.label}</strong>
                <span className="journey-detail">{s.detail}</span>
              </span>
            </li>
          ))}
        </ol>
        <p className="login-human">A human confirms every case.</p>
      </figure>
      <p className="login-about">
        Documents are read on this machine first, personal details are masked before any model sees
        the text, and every finding points to a rule.
      </p>
      <p className="login-note">Pramaan is a sample bank. Synthetic data only.</p>
    </section>
  )
}

export default function LoginPage() {
  const { signIn } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [notice] = useState(takeNotice)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      signIn(await login(email.trim(), password))
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <BrandPanel />
      <main className="login-side">
        <div className="login-theme">
          <ThemeToggle />
        </div>
        <form className="login-card card" onSubmit={submit}>
          <div className="login-card-head">
            <h2>Sign in</h2>
            <p className="muted">Staff accounts only. Your admin creates your account.</p>
          </div>
          {notice && (
            <p className="login-notice" role="status">
              {notice}
            </p>
          )}
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className="input"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <div className="password-wrap">
              <input
                id="password"
                className="input"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                aria-pressed={showPassword}
              >
                <Icon name={showPassword ? 'eye-off' : 'eye'} size={18} />
              </button>
            </div>
          </div>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary login-submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <div className="login-fine">
            <p className="small muted">
              Synthetic data only. Do not enter real customer information.
            </p>
            <p className="small muted login-help">Can&apos;t sign in? Contact your admin.</p>
          </div>
        </form>
      </main>
    </div>
  )
}
