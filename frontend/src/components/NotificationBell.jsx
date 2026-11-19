import { useNavigate } from 'react-router-dom'
import Icon from './Icons'
import { useUnread } from './UnreadProvider'
import './NotificationBell.css'

export const inboxPath = (role) => (role === 'admin' ? '/admin/inbox' : '/inbox')

const label = (n) => (n === 0 ? 'Notifications, none unread' : `Notifications, ${n} unread`)

/** The bell in the top bar: a button that opens the inbox. The name carries the real count. */
export default function NotificationBell({ user }) {
  const { count } = useUnread()
  const navigate = useNavigate()
  return (
    <button
      type="button"
      className="bell"
      aria-label={label(count)}
      title="Notifications"
      onClick={() => navigate(inboxPath(user.role))}
    >
      <Icon name="bell" size={18} />
      {count > 0 && (
        <span className="bell-count" aria-hidden="true">
          {count > 99 ? '99+' : count}
        </span>
      )}
    </button>
  )
}
