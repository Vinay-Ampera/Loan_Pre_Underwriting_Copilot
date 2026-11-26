import StatusChip from './StatusChip'
import { formatWhen } from '../lib/format'

const STATES = {
  due_today: ['refer', 'clock', 'Due today'],
  overdue: ['reject', 'alert', 'Overdue'],
}

/**
 * The decision timer's badge (Stage 12 Part C). The server says which state a case is in; nothing
 * is shown for a case that is not timed.
 */
export default function DueBadge({ state, dueAt, workingDays }) {
  if (!STATES[state]) return null
  const [tone, icon, label] = STATES[state]
  const target = workingDays ? ` (${workingDays} working days after the report)` : ''
  const detail = `Decision due ${formatWhen(dueAt)}${target}`
  return (
    <StatusChip tone={tone} icon={icon} title={detail}>
      {label}
      <span className="sr-only">. {detail}</span>
    </StatusChip>
  )
}
