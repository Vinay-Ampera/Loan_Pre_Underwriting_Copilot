import { describe, expect, it } from 'vitest'
import { journeyState, JOURNEY } from './journey'

const states = (c) => journeyState(c).map((s) => s.state)

describe('journeyState', () => {
  it('has the five banking stages in order', () => {
    expect(JOURNEY.map((s) => s.id)).toEqual(['intake', 'verify', 'risk', 'decision', 'signoff'])
  })

  it('starts at intake for a draft', () => {
    expect(states({ status: 'draft' })).toEqual(['current', 'todo', 'todo', 'todo', 'todo'])
  })

  it('follows the stages that have run while the case is running', () => {
    const run = (...stages) => ({ status: 'running', stages: stages.map((stage) => ({ stage })) })
    expect(states(run())).toEqual(['current', 'todo', 'todo', 'todo', 'todo'])
    expect(states(run('extraction'))).toEqual(['done', 'current', 'todo', 'todo', 'todo'])
    expect(states(run('extraction', 'kyc', 'risk'))).toEqual([
      'done',
      'done',
      'done',
      'current',
      'todo',
    ])
  })

  it('waits for the human at stage 5 and never calls it done', () => {
    expect(states({ status: 'awaiting_confirmation' })).toEqual([
      'done',
      'done',
      'done',
      'done',
      'current',
    ])
  })

  it('is done only after the officer has acted', () => {
    expect(states({ status: 'confirmed' }).every((s) => s === 'done')).toBe(true)
    expect(states({ status: 'overridden' }).every((s) => s === 'done')).toBe(true)
  })

  it('shows the stage where a stopped case stopped', () => {
    const stopped = (stopped_stage) => ({ status: 'stopped', report: { stopped_stage } })
    expect(states(stopped('kyc'))).toEqual(['done', 'stopped', 'todo', 'todo', 'todo'])
    expect(states(stopped('extraction'))).toEqual(['stopped', 'todo', 'todo', 'todo', 'todo'])
    expect(states(stopped('policy'))).toEqual(['done', 'done', 'done', 'stopped', 'todo'])
  })
})
