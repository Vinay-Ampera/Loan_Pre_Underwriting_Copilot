import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import MessageDialog from './MessageDialog'

const META = {
  subject: 'Pramaan: please contact your loan officer',
  footer: 'Pramaan staff will never ask you for your OTP, PIN or password.',
  max_body: 600,
  contact: ['Officer: Asha', 'Email: asha@example.test'],
  phone_set: true,
  templates: [
    { code: 'general_contact', label: 'Please get in touch', body: 'Dear customer, please call.' },
    { code: 'blank', label: 'Blank (write your own)', body: '' },
  ],
}
const drafted = (over = {}) => ({
  id: 'm1',
  status: 'draft',
  recipient: '****@example.test',
  subject: META.subject,
  text: 'Dear customer, please call.\n\nOfficer: Asha\n\n' + META.footer,
  ...over,
})

beforeEach(() => {
  api.get.mockReset().mockResolvedValue(META)
  api.post.mockReset()
  api.put.mockReset()
})

const open = async () => {
  const onDone = vi.fn()
  render(
    <MessageDialog caseId="c1" recipient="****@example.test" onClose={vi.fn()} onDone={onDone} />,
  )
  await screen.findByLabelText('Template')
  return { onDone, user: userEvent.setup() }
}

describe('MessageDialog', () => {
  it('shows the locked footer and contact lines and fills the template text', async () => {
    await open()
    expect(screen.getByLabelText('Message')).toHaveValue('Dear customer, please call.')
    expect(screen.getByText(META.footer)).toBeInTheDocument()
    expect(screen.getByText('Officer: Asha')).toBeInTheDocument()
    expect(screen.getByLabelText('Subject')).toBeDisabled()
  })

  it('sends only from the second step: Review saves a draft, Yes send sends', async () => {
    const { user, onDone } = await open()
    api.post.mockResolvedValueOnce(drafted()).mockResolvedValueOnce({ status: 'sent' })
    await user.click(screen.getByRole('button', { name: 'Review' }))
    expect(api.post).toHaveBeenCalledTimes(1) // the draft only, nothing sent yet
    expect(api.post.mock.calls[0][0]).toBe('/cases/c1/messages')
    expect(await screen.findByTestId('final-text')).toHaveTextContent(META.footer)
    await user.click(screen.getByRole('button', { name: 'Yes, send' }))
    expect(api.post).toHaveBeenLastCalledWith('/messages/m1/send', { second_click: true })
    expect(await screen.findByText('Message sent')).toBeInTheDocument()
    expect(onDone).toHaveBeenCalled()
  })

  it('shows why a message is blocked and stays on the edit step', async () => {
    const { user } = await open()
    api.post.mockResolvedValueOnce(
      drafted({
        status: 'blocked',
        block_reason: 'Contains a PAN; Mentions a score, a band or a rule',
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Review' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Contains a PAN')
    expect(alert).toHaveTextContent('Mentions a score')
    expect(screen.queryByRole('button', { name: 'Yes, send' })).toBeNull()
  })

  it('shows a failed send and keeps the dialog open for another try', async () => {
    const { user } = await open()
    api.post
      .mockResolvedValueOnce(drafted())
      .mockRejectedValueOnce(new Error('The message could not be sent. It is saved as failed.'))
    await user.click(screen.getByRole('button', { name: 'Review' }))
    await user.click(await screen.findByRole('button', { name: 'Yes, send' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('saved as failed'))
    expect(screen.getByRole('button', { name: 'Yes, send' })).toBeEnabled()
  })

  it('asks for an email when the case has none', async () => {
    render(<MessageDialog caseId="c1" recipient={null} onClose={vi.fn()} />)
    const user = userEvent.setup()
    await screen.findByLabelText('Template')
    expect(screen.getByRole('button', { name: 'Review' })).toBeDisabled()
    await user.type(screen.getByLabelText('To'), 'typed@example.test')
    expect(screen.getByRole('button', { name: 'Review' })).toBeEnabled()
  })

  it('reviews again after backing out: the saved draft is updated with put, not created twice', async () => {
    const { user } = await open()
    api.post.mockResolvedValueOnce(drafted())
    api.put.mockResolvedValueOnce(drafted({ text: 'Updated' }))
    await user.click(screen.getByRole('button', { name: 'Review' }))
    await user.click(await screen.findByRole('button', { name: 'Back to edit' }))
    await user.click(screen.getByRole('button', { name: 'Review' }))
    expect(api.put).toHaveBeenCalledWith(
      '/messages/m1',
      expect.objectContaining({ body: expect.any(String) }),
    )
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(await screen.findByTestId('final-text')).toHaveTextContent('Updated')
  })

  it('tells the caller about a draft left behind when the dialog is closed', async () => {
    const { user, onDone } = await open()
    api.post.mockResolvedValueOnce(drafted())
    await user.click(screen.getByRole('button', { name: 'Review' }))
    await user.click(await screen.findByRole('button', { name: 'Back to edit' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onDone).toHaveBeenCalled()
  })
})
