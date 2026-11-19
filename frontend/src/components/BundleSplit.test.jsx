import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  upload: vi.fn(),
  blob: vi.fn(),
}))
vi.mock('../api/client', () => ({ api }))

import BundleSplit, { joinBack, pageRows, startAt } from './BundleSplit'

const seg = (a, b, t, c = 1) => ({ page_from: a, page_to: b, doc_type: t, confidence: c })
const PROPOSED = [seg(1, 1, 'pan_card'), seg(2, 4, 'bank_statement')]
const bundle = (segments = PROPOSED) => ({
  id: 'b1',
  name: 'all.pdf',
  pages: 4,
  segments,
  proposed: PROPOSED,
})

function setup(b = bundle(), props = {}) {
  const onChange = vi.fn()
  const onError = vi.fn()
  render(
    <BundleSplit
      caseId="c1"
      bundle={b}
      docTypes={['pan_card', 'aadhaar', 'bank_statement']}
      editable
      onChange={onChange}
      onError={onError}
      {...props}
    />,
  )
  return { onChange, onError, user: userEvent.setup() }
}
beforeEach(() => Object.values(api).forEach((f) => f.mockReset()))

describe('the split helpers', () => {
  it('lists every page with where a document starts', () => {
    expect(pageRows(PROPOSED, 4).map((r) => [r.page, r.start, r.type])).toEqual([
      [1, true, 'pan_card'],
      [2, true, 'bank_statement'],
      [3, false, 'bank_statement'],
      [4, false, 'bank_statement'],
    ])
  })
  it('a new document starts unrecognised, and joining back undoes it', () => {
    const cut = startAt(PROPOSED, 3)
    expect(cut.map((s) => [s.page_from, s.page_to, s.doc_type])).toEqual([
      [1, 1, 'pan_card'],
      [2, 2, 'bank_statement'],
      [3, 4, 'unknown'],
    ])
    expect(joinBack(cut, 3).map((s) => [s.page_from, s.page_to])).toEqual([
      [1, 1],
      [2, 4],
    ])
  })
})

describe('BundleSplit', () => {
  it('shows every page; page 1 always starts a document', () => {
    setup()
    expect(screen.getByLabelText('A new document starts on page 1')).toBeDisabled()
    expect(screen.getByLabelText('A new document starts on page 2')).toBeChecked()
    expect(screen.getByLabelText('A new document starts on page 3')).not.toBeChecked()
    expect(screen.getAllByText(/continues the document from page 2/)).toHaveLength(2)
  })

  it('ticking a page, unticking it and choosing a type save at once, without a dialog', async () => {
    const { user, onChange } = setup()
    api.put.mockResolvedValue({ bundles: [] })
    await user.click(screen.getByLabelText('A new document starts on page 3'))
    expect(api.put).toHaveBeenLastCalledWith('/cases/c1/documents/b1/split', {
      segments: [
        { page_from: 1, page_to: 1, doc_type: 'pan_card' },
        { page_from: 2, page_to: 2, doc_type: 'bank_statement' },
        { page_from: 3, page_to: 4, doc_type: 'unknown' },
      ],
    })
    await user.click(screen.getByLabelText('A new document starts on page 2'))
    expect(api.put).toHaveBeenLastCalledWith('/cases/c1/documents/b1/split', {
      segments: [{ page_from: 1, page_to: 4, doc_type: 'pan_card' }],
    })
    await user.selectOptions(
      screen.getByLabelText('What the document starting on page 1 is'),
      'aadhaar',
    )
    expect(api.put).toHaveBeenLastCalledWith('/cases/c1/documents/b1/split', {
      segments: [
        { page_from: 1, page_to: 1, doc_type: 'aadhaar' },
        { page_from: 2, page_to: 4, doc_type: 'bank_statement' },
      ],
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(onChange).toHaveBeenCalledTimes(3)
  })

  it('cutting the PDF needs the second click and Cancel cuts nothing', async () => {
    const { user, onChange } = setup()
    api.post.mockResolvedValue({
      inventory: { bundles: [] },
      results: [{ name: 'a', status: 'accepted' }],
    })
    await user.click(screen.getByRole('button', { name: 'Confirm the split' }))
    expect(api.post).not.toHaveBeenCalled() // the first click only opens the dialog
    expect(screen.getByText(/The original PDF stays untouched/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(api.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Confirm the split' }))
    await user.click(screen.getByRole('button', { name: 'Yes, split it' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/documents/b1/split/confirm', {
      second_click: true,
    })
    await vi.waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ bundles: [] }, [{ name: 'a', status: 'accepted' }]),
    )
  })

  it('offers the proposal back only after an edit', async () => {
    const edited = [seg(1, 4, 'bank_statement')]
    const first = setup()
    expect(screen.queryByRole('button', { name: 'Back to the proposed split' })).toBeNull()
    first.onChange.mockClear()
    document.body.innerHTML = ''
    const { user } = setup(bundle(edited))
    api.put.mockResolvedValue({})
    await user.click(screen.getByRole('button', { name: 'Back to the proposed split' }))
    expect(api.put).toHaveBeenCalledWith('/cases/c1/documents/b1/split', {
      segments: [
        { page_from: 1, page_to: 1, doc_type: 'pan_card' },
        { page_from: 2, page_to: 4, doc_type: 'bank_statement' },
      ],
    })
  })

  it('removing the PDF needs the second click', async () => {
    const { user, onChange } = setup()
    api.del.mockResolvedValue(null)
    api.get.mockResolvedValue({ bundles: [] })
    await user.click(screen.getByRole('button', { name: 'Remove this PDF' }))
    expect(api.del).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Yes, remove it' }))
    expect(api.del).toHaveBeenCalledWith('/cases/c1/documents/b1')
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith({ bundles: [] }))
  })

  it('shows a server refusal and changes nothing else', async () => {
    const { user, onError } = setup()
    api.put.mockRejectedValue(new Error('Every page must belong to a document'))
    await user.click(screen.getByLabelText('A new document starts on page 3'))
    await vi.waitFor(() =>
      expect(onError).toHaveBeenCalledWith('Every page must belong to a document'),
    )
  })

  it('is read-only when the case can no longer change', () => {
    setup(bundle(), { editable: false })
    expect(screen.getByLabelText('A new document starts on page 3')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Confirm the split' })).toBeNull()
  })
})
