import { useState } from 'react'
import Icon from './Icons'
import './TwoStep.css'

/** The code box: six digits from the app, or (after the switch) one recovery code. */
function CodeField({ recovery, value, onChange }) {
  return (
    <div className="field">
      <label htmlFor="two-step-code">{recovery ? 'Recovery code' : '6-digit code'}</label>
      <input
        id="two-step-code"
        className="input two-step-input mono"
        inputMode={recovery ? 'text' : 'numeric'}
        autoComplete="one-time-code"
        autoCapitalize="none"
        spellCheck={false}
        maxLength={recovery ? 14 : 7}
        placeholder={recovery ? 'xxxxx-xxxxx' : '000000'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
        autoFocus
      />
    </div>
  )
}

function Problem({ error }) {
  if (!error) return null
  return (
    <p className="field-error" role="alert">
      {error}
    </p>
  )
}

function BackLink({ onBack }) {
  return (
    <button type="button" className="btn btn-ghost two-step-back" onClick={onBack}>
      Use a different account
    </button>
  )
}

/** After the password, for an account with 2-step turned on. */
export function CodeStep({ busy, error, onVerify, onBack }) {
  const [recovery, setRecovery] = useState(false)
  const [code, setCode] = useState('')
  return (
    <form
      className="two-step"
      onSubmit={(e) => {
        e.preventDefault()
        onVerify(code)
      }}
    >
      <div className="login-card-head">
        <h2>Enter your code</h2>
        <p className="muted">
          {recovery
            ? 'Type one of the recovery codes you saved when you set up 2-step verification. Each one works once.'
            : 'Open Microsoft Authenticator on your phone and type the 6-digit code shown for Pramaan.'}
        </p>
      </div>
      <CodeField recovery={recovery} value={code} onChange={setCode} />
      <Problem error={error} />
      <button type="submit" className="btn btn-primary login-submit" disabled={busy}>
        {busy ? 'Checking…' : 'Verify and sign in'}
      </button>
      <button
        type="button"
        className="btn btn-ghost"
        onClick={() => {
          setRecovery((r) => !r)
          setCode('')
        }}
      >
        {recovery ? 'Use the code from the app' : 'Lost your phone? Use a recovery code'}
      </button>
      <BackLink onBack={onBack} />
    </form>
  )
}

/** First sign-in (or after a reset): scan the QR code, then prove it with the first code. */
export function SetupStep({ setup, busy, error, onVerify, onBack }) {
  const [code, setCode] = useState('')
  return (
    <form
      className="two-step"
      onSubmit={(e) => {
        e.preventDefault()
        onVerify(code)
      }}
    >
      <div className="login-card-head">
        <h2>Set up 2-step verification</h2>
        <p className="muted">
          Your account signs in with your password and a code from your phone. You do this once; it
          takes about a minute.
        </p>
      </div>
      <ol className="two-step-list">
        <li>
          Install <strong>Microsoft Authenticator</strong> on your phone from the App Store or
          Google Play.
        </li>
        <li>
          In the app, tap <strong>+</strong>, choose <strong>Other (Google, Facebook, etc.)</strong>{' '}
          and scan this QR code.
          <img
            className="two-step-qr"
            src={setup.qr}
            alt="QR code to add Pramaan to Microsoft Authenticator"
            width="200"
            height="200"
          />
          <details className="two-step-key">
            <summary>Cannot scan it? Type the key instead</summary>
            <p className="small muted">
              In the app choose &ldquo;Enter code manually&rdquo;. Account name: {setup.account}
            </p>
            <p className="mono two-step-secret" data-testid="two-step-key">
              {setup.key}
            </p>
          </details>
        </li>
        <li>Type the 6-digit code the app now shows for Pramaan.</li>
      </ol>
      <CodeField recovery={false} value={code} onChange={setCode} />
      <Problem error={error} />
      <button type="submit" className="btn btn-primary login-submit" disabled={busy}>
        {busy ? 'Checking…' : 'Turn on and sign in'}
      </button>
      <BackLink onBack={onBack} />
    </form>
  )
}

function saveAsText(codes) {
  const text = `Pramaan recovery codes\nEach code signs you in once if you lose your phone.\n\n${codes.join('\n')}\n`
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
  const a = document.createElement('a')
  a.href = url
  a.download = 'pramaan-recovery-codes.txt'
  a.click()
  URL.revokeObjectURL(url)
}

/** Shown once, straight after setup. The person must say they saved them before going on. */
export function RecoveryCodes({ codes, onDone }) {
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState(false)
  return (
    <div className="two-step">
      <div className="login-card-head">
        <h2>Save your recovery codes</h2>
        <p className="muted">
          2-step verification is on. If you lose your phone, each code below signs you in once
          instead of the app. They are shown only now: keep them somewhere safe, away from your
          phone.
        </p>
      </div>
      <ul className="two-step-codes mono" aria-label="Recovery codes">
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="two-step-row">
        <button
          type="button"
          className="btn"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(codes.join('\n'))
              setCopied(true)
            } catch {
              setCopied(false)
            }
          }}
        >
          <Icon name={copied ? 'check' : 'copy'} />
          {copied ? 'Copied' : 'Copy'}
        </button>
        <button type="button" className="btn" onClick={() => saveAsText(codes)}>
          <Icon name="file" />
          Download
        </button>
      </div>
      <label className="two-step-check">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />I have
        saved these codes
      </label>
      <button
        type="button"
        className="btn btn-primary login-submit"
        disabled={!saved}
        onClick={onDone}
      >
        Continue to Pramaan
      </button>
    </div>
  )
}

/** After a recovery code: how many are left, and what to do about the lost phone. */
export function RecoveryUsed({ left, onDone }) {
  return (
    <div className="two-step">
      <div className="login-card-head">
        <h2>Signed in with a recovery code</h2>
        <p className="muted">
          That code is now used up. You have{' '}
          <strong>
            {left} recovery code{left === 1 ? '' : 's'}
          </strong>{' '}
          left.
        </p>
      </div>
      <p className={left <= 2 ? 'two-step-warn' : 'small muted'} role="status">
        If you lost your phone, ask your admin to reset your 2-step verification. At your next
        sign-in you then scan a new QR code.
      </p>
      <button type="button" className="btn btn-primary login-submit" onClick={onDone}>
        Continue to Pramaan
      </button>
    </div>
  )
}
