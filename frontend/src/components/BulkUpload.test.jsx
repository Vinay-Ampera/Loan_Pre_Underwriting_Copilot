import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import BulkUpload, { summarise } from './BulkUpload'

describe('BulkUpload', () => {
  it('summarises what happened to the files', () => {
    expect(
      summarise([
        { status: 'accepted' },
        { status: 'warning' },
        { status: 'rejected' },
        { status: 'ignored' },
        { status: 'ignored' },
      ]),
    ).toBe('2 received · 1 not accepted · 2 repeats ignored')
  })

  it('sends a folder file under its path and lists each result', async () => {
    const upload = vi.fn().mockResolvedValue([
      { name: 'a.pdf', status: 'accepted', message: 'Accepted.' },
      { name: 'b.jpg', status: 'rejected', message: 'Too blurry.' },
    ])
    render(<BulkUpload upload={upload} />)
    const input = document.getElementById('bulk-folder')
    const f = new File(['x'], 'a.pdf', { type: 'application/pdf' })
    Object.defineProperty(f, 'webkitRelativePath', { value: 'case/primary/a.pdf' })
    await userEvent.setup().upload(input, f)
    const form = upload.mock.calls[0][0]
    expect(form.getAll('files')[0].name).toBe('case/primary/a.pdf')
    expect(await screen.findByText('1 received · 1 not accepted')).toBeInTheDocument()
    expect(screen.getByText('Too blurry.')).toBeInTheDocument()
  })

  it('shows the refusal of an unsafe archive without hiding earlier results', async () => {
    const upload = vi
      .fn()
      .mockRejectedValue(new Error('The zip contains a path outside its folder and was refused.'))
    render(<BulkUpload upload={upload} />)
    await userEvent.setup().upload(document.getElementById('bulk-files'), new File(['x'], 'a.zip'))
    expect(await screen.findByRole('alert')).toHaveTextContent('refused')
  })

  it('does nothing while disabled', async () => {
    const upload = vi.fn()
    render(<BulkUpload upload={upload} disabled />)
    expect(document.getElementById('bulk-files')).toBeDisabled()
    expect(upload).not.toHaveBeenCalled()
  })
})
