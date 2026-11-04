import { useState } from 'react'
import { login } from '../api/client'
import { takeNotice } from '../api/session'
import { useSession } from '../App'
import BrandMark from '../components/BrandMark'
import ThemeToggle from '../components/ThemeToggle'
import { JOURNEY } from '../lib/journey'
import './LoginPage.css'

function BrandPanel() {
  return (
    <section className="login-panel" aria-label="About Pramaan">
      <BrandMark inverse />
      <h1 className="login-headline">Proof before every decision.</h1>
      <p className="login-lead">
        Pramaan checks a loan file stage by stage, scores it in code and cites the policy. The loan
        officer decides.
      </p>
      <p className="login-about">
        Documents are read on this machine first, personal details are masked before any model sees
        the text, and every finding points to a rule.
      </p>
      <ol className="journey" aria-label="The five underwriting stages">
        {JOURNEY.map((s, i) => (
          <li key={s.id} style={{ '--i': i }}>
            <span className="journey-n" aria-hidden="true">
              {i + 1}
            </span>
            <span>
              <strong>{s.label}</strong>
              <span className="journey-detail">{s.detail}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="login-human">A human confirms every case.</p>
      <p className="login-note">Pramaan is a sample bank. Synthetic data only.</p>
    </section>
  )
}

export default function LoginPage() {
  const { signIn } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
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
        <div className="login-glow" aria-hidden="true" />
        <form className="login-card card" onSubmit={submit}>
          <h2>Sign in</h2>
          <p className="muted">Staff accounts only. Your admin creates your account.</p>
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
            <input
              id="password"
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="small muted">
            Synthetic data only. Do not enter real customer information.
          </p>
          <p className="small muted login-help">Can&apos;t sign in? Contact your admin.</p>
        </form>
      </main>
    </div>
  )
}
