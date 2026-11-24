import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BarChart from '../components/BarChart'
import { scoreRows } from './AuditorOverviewPage'

const buckets = (counts) =>
  counts.map((count, i) => ({ from: i * 10, to: i < 9 ? i * 10 + 9 : 100, count }))

describe('score distribution', () => {
  it('leaves out the empty ranges at both ends and says so', () => {
    const { rows, foot } = scoreRows(buckets([0, 0, 0, 0, 2, 0, 5, 9, 3, 0]))
    expect(rows.map((r) => r.label)).toEqual([
      '40 to 49',
      '50 to 59',
      '60 to 69',
      '70 to 79',
      '80 to 89',
    ])
    expect(rows[1].value).toBe(0) // a gap in the middle stays
    expect(foot).toBe('No case scored below 40 or above 89.')
  })

  it('keeps every range when the first and last have cases', () => {
    const { rows, foot } = scoreRows(buckets([1, 0, 0, 0, 0, 0, 0, 0, 0, 1]))
    expect(rows).toHaveLength(10)
    expect(foot).toBeNull()
  })

  it('names only the end that was left out', () => {
    expect(scoreRows(buckets([0, 0, 0, 0, 0, 0, 0, 4, 2, 1])).foot).toBe('No case scored below 70.')
    expect(scoreRows(buckets([3, 1, 0, 0, 0, 0, 0, 0, 0, 0])).foot).toBe('No case scored above 19.')
  })

  it('shows the empty message when no case has a score', () => {
    const { rows, foot } = scoreRows(buckets(Array(10).fill(0)))
    expect(rows).toEqual([])
    render(
      <BarChart
        title="Score distribution"
        rows={rows}
        foot={foot}
        empty="No case has a score yet."
      />,
    )
    expect(screen.getByText('No case has a score yet.')).toBeInTheDocument()
  })

  it('prints the line under the bars', () => {
    const { rows, foot } = scoreRows(buckets([0, 0, 0, 0, 0, 0, 2, 0, 0, 0]))
    const { container } = render(<BarChart title="Score distribution" rows={rows} foot={foot} />)
    expect(within(container.querySelector('figure')).getByText(foot)).toHaveClass('bar-foot')
    expect(container.querySelectorAll('li')).toHaveLength(1)
  })
})
