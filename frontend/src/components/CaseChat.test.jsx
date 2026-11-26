import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CaseChat from './CaseChat'
import { api } from '../api/client'

vi.mock('../api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

const history = (over = {}) => ({
  report_version: 2,
  off: false,
  off_text: null,
  max_chars: 500,
  turns: [],
  ...over,
})
const answered = {
  id: 't1',
  question: 'Why did Income and FOIR lose points?',
  outcome: 'answered',
  text: null,
  note: null,
  report_version: 2,
  answer: {
    sentences: [
      {
        text: 'The FOIR earned 6 of 12 points.',
        citations: [
          { kind: 'rule', id: 'CM-INC-10' },
          { kind: 'clause', id: 'CM-INC-01' },
          { kind: 'field', id: 'payslip.employer' },
        ],
      },
    ],
    clauses: { 'CM-INC-01': { title: 'Fixed obligations', text: 'FOIR of 40 percent or under.' } },
    fields: { 'payslip.employer': 'Payslip · employer' },
  },
}
const box = () => screen.getByLabelText('Your question')

describe('CaseChat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockResolvedValue(history())
    api.post.mockResolvedValue(answered)
  })

  it('sends a question with Enter and shows the answer with its citation chips', async () => {
    const user = userEvent.setup()
    render(<CaseChat caseId="c1" reportVersion={2} />)
    await screen.findByText(/Chat cannot change the score or decide anything/)
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
    await user.type(box(), 'Why did Income and FOIR lose points?{Enter}')
    expect(api.post).toHaveBeenCalledWith('/cases/c1/chat', {
      question: 'Why did Income and FOIR lose points?',
    })
    expect(await screen.findByText(/The FOIR earned 6 of 12 points/)).toBeInTheDocument()
    expect(screen.getByText('CM-INC-10')).toBeInTheDocument()
    expect(screen.getByText('Payslip · employer')).toBeInTheDocument()
    expect(screen.getByText('Check the cited source before relying on an answer.')).toBeVisible()
    expect(screen.queryByRole('dialog')).toBeNull() // asking changes nothing: no second click
    expect(box()).toHaveValue('')
    expect(screen.queryByText(/About report version/)).toBeNull()

    const chip = screen.getByRole('button', { name: 'CM-INC-01' })
    await user.click(chip)
    expect(chip).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('FOIR of 40 percent or under.')).toBeInTheDocument()
    await user.click(chip)
    expect(screen.queryByText('FOIR of 40 percent or under.')).toBeNull()
  })

  it('makes a new line with Shift+Enter and counts the characters', async () => {
    const user = userEvent.setup()
    render(<CaseChat caseId="c1" />)
    await screen.findByText('0 of 500')
    await user.type(box(), 'one{Shift>}{Enter}{/Shift}two')
    expect(api.post).not.toHaveBeenCalled()
    expect(box()).toHaveValue('one\ntwo')
    expect(screen.getByText('7 of 500')).toBeInTheDocument()
    expect(box()).toHaveAttribute('maxlength', '500')
  })

  it('shows the fixed text, the hidden-numbers note and which report an answer was about', async () => {
    api.get.mockResolvedValue(
      history({
        turns: [
          {
            id: 't0',
            question: 'Is <PAN_1> right?',
            outcome: 'fixed_text',
            text: "I can't answer that from this case's documents and policy.",
            note: 'Personal numbers in your question were hidden before it was sent.',
            report_version: 1,
            answer: null,
          },
        ],
      }),
    )
    render(<CaseChat caseId="c1" />)
    expect(await screen.findByText(/I can't answer that/)).toBeInTheDocument()
    expect(screen.getByText(/Personal numbers in your question were hidden/)).toBeInTheDocument()
    expect(screen.getByText('About report version 1')).toBeInTheDocument()
  })

  it('says when chat is off and takes no question', async () => {
    api.get.mockResolvedValue(
      history({ off: true, off_text: 'Chat is off because the AI models are switched off.' }),
    )
    render(<CaseChat caseId="c1" />)
    expect(await screen.findByText(/^Chat is off/)).toHaveAttribute('role', 'status')
    expect(box()).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
  })

  it('keeps the question in the box and shows the limit message', async () => {
    api.post.mockRejectedValue(
      new Error('You have asked many questions in the last hour. Please try again a little later.'),
    )
    const user = userEvent.setup()
    render(<CaseChat caseId="c1" />)
    await screen.findByText('0 of 500')
    await user.type(box(), 'What is the FOIR?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('many questions in the last hour')
    expect(box()).toHaveValue('What is the FOIR?')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled())
  })
})
