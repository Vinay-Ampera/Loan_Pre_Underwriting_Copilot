import { journeyState } from '../lib/journey'
import Icon from './Icons'
import './CaseStepper.css'

const WORD = { done: 'done', current: 'in progress', stopped: 'stopped here', todo: 'not started' }
const MARK = { done: 'check', current: 'dot', stopped: 'x' }

/** The five underwriting stages and where the case is. A stopped case stops at the failing one. */
export default function CaseStepper({ caseData, stopText }) {
  const steps = journeyState(caseData)
  const stopped = steps.find((s) => s.state === 'stopped')
  const allDone = steps.every((s) => s.state === 'done')
  return (
    <div className={`stepper-wrap card${allDone ? ' stepper-done' : ''}`}>
      <ol className="stepper" aria-label="Underwriting stages">
        {steps.map((s, i) => (
          <li
            key={s.id}
            className={`step step-${s.state}`}
            aria-current={s.state === 'current' || s.state === 'stopped' ? 'step' : undefined}
          >
            <span className="step-dot" aria-hidden="true">
              {MARK[s.state] ? <Icon name={MARK[s.state]} size={14} /> : i + 1}
            </span>
            <span className="step-text">
              <span className="step-label">{s.label}</span>
              <span className="step-detail">{s.detail}</span>
              <span className="step-state">{WORD[s.state]}</span>
            </span>
          </li>
        ))}
      </ol>
      {stopped && stopText && (
        <p className="step-stop" role="note">
          Stopped at “{stopped.label}”: {stopText}
        </p>
      )}
    </div>
  )
}
