import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import AdminAiControlPage, { diffLines } from './AdminAiControlPage'

const role = (primary, fallbacks = []) => ({ primary, fallbacks, temperature: 0, max_tokens: null })
const ROLES = ['supervisor', 'extraction', 'decision', 'kyc', 'risk', 'policy', 'judge']
const config = () => ({
  roles: Object.fromEntries(
    ROLES.map((r) => [r, role(r === 'judge' ? 'flash_lite' : 'flash', ['groq'])]),
  ),
  router: { num_retries: 1, timeout: 90, cooldown_time: 30 },
  llm_enabled: true,
})
const overview = (over = {}) => ({
  version: 0,
  config: config(),
  default: config(),
  roles: ROLES.map((r) => ({ role: r, label: `${r} step` })),
  limits: {
    temperature: [0, 1],
    max_tokens: [200, 8000],
    num_retries: [0, 3],
    timeout: [10, 300],
    cooldown_time: [5, 300],
  },
  max_fallbacks: 3,
  providers: [
    { id: 'flash', model: 'gemini/flash', key_env: 'GEMINI_API_KEY', key_set: true },
    { id: 'flash_lite', model: 'gemini/flash-lite', key_env: 'GEMINI_API_KEY', key_set: true },
    { id: 'groq', model: 'groq/gpt-oss', key_env: 'GROQ_API_KEY', key_set: true },
    { id: 'nim', model: 'nvidia/nemotron', key_env: 'NVIDIA_API_KEY', key_set: false },
  ],
  prompts: ['kyc', 'risk'].map((name) => ({ name, version: 1, edited: false, has_draft: false })),
  ...over,
})
const prompt = (over = {}) => ({
  name: 'kyc',
  role: 'KYC: explains identity checks',
  version: 1,
  edited: false,
  editable: 'You explain KYC results.',
  file_editable: 'You explain KYC results.',
  file_version: 1,
  locked: 'Rules (fixed by the system, not editable):\n1. Reply with JSON only.',
  max_chars: 4000,
  versions: [],
  draft: null,
  ...over,
})

let current
beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset())
  current = { overview: overview(), prompt: prompt() }
  api.get.mockImplementation(async (path) => {
    if (path === '/admin/ai') return current.overview
    if (path === '/admin/ai/config/history') return []
    if (path.startsWith('/admin/ai/prompts/')) return current.prompt
    throw new Error(`unexpected ${path}`)
  })
})

describe('AI control: models and settings', () => {
  it('saves a model change only after a written reason and the confirm click', async () => {
    const user = userEvent.setup()
    render(<AdminAiControlPage />)
    await user.selectOptions(await screen.findByLabelText('First choice for kyc'), 'groq')
    expect(screen.getByText('You have changes that are not saved.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Review and save' }))
    expect(api.put).not.toHaveBeenCalled() // the first click only opens the dialog
    const confirm = screen.getByRole('button', { name: 'Yes, save' })
    expect(confirm).toBeDisabled() // no reason yet
    await user.type(screen.getByLabelText('Why are you making this change?'), 'too short')
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('Why are you making this change?'), ' and now longer')
    api.put.mockImplementation(async (_path, sent) => {
      current.overview = overview({ version: 1, config: sent.config }) // the server now holds it
      return { version: 1, changes: ['kyc'] }
    })
    await user.click(confirm)
    expect(api.put).toHaveBeenCalledTimes(1)
    const [path, body] = api.put.mock.calls[0]
    expect(path).toBe('/admin/ai/config')
    expect(body.second_click).toBe(true)
    expect(body.reason).toMatch(/and now longer/)
    expect(body.config.roles.kyc.primary).toBe('groq')
    expect(await screen.findByText(/Saved as version 1/)).toBeInTheDocument()
  })

  it('Cancel in the dialog sends nothing and Discard puts the saved values back', async () => {
    const user = userEvent.setup()
    render(<AdminAiControlPage />)
    await user.selectOptions(await screen.findByLabelText('First choice for risk'), 'groq')
    await user.click(screen.getByRole('button', { name: 'Review and save' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(api.put).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Discard' }))
    expect(screen.getByLabelText('First choice for risk')).toHaveValue('flash')
    expect(screen.queryByText('You have changes that are not saved.')).not.toBeInTheDocument()
  })

  it('marks a model with no key, and shows the refusal from the server', async () => {
    const user = userEvent.setup()
    render(<AdminAiControlPage />)
    const select = await screen.findByLabelText('First choice for kyc')
    expect(
      within(select).getByRole('option', { name: 'nvidia/nemotron (no key)' }),
    ).toBeInTheDocument()
    await user.selectOptions(select, 'nim')
    await user.click(screen.getByRole('button', { name: 'Review and save' }))
    await user.type(
      screen.getByLabelText('Why are you making this change?'),
      'trying the NVIDIA model',
    )
    api.put.mockRejectedValue(
      new Error('kyc: the key for nim (NVIDIA_API_KEY) is not set in .env.'),
    )
    await user.click(screen.getByRole('button', { name: 'Yes, save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('NVIDIA_API_KEY')
  })

  it('adds and removes a fallback and edits the retry numbers', async () => {
    const user = userEvent.setup()
    render(<AdminAiControlPage />)
    await user.click(
      (await screen.findAllByRole('button', { name: 'Add a fallback' }))[0], // supervisor
    )
    expect(screen.getByLabelText('Fallback 2 for supervisor')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Remove fallback 2 for supervisor' }))
    expect(screen.queryByLabelText('Fallback 2 for supervisor')).not.toBeInTheDocument()
    await user.clear(screen.getByLabelText('Seconds to wait for an answer'))
    await user.type(screen.getByLabelText('Seconds to wait for an answer'), '120')
    expect(screen.getByLabelText('Seconds to wait for an answer')).toHaveValue(120)
  })

  it('the settings tab edits the model switch, temperature and length limit', async () => {
    const user = userEvent.setup()
    render(<AdminAiControlPage />)
    await user.click(await screen.findByRole('tab', { name: /Settings/ }))
    await user.click(screen.getByRole('checkbox'))
    await user.clear(screen.getByLabelText('Length limit for kyc'))
    await user.type(screen.getByLabelText('Length limit for kyc'), '900')
    await user.click(screen.getByRole('button', { name: 'Review and save' }))
    await user.type(screen.getByLabelText('Why are you making this change?'), 'Pausing the models')
    api.put.mockResolvedValue({ version: 2, changes: [] })
    await user.click(screen.getByRole('button', { name: 'Yes, save' }))
    const body = api.put.mock.calls[0][1]
    expect(body.config.llm_enabled).toBe(false)
    expect(body.config.roles.kyc.max_tokens).toBe(900)
  })
})

describe('AI control: keys', () => {
  it('shows only whether a key is set, and tests a model on request', async () => {
    const user = userEvent.setup()
    render(<AdminAiControlPage />)
    await user.click(await screen.findByRole('tab', { name: 'Keys' }))
    expect(screen.getAllByText('GEMINI_API_KEY').length).toBeGreaterThan(0)
    expect(screen.getByText('Key is missing')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Test nvidia/nemotron' })).toBeDisabled()
    api.post.mockResolvedValue({ provider: 'groq', ok: true, error: '', latency_ms: 321 })
    await user.click(screen.getByRole('button', { name: 'Test groq/gpt-oss' }))
    expect(api.post).toHaveBeenCalledWith('/admin/ai/test-model', { provider: 'groq' })
    expect(await screen.findByText('Works (321 ms)')).toBeInTheDocument()
    api.post.mockResolvedValue({
      provider: 'flash',
      ok: false,
      error: 'AuthenticationError',
      latency_ms: 4,
    })
    await user.click(screen.getByRole('button', { name: 'Test gemini/flash' }))
    expect(await screen.findByText('Failed: AuthenticationError')).toBeInTheDocument()
  })
})

describe('AI control: prompts', () => {
  async function openKyc(user) {
    render(<AdminAiControlPage />)
    await user.click(await screen.findByRole('tab', { name: 'Prompts' }))
    return screen.findByLabelText('Editable instructions for kyc')
  }

  it('shows the locked rules apart from the editable text, and cannot publish an untested draft', async () => {
    const user = userEvent.setup()
    const box = await openKyc(user)
    expect(box).toHaveValue('You explain KYC results.')
    const locked = screen.getByRole('region', { name: 'Locked rules' })
    expect(within(locked).getByText(/Reply with JSON only/)).toBeInTheDocument()
    expect(within(locked).queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Publish' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled() // nothing changed
    await user.type(box, ' Keep it short.')
    expect(screen.getByRole('region', { name: 'What changes' })).toHaveTextContent(
      '+ You explain KYC results. Keep it short.',
    )
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Test the draft' })).toBeDisabled() // not saved yet
    expect(screen.getByRole('button', { name: 'Publish' })).toBeDisabled()
  })

  it('saves a draft, tests it, then publishes only after a reason and the second click', async () => {
    const user = userEvent.setup()
    const box = await openKyc(user)
    await user.type(box, ' Keep it short.')
    api.put.mockImplementation(async () => {
      current.prompt = prompt({
        draft: { body: 'You explain KYC results. Keep it short.', tested: false },
      })
      return current.prompt
    })
    await user.click(screen.getByRole('button', { name: 'Save draft' }))
    expect(api.put).toHaveBeenCalledWith('/admin/ai/prompts/kyc/draft', {
      body: 'You explain KYC results. Keep it short.',
    })
    const test = await screen.findByRole('button', { name: 'Test the draft' })
    await vi.waitFor(() => expect(test).toBeEnabled())
    api.post.mockImplementation(async (path) => {
      if (path.endsWith('/test')) {
        current.prompt = prompt({
          draft: { body: 'You explain KYC results. Keep it short.', tested: true },
        })
        return { ok: true, issues: [], model: 'fake/model', latency_ms: 5, preview: '{}' }
      }
      return prompt({ version: 2, edited: true })
    })
    await user.click(test)
    expect(await screen.findByText('The test passed.')).toBeInTheDocument()
    const publish = screen.getByRole('button', { name: 'Publish' })
    await vi.waitFor(() => expect(publish).toBeEnabled())
    await user.click(publish)
    expect(api.post).not.toHaveBeenCalledWith('/admin/ai/prompts/kyc/publish', expect.anything())
    await user.type(screen.getByLabelText('Why are you making this change?'), 'Shorter is clearer')
    await user.click(screen.getByRole('button', { name: 'Yes, publish' }))
    expect(api.post).toHaveBeenCalledWith('/admin/ai/prompts/kyc/publish', {
      reason: 'Shorter is clearer',
      second_click: true,
    })
  })

  it('shows what the test found when a draft does not pass, and restores an older version with a reason', async () => {
    const user = userEvent.setup()
    current.prompt = prompt({
      version: 3,
      edited: true,
      versions: [
        {
          version: 3,
          by: 'Ada Admin',
          at: '2026-11-18T10:00:00Z',
          reason: 'Warmer tone',
          source: 'edit',
        },
      ],
      draft: { body: 'Be warm.', tested: false },
    })
    await openKyc(user)
    api.post.mockResolvedValue({
      ok: false,
      issues: ['claims a decision was taken (approved)'],
      model: 'fake/m',
      latency_ms: 5,
      preview: '',
    })
    await user.click(screen.getByRole('button', { name: 'Test the draft' }))
    expect(await screen.findByText('The test did not pass.')).toBeInTheDocument()
    expect(screen.getByText(/claims a decision was taken/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Restore the original' }))
    await user.type(
      screen.getByLabelText('Why are you making this change?'),
      'Going back to the original',
    )
    api.post.mockResolvedValue(prompt())
    await user.click(screen.getByRole('button', { name: 'Yes, restore' }))
    expect(api.post).toHaveBeenLastCalledWith('/admin/ai/prompts/kyc/rollback', {
      version: 1,
      reason: 'Going back to the original',
      second_click: true,
    })
  })
})

describe('diffLines', () => {
  it('marks removed and added lines and keeps the ones that stayed', () => {
    const lines = diffLines('a\nb', 'a\nc')
    expect(lines).toEqual([
      { t: 'a', k: 'same' },
      { t: 'b', k: 'del' },
      { t: 'c', k: 'add' },
    ])
  })
})
