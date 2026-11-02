import { useState } from 'react'
import { login } from '../api/client'
import { useSession } from '../App'
import BrandMark from '../components/BrandMark'
import ThemeToggle from '../components/ThemeToggle'
import { JOURNEY } from '../lib/journey'
import './LoginPage.css'

// The scoring weights and bands, shown as facts. They come from the locked scoring decision
// (rules file); nothing is computed here.
const WEIGHTS = [
  ['KYC', 20],
  ['Documents', 15],
  ['Income and FOIR', 30],
  ['Credit', 25],
  ['Policy fit', 10],
]

function BrandPanel() {
  return (
    <section className="login-panel" aria-label="About Pramaan">
      <BrandMark inverse />
      <h1 className="login-headline">Proof before every decision.</h1>
      <p className="login-lead">
        Pramaan checks a loan file stage by stage, scores it in code and cites the policy. The loan
        officer decides.
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
      <div className="scorebar-wrap">
        <p className="scorebar-title">The score: 100 points</p>
        <ul className="scorebar" aria-label="Score weights">
          {WEIGHTS.map(([name, pts]) => (
            <li key={name} style={{ flexGrow: pts }}>
              <span className="seg-pts">{pts}</span>
              <span className="seg-name">{name}</span>
            </li>
          ))}
        </ul>
        <p className="bands">
          85 and above: recommend approve · 60 to 84: refer · below 60: recommend reject
        </p>
      </div>
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
        </form>
      </main>
    </div>
  )
}
