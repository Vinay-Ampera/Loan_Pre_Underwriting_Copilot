import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import CustomerContact from './CustomerContact'

const META = {
  subject: 'Pramaan: please contact your loan officer',
  footer: 'Pramaan staff will never ask you for your OTP, PIN or password.',
  max_body: 600,
  contact: ['Officer: Asha'],
  phone_set: true,
  templates: [{ code: 'general_contact', label: 'Please get in touch', body: 'Dear customer.' }],
}
const msg = (id, status) => ({
  id,
  status,
  template: 'general_contact',
  template_label: 'Please get in touch',
  body: 'Saved text',
  recipient: '****@example.test',
  case_ref_included: false,
  created_at: '2026-11-03T10:00:00Z',
  sent_at: null,
})

function setup(list) {
  api.get
    .mockReset()
    .mockImplementation(async (path) => (path === '/messages/templates' ? META : list))
  api.del.mockReset().mockResolvedValue(null)
  render(
    <MemoryRouter>
      <CustomerContact caseId="c1" recipient="****@example.test" />
    </MemoryRouter>,
  )
  return userEvent.setup()
}
beforeEach(() => vi.clearAllMocks())

describe('CustomerContact', () => {
  it('opens the editor straight away when there is no unsent draft', async () => {
    const user = setup([{ ...msg('a', 'sent') }])
    await screen.findByText('Recent messages')
    await user.click(screen.getByRole('button', { name: 'Write a message' }))
    expect(await screen.findByLabelText('Template')).toBeInTheDocument()
    expect(screen.queryByText('You have an unsent draft')).toBeNull()
  })

  it('asks first when a draft exists and continues it with its saved text', async () => {
    const user = setup([msg('d1', 'draft')])
    await screen.findByText('Recent messages')
    await user.click(screen.getByRole('button', { name: 'Write a message' }))
    expect(await screen.findByText('You have an unsent draft')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Continue the draft' }))
    expect(await screen.findByLabelText('Message')).toHaveValue('Saved text')
  })

  it('deletes the old draft only from the explicit delete button, then opens a new message', async () => {
    const user = setup([msg('d1', 'draft')])
    await screen.findByText('Recent messages')
    await user.click(screen.getByRole('button', { name: 'Write a message' }))
    expect(api.del).not.toHaveBeenCalled()
    await user.click(await screen.findByRole('button', { name: 'Delete the draft and start new' }))
    expect(api.del).toHaveBeenCalledWith('/messages/d1')
    expect(await screen.findByLabelText('Template')).toBeInTheDocument()
  })

  it('starting new keeps the old draft', async () => {
    const user = setup([msg('d1', 'draft')])
    await screen.findByText('Recent messages')
    await user.click(screen.getByRole('button', { name: 'Write a message' }))
    await user.click(await screen.findByRole('button', { name: 'Start a new message' }))
    expect(await screen.findByLabelText('Message')).toHaveValue('Dear customer.')
    expect(api.del).not.toHaveBeenCalled()
  })
})
