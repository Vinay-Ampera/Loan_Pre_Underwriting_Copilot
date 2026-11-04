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

  it('the admin view has no upload box and no actions, only the zip', () => {
    setup(inventory(), { editable: false, onContinue: undefined })
    expect(screen.queryByText(/Choose files or a zip/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ask the applicant' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Proceed anyway' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Type of pan.pdf')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Download all files (zip)' })).toBeInTheDocument()
  })
})
