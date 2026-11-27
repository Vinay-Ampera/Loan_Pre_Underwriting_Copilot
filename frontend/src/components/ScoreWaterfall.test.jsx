import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import ScoreWaterfall from './ScoreWaterfall'

const stage = (id, label, max, earned, lost, levelAfter) => ({
  stage: id,
  label,
  max,
  earned,
  lost,
  level_after: levelAfter,
})
const data = {
  start: 100,
  stages: [
    stage('kyc', 'KYC', 20, 18, 2, 98),
    stage('documents', 'Documents', 15, 15, 0, 98),
    stage('income', 'Income and FOIR', 30, 12, 18, 80),
    stage('credit', 'Credit and behaviour', 25, 19, 6, 74),
    stage('policy', 'Policy fit', 10, 8, 2, 72),
  ],
  bonus: 0,
  final: 72,
  band: 'refer',
  approve_min: 85,
  refer_min: 60,
  cap_rule_ids: [],
}
const step = (container, id) => container.querySelector(`[data-step="${id}"]`)
const height = (container, id) =>
  Number(step(container, id).querySelector('rect').getAttribute('height'))

describe('ScoreWaterfall', () => {
  it('draws one labelled bar per step, the band lines and a text summary', () => {
    const { container } = render(<ScoreWaterfall data={data} />)
    const chart = screen.getByRole('img')
    expect(chart).toHaveAccessibleName(
      'Score breakdown: starts at 100; KYC lost 2, Documents lost 0, Income and FOIR lost 18, ' +
        'Credit and behaviour lost 6, Policy fit lost 2; final score 72, refer.',
    )
    expect(container.querySelectorAll('[data-step]')).toHaveLength(7)
    expect(step(container, 'income')).toHaveTextContent('−18')
    expect(step(container, 'final')).toHaveTextContent('Score 72')
    expect(chart).toHaveTextContent('85 recommend approve')
    expect(chart).toHaveTextContent('60 refer')
    // bar heights follow the points; a stage that lost nothing is a thin tick
    expect(height(container, 'income')).toBeCloseTo(36)
    expect(height(container, 'documents')).toBe(2)
    expect(step(container, 'documents')).toHaveTextContent('−0')
    expect(step(container, 'bonus')).toBeNull()
    expect(screen.queryByText(/Capped at refer/)).toBeNull()
  })

  it('has the same numbers as a table, shown on request', async () => {
    const user = userEvent.setup()
    render(<ScoreWaterfall data={data} />)
    const rows = () => within(screen.getByRole('table')).getAllByRole('row')
    expect(rows()[3]).toHaveTextContent('Income and FOIR301218')
    expect(screen.getByRole('table').parentElement).toHaveClass('sr-only')
    await user.click(screen.getByRole('button', { name: 'Show as a table' }))
    expect(screen.getByRole('table').parentElement).not.toHaveClass('sr-only')
    expect(screen.queryByRole('img')).toBeNull()
    // in the table view the button offers the way back
    await user.click(screen.getByRole('button', { name: 'Show as a graph' }))
    expect(screen.getByRole('img')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show as a table' })).toBeInTheDocument()
  })

  it('shows exactly the numbers it is given and works none out', () => {
    // deliberately inconsistent: a component that computed anything would disagree
    const odd = { ...data, stages: [stage('kyc', 'KYC', 20, 99, 7, 50)], final: 41 }
    const { container } = render(<ScoreWaterfall data={odd} />)
    expect(step(container, 'kyc')).toHaveTextContent('−7')
    expect(step(container, 'final')).toHaveTextContent('41')
    expect(screen.getByRole('table')).toHaveTextContent('KYC20997')
  })

  it('draws a precedent bonus as a step up', () => {
    const { container } = render(<ScoreWaterfall data={{ ...data, bonus: 3, final: 75 }} />)
    expect(step(container, 'bonus')).toHaveTextContent('+3')
    expect(step(container, 'bonus').querySelector('rect')).toHaveClass('wf-bonus')
    expect(screen.getByRole('img')).toHaveAccessibleName(/a precedent bonus added 3/)
  })

  it('marks a cap with its rule and says why a high score stays at refer', () => {
    const capped = { ...data, final: 90, cap_rule_ids: ['CM-FRD-01'] }
    render(<ScoreWaterfall data={capped} />)
    expect(screen.getByText('Capped at refer · CM-FRD-01')).toBeInTheDocument()
    expect(
      screen.getByText('The score is above 85, but a rule keeps this case at refer.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAccessibleName(/capped at refer by CM-FRD-01/)
  })

  it('keeps the note off a capped case below the approve line', () => {
    render(<ScoreWaterfall data={{ ...data, cap_rule_ids: ['CM-FRD-01'] }} />)
    expect(screen.getByText('Capped at refer · CM-FRD-01')).toBeInTheDocument()
    expect(screen.queryByText(/keeps this case at refer/)).toBeNull()
  })

  it('shows nothing for a stopped case', () => {
    const { container } = render(<ScoreWaterfall data={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
