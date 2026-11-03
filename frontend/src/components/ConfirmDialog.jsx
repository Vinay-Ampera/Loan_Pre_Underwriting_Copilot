import Dialog from './Dialog'

/**
 * The second click for anything that deletes or cannot be undone. Nothing happens until the
 * button here is pressed; Cancel has focus first so a stray Enter never confirms.
 */
export default function ConfirmDialog({
  title,
  children,
  confirmLabel,
  danger = true,
  busy = false,
  error = null,
  onClose,
  onConfirm,
}) {
  return (
    <Dialog title={title} onClose={onClose} labelledBy="confirm-dialog-title">
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
