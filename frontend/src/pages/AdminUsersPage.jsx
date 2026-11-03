import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useSession } from '../App'
import { useAsync } from '../hooks/useAsync'
import Dialog from '../components/Dialog'
import StatusChip from '../components/StatusChip'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import './AdminUsersPage.css'

function CreateDialog({ onClose, onCreated }) {
  const [form, setForm] = useState({ name: '', email: '', role: 'officer' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onCreated(await api.post('/admin/users', form))
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <Dialog title="Add a user" onClose={onClose} labelledBy="create-user-title">
      <form className="user-form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="u-name">Full name</label>
          <input
            id="u-name"
            className="input"
            value={form.name}
            onChange={set('name')}
            required
            data-autofocus
          />
        </div>
        <div className="field">
          <label htmlFor="u-email">Email</label>
          <input
            id="u-email"
            className="input"
            type="email"
            value={form.email}
            onChange={set('email')}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="u-role">Role</label>
          <select id="u-role" className="select" value={form.role} onChange={set('role')}>
            <option value="officer">Loan officer</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <p className="small muted">
          A temporary password is made for the account and shown once on the next screen.
        </p>
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Creating…' : 'Create user'}
          </button>
        </div>
      </form>
    </Dialog>
  )
}

function PasswordDialog({ title, email, password, onClose }) {
  return (
    <Dialog title={title} onClose={onClose} labelledBy="temp-password-title">
      <p>
        Temporary password for <strong>{email}</strong>. It is shown only now and is not stored or
        logged. Pass it to the person privately.
      </p>
      <p className="temp-password mono" data-testid="temp-password">
        {password}
      </p>
      <div className="dialog-actions">
        <button type="button" className="btn btn-primary" onClick={onClose} data-autofocus>
          I have copied it
        </button>
      </div>
    </Dialog>
  )
}

function ConfirmDialog({ title, children, confirmLabel, danger, busy, error, onClose, onConfirm }) {
  return (
    <Dialog title={title} onClose={onClose} labelledBy="confirm-user-title">
      {children}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      <div className="dialog-actions">
        <button type="button" className="btn" onClick={onClose} data-autofocus>
          Cancel
        </button>
        <button
          type="button"
          className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
          disabled={busy}
          onClick={onConfirm}
        >
          {confirmLabel}
        </button>
      </div>
    </Dialog>
  )
}

export default function AdminUsersPage() {
  const { session } = useSession()
  const { data, error, loading, reload } = useAsync(() => api.get('/admin/users'), [])
  const [dialog, setDialog] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)

  const close = () => {
    setDialog(null)
    setActionError(null)
  }

  async function run(path, then) {
    setBusy(true)
    setActionError(null)
    try {
      const res = await api.post(path)
      then?.(res)
      reload()
    } catch (e) {
      setActionError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="admin-users">
      <header className="users-head">
        <div>
          <h1>Users</h1>
          <p className="muted">
            Staff accounts. There is no sign-up: accounts are made here. Every change is written to
            the audit log.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => setDialog({ kind: 'create' })}
        >
          Add user
        </button>
      </header>

      {loading && <Skeleton lines={4} height={40} />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && <EmptyState title="No users">Add the first user.</EmptyState>}
      {data && data.length > 0 && (
        <div className="card users-wrap">
          <table className="users">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((u) => {
                const me = u.id === session.user.id
                return (
                  <tr key={u.id}>
                    <td data-label="Name">
                      {u.role === 'officer' ? (
                        <Link to={`/admin/users/${u.id}`}>{u.name}</Link>
                      ) : (
                        u.name
                      )}{' '}
                      {me && <span className="muted">(you)</span>}
                    </td>
                    <td data-label="Email">{u.email}</td>
                    <td data-label="Role">{u.role}</td>
                    <td data-label="Status">
                      {u.active ? (
                        u.locked ? (
                          <StatusChip tone="refer">Locked after failed sign-ins</StatusChip>
                        ) : (
                          <StatusChip tone="approve">Active</StatusChip>
                        )
                      ) : (
                        <StatusChip tone="stopped">Disabled</StatusChip>
                      )}
                    </td>
                    <td className="row-actions">
                      <button
                        type="button"
                        className="btn"
                        onClick={() => setDialog({ kind: 'reset', user: u })}
                        aria-label={`Reset password for ${u.name}`}
                      >
                        Reset password
                      </button>
                      {u.active ? (
                        <button
                          type="button"
                          className="btn"
                          disabled={me}
                          title={me ? 'You cannot disable your own account' : undefined}
                          onClick={() => setDialog({ kind: 'disable', user: u })}
                          aria-label={`Disable ${u.name}`}
                        >
                          Disable
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn"
                          onClick={() => run(`/admin/users/${u.id}/enable`)}
                          aria-label={`Enable ${u.name}`}
                        >
                          Enable
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {actionError && !dialog && (
        <p className="field-error" role="alert">
          {actionError}
        </p>
      )}

      {dialog?.kind === 'create' && (
        <CreateDialog
          onClose={close}
          onCreated={(res) => {
            reload()
            setDialog({ kind: 'password', title: 'User created', res })
          }}
        />
      )}
      {dialog?.kind === 'password' && (
        <PasswordDialog
          title={dialog.title}
          email={dialog.res.email}
          password={dialog.res.temporary_password}
          onClose={close}
        />
      )}
      {dialog?.kind === 'disable' && (
        <ConfirmDialog
          title="Disable this account?"
          confirmLabel="Yes, disable"
          danger
          busy={busy}
          error={actionError}
          onClose={close}
          onConfirm={() => run(`/admin/users/${dialog.user.id}/disable`, close)}
        >
          <p>
            <strong>{dialog.user.name}</strong> will be signed out and will not be able to sign in
            until you enable the account again.
          </p>
        </ConfirmDialog>
      )}
      {dialog?.kind === 'reset' && (
        <ConfirmDialog
          title="Reset this password?"
          confirmLabel="Yes, reset password"
          busy={busy}
          error={actionError}
          onClose={close}
          onConfirm={() =>
            run(`/admin/users/${dialog.user.id}/reset-password`, (res) =>
              setDialog({ kind: 'password', title: 'Password reset', res }),
            )
          }
        >
          <p>
            A new temporary password is made for <strong>{dialog.user.name}</strong>. The old one
            stops working at once.
          </p>
        </ConfirmDialog>
      )}
    </div>
  )
}
