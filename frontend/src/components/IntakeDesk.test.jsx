import { render, screen, within } from '@testing-library/react'
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

import IntakeDesk from './IntakeDesk'

const file = (id, name, doc_type, role = 'primary') => ({
  id,
  name,
  doc_type,
  role,
  detected: doc_type,
  type_changed: false,
  person_changed: false,
  warnings: [],
  feeds: doc_type === 'pan_card' ? ['name', 'date of birth', 'PAN'] : [],
})
const inventory = (over = {}) => ({
  people: [
    {
      role: 'primary',
      employment: 'salaried',
      received: [file('f1', 'pan.pdf', 'pan_card')],
      missing: [{ type: 'payslip', types: ['payslip'], needed: 3, have: 1, essential: false }],
      extra: [],
      checklist: [],
    },
  ],
  unassigned: [],
  unrecognised: [],
  rejected: [],
  duplicates: [],
  conflicts: [],
  depends_on_employment: [],
  counts: {
    received: 1,
    missing: 1,
    extra: 0,
    unassigned: 0,
    unrecognised: 0,
    rejected: 0,
    duplicates: 0,
  },
  essential_missing: 0,
  complete: false,
  proceeded: false,
  ...over,
})

function setup(inv = inventory(), props = {}) {
  const setInventory = vi.fn()
  const onContinue = vi.fn()
  render(
    <IntakeDesk
      caseId="c1"
      inventory={inv}
      setInventory={setInventory}
      docTypes={['pan_card', 'aadhaar', 'payslip', 'other']}
      editable
      recipient="****@example.test"
      onContinue={onContinue}
      {...props}
    />,
  )
  return { setInventory, onContinue, user: userEvent.setup() }
}
beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset())
})

describe('IntakeDesk: second click only where the plan says', () => {
  it('Proceed anyway needs the second click and Cancel records nothing', async () => {
    const { user, setInventory } = setup()
    api.post.mockResolvedValue(inventory({ proceeded: true }))
    await user.click(screen.getByRole('button', { name: 'Proceed anyway' }))
    expect(api.post).not.toHaveBeenCalled() // the first click only opens the dialog
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(api.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Proceed anyway' }))
    await user.click(screen.getByRole('button', { name: 'Yes, proceed anyway' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/intake/proceed', { second_click: true })
    await vi.waitFor(() => expect(setInventory).toHaveBeenCalled())
  })

  it('Continue waits for a second click while the applicant has not pressed Send', async () => {
    const full = inventory({ complete: true, waiting_for_applicant: true })
    full.people[0].missing = []
    full.counts.missing = 0
    const { user, onContinue } = setup(full)
    expect(screen.getByText(/has not pressed Send to the bank yet/)).toBeInTheDocument()
    api.post.mockResolvedValue({ ...full, waiting_for_applicant: false })
    await user.click(screen.getByRole('button', { name: 'Continue to the application form' }))
    expect(onContinue).not.toHaveBeenCalled() // the first click only opens the dialog
    expect(api.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(api.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Continue to the application form' }))
    await user.click(screen.getByRole('button', { name: 'Yes, continue anyway' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/intake/continue-unsent', {
      second_click: true,
    })
    await vi.waitFor(() => expect(onContinue).toHaveBeenCalled())
  })

  it('after asking for more, the note says the new files are awaited, not a first Send', () => {
    const full = inventory({ complete: true, waiting_for_applicant: true, asked_for_more: true })
    full.people[0].missing = []
    full.counts.missing = 0
    setup(full)
    expect(
      screen.getByText(/You asked the applicant for more files and they have not sent them yet/),
    ).toBeInTheDocument()
    expect(screen.queryByText(/has not pressed Send/)).not.toBeInTheDocument()
  })

  it('Continue goes straight on when no link is waiting for the applicant', async () => {
    const full = inventory({ complete: true, waiting_for_applicant: false })
    full.people[0].missing = []
    full.counts.missing = 0
    const { user, onContinue } = setup(full)
    expect(screen.queryByText(/has not pressed Send/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Continue to the application form' }))
    expect(onContinue).toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('Proceed anyway is off while the identity papers are missing', () => {
    setup(
      inventory({
        essential_missing: 2,
        people: [
          {
            ...inventory().people[0],
            missing: [{ type: 'aadhaar', types: ['aadhaar'], needed: 1, have: 0, essential: true }],
          },
        ],
      }),
    )
    expect(screen.getByRole('button', { name: 'Proceed anyway' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Continue to the application form' })).toBeDisabled()
  })

  it('Ask the applicant needs the second click, then shows the address once with a copy button', async () => {
    const { user } = setup()
    api.post.mockResolvedValue({ link_id: 'l1', token: 'tok', path: '/u#tok', new_link: true })
    await user.click(screen.getByRole('button', { name: 'Ask the applicant' }))
    expect(api.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Create the link' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/ask-applicant', { second_click: true })
    const box = await screen.findByLabelText('Upload link address')
    expect(box.value).toMatch(/\/u#tok$/)
    expect(screen.getByRole('button', { name: 'Copy the link' })).toBeInTheDocument() // no dialog to copy
  })

  it('sending the link as a message is its own second click and keeps the token out of the draft', async () => {
    const { user } = setup()
    api.post.mockImplementation(async (path) => {
      if (path.endsWith('/ask-applicant'))
        return {
          link_id: 'l1',
          token: 'tok-abcdefghijklmnopqrstu',
          path: '/u#tok-abcdefghijklmnopqrstu',
          new_link: true,
        }
      if (path.endsWith('/messages'))
        return {
          id: 'm1',
          status: 'draft',
          text: 'Dear customer.\n\nUpload link: [your secure upload link]',
        }
      return { status: 'sent' }
    })
    await user.click(screen.getByRole('button', { name: 'Ask the applicant' }))
    await user.click(screen.getByRole('button', { name: 'Create the link' }))
    await user.click(await screen.findByRole('button', { name: 'Send it as a message' }))
    await user.type(screen.getByLabelText('Customer email'), 'customer@example.test')
    await user.click(screen.getByRole('button', { name: 'Prepare the message' }))
    expect(api.post).toHaveBeenCalledWith(
      '/cases/c1/messages',
      expect.objectContaining({
        template: 'upload_link',
        link_id: 'l1',
        recipient_email: 'customer@example.test',
      }),
    )
    const sendCalls = () => api.post.mock.calls.filter(([p]) => p.endsWith('/send'))
    expect(await screen.findByText(/exactly what the customer will receive/)).toBeInTheDocument()
    expect(sendCalls()).toHaveLength(0) // preparing sends nothing
    await user.click(screen.getByRole('button', { name: 'Send to the customer' }))
    expect(sendCalls()).toHaveLength(1)
    expect(sendCalls()[0][1]).toEqual({
      second_click: true,
      link_token: 'tok-abcdefghijklmnopqrstu',
    })
  })
})

describe('IntakeDesk: a PDF with several documents', () => {
  const waiting = {
    id: 'b1',
    name: 'all.pdf',
    pages: 3,
    segments: [{ page_from: 1, page_to: 3, doc_type: 'pan_card' }],
    proposed: [{ page_from: 1, page_to: 3, doc_type: 'pan_card' }],
  }

  it('cannot continue while a PDF waits for its split, and says why', () => {
    setup(
      inventory({
        bundles: [waiting],
        counts: { ...inventory().counts, bundles: 1 },
        complete: false,
        proceeded: true,
        people: [{ ...inventory().people[0], missing: [] }],
      }),
    )
    expect(screen.getByLabelText('Split all.pdf')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue to the application form' })).toBeDisabled()
    expect(screen.getByText(/waiting for you to confirm how it is split/)).toBeInTheDocument()
  })

  it('a desk with only a waiting PDF still shows the split', () => {
    setup(
      inventory({
        bundles: [waiting],
        people: [{ ...inventory().people[0], received: [], missing: [] }],
        counts: { ...inventory().counts, received: 0, bundles: 1 },
      }),
    )
    expect(screen.getByLabelText('Split all.pdf')).toBeInTheDocument()
  })
})

describe('IntakeDesk: no dialog for the easy things', () => {
  it('changing a file type or its person saves at once', async () => {
    const { user, setInventory } = setup()
    api.patch.mockResolvedValue(inventory())
    await user.selectOptions(screen.getByLabelText('Type of pan.pdf'), 'aadhaar')
    expect(api.patch).toHaveBeenCalledWith('/cases/c1/documents/f1', { doc_type: 'aadhaar' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await vi.waitFor(() => expect(setInventory).toHaveBeenCalled())
    await user.selectOptions(screen.getByLabelText('Person for pan.pdf'), 'none')
    expect(api.patch).toHaveBeenLastCalledWith('/cases/c1/documents/f1', { role: 'none' })
  })

  it('stating the employment type saves at once', async () => {
    const { user } = setup()
    api.put.mockResolvedValue(inventory())
    await user.selectOptions(
      screen.getByLabelText('Employment type of the applicant'),
      'self_employed',
    )
    expect(api.put).toHaveBeenCalledWith('/cases/c1/intake', {
      employment: { primary: 'self_employed' },
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('downloading the zip needs no confirmation', async () => {
    const { user } = setup()
    api.blob.mockResolvedValue(new Blob(['z']))
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    await user.click(screen.getByRole('button', { name: 'Download all files (zip)' }))
    expect(api.blob).toHaveBeenCalledWith('/cases/c1/files.zip')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('IntakeDesk: the inventory', () => {
  it('lists each bucket with its reason', () => {
    setup(
      inventory({
        unassigned: [file('u1', 'mystery.pdf', 'payslip', null)],
        unrecognised: [file('u2', 'back.jpg', 'unknown', null)],
        rejected: [
          {
            id: 'r1',
            name: 'blur.jpg',
            code: 'blurry',
            message: 'The image is too blurry to read.',
          },
        ],
        duplicates: [{ id: 'd1', name: 'again.pdf', of: 'pan.pdf', kind: 'exact' }],
        counts: {
          received: 1,
          missing: 1,
          extra: 0,
          unassigned: 1,
          unrecognised: 1,
          rejected: 1,
          duplicates: 1,
        },
      }),
    )
    const box = screen.getByTestId('inventory')
    expect(within(box).getByText('Whose is it?')).toBeInTheDocument()
    expect(within(box).getAllByText('Not recognised').length).toBeGreaterThan(0)
    expect(within(box).getByText(/too blurry/)).toBeInTheDocument()
    expect(within(box).getByText(/repeats/, { selector: 'li' })).toBeInTheDocument()
    expect(within(box).getByText('Payslips', { selector: 'li' })).toBeInTheDocument()
  })

  it('holds back employment-dependent items instead of calling them missing', () => {
    setup(
      inventory({
        people: [{ ...inventory().people[0], employment: null, missing: [] }],
        depends_on_employment: [
          { role: 'primary', if_employment: 'salaried', type: 'payslip', needed: 3, have: 0 },
        ],
      }),
    )
    expect(screen.getByText('Depends on employment type')).toBeInTheDocument()
    expect(screen.getByText(/if salaried: Payslips/)).toBeInTheDocument()
  })

  it('once files are in, the upload box is a slim bar with the extra way to add a file under it', () => {
    setup(inventory(), { children: <p>Add one file and label it yourself</p> })
    const box = document.querySelector('.dropzone')
    expect(box).toHaveClass('dropzone-compact')
    expect(box).toHaveTextContent('Add more')
    const extra = screen.getByText('Add one file and label it yourself')
    expect(box.compareDocumentPosition(extra) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(extra.compareDocumentPosition(screen.getByTestId('inventory'))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
  })

  it('an empty desk keeps the big drop box', () => {
    const empty = inventory({
      people: [{ ...inventory().people[0], received: [] }],
      counts: { ...inventory().counts, received: 0 },
    })
    setup(empty)
    expect(document.querySelector('.dropzone')).not.toHaveClass('dropzone-compact')
  })

  it('the reason a button is off sits above the buttons, in the next-step bar', () => {
    setup(inventory({ essential_missing: 1 }))
    const bar = document.querySelector('.desk-next')
    const note = within(bar).getByText(/needed for every person/)
    const buttons = bar.querySelector('.desk-actions')
    expect(note.compareDocumentPosition(buttons)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('says why Continue is off when papers are missing or the employment type is not stated', () => {
    setup(
      inventory({
        depends_on_employment: [
          { role: 'primary', if_employment: 'salaried', type: 'payslip', needed: 3 },
        ],
      }),
    )
    expect(screen.getByRole('button', { name: 'Continue to the application form' })).toBeDisabled()
    const bar = document.querySelector('.desk-next')
    expect(bar).toHaveTextContent('State the employment type above')
    expect(bar).toHaveTextContent('Some documents are still missing')
  })

  it('the admin view has no upload box and no actions, only the zip', () => {
    setup(inventory(), { editable: false, onContinue: undefined })
    expect(screen.queryByText(/Choose files or a zip/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ask the applicant' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Proceed anyway' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Type of pan.pdf')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Download all files (zip)' })).toBeInTheDocument()
  })
})
