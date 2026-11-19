import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { readFileSync } from 'node:fs'
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

  it('shows an uploading panel with the file count while the files are sent and read', async () => {
    let finish
    const upload = vi.fn(() => new Promise((resolve) => (finish = resolve)))
    render(<BulkUpload upload={upload} />)
    const files = [new File(['x'], 'a.pdf'), new File(['y'], 'b.pdf')]
    await userEvent.setup().upload(document.getElementById('bulk-files'), files)
    expect(await screen.findByTestId('bulk-working')).toHaveTextContent('Uploading 2 files')
    expect(screen.queryByText('Choose files or a zip')).not.toBeInTheDocument()
    finish([{ name: 'a.pdf', status: 'accepted', message: '' }])
    expect(await screen.findByText('1 received')).toBeInTheDocument()
    expect(screen.queryByTestId('bulk-working')).not.toBeInTheDocument()
    expect(screen.getByText('Choose files or a zip')).toBeInTheDocument()
  })

  it('pops a not-accepted file up at the top of the screen as well as listing it', async () => {
    const upload = vi.fn().mockResolvedValue([
      {
        name: 'index.json',
        status: 'rejected',
        message: 'Only PDF, JPG and PNG files are accepted.',
      },
    ])
    render(<BulkUpload upload={upload} />)
    await userEvent
      .setup()
      .upload(document.getElementById('bulk-folder'), new File(['x'], 'index.json'))
    const toast = (await screen.findByText('1 file was not accepted')).closest('.toast')
    expect(toast).toHaveTextContent('index.json: Only PDF, JPG and PNG files are accepted.')
    expect(screen.getByTestId('bulk-results')).toHaveTextContent('Not accepted')
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

  it('hides the camera on a computer and the folder on a phone, above the shared .btn rule', () => {
    // the shared .btn rule (display: inline-flex) loads after this file, so a plain
    // .bulk-camera { display: none } lost and a laptop showed "Take a photo"
    const css = readFileSync('src/components/BulkUpload.css', 'utf8')
    expect(css).toMatch(/\.btn\.bulk-camera\s*\{\s*display:\s*none/)
    const phone = css.slice(css.indexOf('@media (hover: none) and (pointer: coarse)'))
    expect(phone).toMatch(/\.btn\.bulk-camera\s*\{\s*display:\s*inline-flex/)
    expect(phone).toMatch(/\.btn\.bulk-folder\s*\{\s*display:\s*none/)
  })

  it('offers the camera only on the applicant page', () => {
    const { unmount } = render(<BulkUpload upload={vi.fn()} />)
    expect(screen.queryByText('Take a photo')).not.toBeInTheDocument()
    unmount()
    render(<BulkUpload upload={vi.fn()} camera />)
    expect(screen.getByText('Take a photo')).toBeInTheDocument()
  })
})
