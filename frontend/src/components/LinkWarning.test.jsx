import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import LinkWarning from './LinkWarning'

const base = { id: 'c1', case_no: 'CASE-2026-0007', status: 'draft', applicant_sent: null }
const linkOf = (state) => ({ link: { id: 'l1', state, expires_at: '2026-11-10T10:00:00Z' } })

function show(c, link) {
  api.get.mockReset().mockResolvedValue(link)
  render(
    <MemoryRouter>
      <LinkWarning c={{ ...base, ...c }} />
    </MemoryRouter>,
  )
}
beforeEach(() => api.get.mockReset())

describe('LinkWarning', () => {
  it('warns about an expired link while the applicant has not sent, with a button to Upload links', async () => {
    show({}, linkOf('expired'))
    expect(await screen.findByText(/has expired/)).toBeInTheDocument()
    expect(screen.getByText(/Set days/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open Upload links' })).toHaveAttribute(
      'href',
      '/links?case=CASE-2026-0007',
    )
  })

  it('says a switched-off link cannot be reopened and points to Ask the applicant', async () => {
    show({}, linkOf('disabled'))
    expect(await screen.findByText(/been switched off/)).toBeInTheDocument()
    expect(screen.getByText(/Use Ask the applicant/)).toBeInTheDocument()
  })

  it('warns after the officer asked for more and the link has ended', async () => {
    show(
      { applicant_sent: { at: '2026-11-18' }, more_requested: { at: '2026-11-19' } },
      linkOf('expired'),
    )
    expect(await screen.findByText(/asked for more documents/)).toBeInTheDocument()
  })

  it('stays quiet for an open link, a finished submission, or a case with no link', async () => {
    show({}, linkOf('active'))
    await vi.waitFor(() => expect(api.get).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    // the applicant has sent and nothing more was asked: no call at all
    show({ applicant_sent: { at: '2026-11-18' } }, linkOf('expired'))
    expect(api.get).not.toHaveBeenCalled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    show({}, { link: null })
    await vi.waitFor(() => expect(api.get).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('stays quiet once the case is running or decided', () => {
    show({ status: 'running' }, linkOf('expired'))
    expect(api.get).not.toHaveBeenCalled()
  })
})
