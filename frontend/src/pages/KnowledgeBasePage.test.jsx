import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
  upload: vi.fn(),
}))
vi.mock('../api/client', () => ({ api }))

import KnowledgeBasePage from './KnowledgeBasePage'
import PolicyLibraryPage from './PolicyLibraryPage'
import { ruleText } from '../lib/policy'

const rule = {
  rule_id: 'HL-CIBIL-01',
  kind: 'hard',
  stage: 'credit',
  field: 'cibil_score',
  operator: 'gte',
  threshold: 700,
  tiers: null,
  points: 0,
  on_fail: 'stop',
  fail_class: 'eligibility',
}
const clause = (id, title, text, rules = []) => ({
  clause_id: id,
  title,
  source_tag: 'public',
  text,
  rules,
  cited_30d: 2,
})
const version = (over = {}) => ({
  id: 'v1',
  loan_type: 'home',
  title: 'Sample Bank Home Loan Policy',
  version: '2026.10.31-1',
  status: 'active',
  origin: 'file',
  effective_from: '2026-11-01',
  reason: null,
  published_by: null,
  published_at: null,
  clauses: 2,
  embedded: 2,
  intro: 'Sample policy, synthetic.',
  clause_list: [
    clause('HL-ELIG-03', 'Credit score', 'A credit score of 700 or above is required.', [rule]),
    clause('HL-PROD-01', 'Tenure', 'The maximum tenure is 30 years.'),
  ],
  ...over,
})
const check = (over = {}) => ({
  ok: true,
  errors: [],
  warnings: [
    {
      level: 'warning',
      code: 'RULE_NUMBER',
      message: 'Rule HL-CIBIL-01 uses 700 from the rules file',
      line: 12,
      clause_id: 'HL-ELIG-03',
    },
  ],
  fixes: [],
  fixed_text: null,
  summary: {
    version: '2026.11.21-1',
    title: 'x',
    clauses: 2,
    effective_from: '2026-11-21',
    takes_effect: 'now',
  },
  changes: null,
  ...over,
})
const draft = (over = {}) => ({
  loan_type: 'home',
  body: '---\nversion: "2026.11.21-1"\n---\n',
  origin: 'edit',
  updated_by: 'Ada Admin',
  updated_at: '2026-11-21T10:00:00Z',
  check: check(),
  retrieval: null,
  retrieval_stale: false,
  clauses: version().clause_list,
  can_publish: false,
  blockers: ['Run the retrieval check on this text.'],
  warning_count: 1,
  ...over,
})
const policies = () =>
  ['common', 'personal', 'home', 'education', 'business', 'vehicle'].map((lt) => ({
    loan_type: lt,
    active: { id: lt, version: '2026.10.31-1', clauses: 9, missing_embeddings: 0 },
    scheduled: null,
    draft: lt === 'home' && current.draft ? { updated_at: 'x' } : null,
  }))

let current
beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset())
  current = { draft: null, versions: [version()], learnings: null }
  api.get.mockImplementation(async (path) => {
    if (path === '/knowledge/policies') return policies()
    if (path.startsWith('/knowledge/policies/'))
      return {
        loan_type: 'home',
        active: version(),
        scheduled: null,
        versions: current.versions,
        draft: current.draft,
      }
    if (path.startsWith('/knowledge/learnings')) return current.learnings
    if (path.startsWith('/knowledge/search'))
      return {
        active: [{ clause_id: 'HL-ELIG-03', title: 'Credit score', text: 't', relevance: 0.9 }],
        draft: null,
      }
    throw new Error(`unexpected ${path}`)
  })
  api.post.mockResolvedValue({})
  api.put.mockResolvedValue({})
})

const renderAdmin = () =>
  render(
    <MemoryRouter>
      <KnowledgeBasePage />
    </MemoryRouter>,
  )

async function openHome(user) {
  renderAdmin()
  await user.click(await screen.findByRole('button', { name: /Home loan/ }))
}

describe('Knowledge base: reading', () => {
  it('shows each clause with the rules that use it and how often it was cited', async () => {
    const user = userEvent.setup()
    await openHome(user)
    const c = await screen.findByText('A credit score of 700 or above is required.')
    const item = c.closest('li')
    expect(
      within(item).getByText(/cibil score ≥ 700 · hard, stops \(eligibility\)/),
    ).toBeInTheDocument()
    expect(within(item).getByText('Cited in 2 cases in the last 30 days.')).toBeInTheDocument()
  })

  it('writes rules in plain words', () => {
    expect(ruleText(rule)).toBe('cibil score ≥ 700 · hard, stops (eligibility)')
    expect(
      ruleText({
        ...rule,
        kind: 'soft',
        points: 5,
        tiers: [{ operator: 'gte', threshold: 95, points: 5 }],
      }),
    ).toBe('cibil score: ≥ 95: 5 points (of 5)')
  })
})

describe('Knowledge base: changing a policy', () => {
  it('changes one clause through the clause endpoint', async () => {
    const user = userEvent.setup()
    await openHome(user)
    await user.click(screen.getByRole('tab', { name: 'Change' }))
    await user.click(await screen.findByRole('button', { name: 'Change HL-ELIG-03' }))
    const text = screen.getByLabelText('Clause text')
    await user.clear(text)
    await user.type(text, 'A credit score of 720 or above is required.')
    await user.click(screen.getByRole('button', { name: 'Save to the draft' }))
    expect(api.post).toHaveBeenCalledWith('/knowledge/policies/home/draft/clause', {
      action: 'edit',
      clause_id: 'HL-ELIG-03',
      source_tag: 'public',
      title: 'Credit score',
      text: 'A credit score of 720 or above is required.',
    })
  })

  it('publishes only after the retrieval check, a reason and the warnings tick', async () => {
    current.draft = draft()
    const user = userEvent.setup()
    await openHome(user)
    await user.click(screen.getByRole('tab', { name: /Change/ }))
    expect(await screen.findByRole('button', { name: 'Publish…' })).toBeDisabled()
    expect(screen.getByText('Run the retrieval check on this text.')).toBeInTheDocument()
    expect(screen.getByText(/Rule HL-CIBIL-01 uses 700/)).toBeInTheDocument()

    current.draft = draft({
      can_publish: true,
      blockers: [],
      retrieval: {
        queries: 10,
        now: { 'hit@1': 0.9, 'hit@3': 1, 'recall@5': 1, mrr: 0.95, citation_validity: 1 },
        draft: { 'hit@1': 0.9, 'hit@3': 1, 'recall@5': 1, mrr: 0.95, citation_validity: 1 },
        errors: [],
        warnings: [],
      },
    })
    await user.click(screen.getByRole('button', { name: 'Run the retrieval check' }))
    expect(api.post).toHaveBeenCalledWith('/knowledge/policies/home/draft/retrieval-check')
    await user.click(await screen.findByRole('button', { name: 'Publish…' }))
    const confirm = screen.getByRole('button', { name: 'Yes, publish' })
    await user.type(
      screen.getByLabelText('Why are you making this change?'),
      'Board approved the change',
    )
    expect(confirm).toBeDisabled() // the warnings are not ticked yet
    await user.click(screen.getByLabelText(/I have read the 1 warning/))
    await user.click(confirm)
    expect(api.post).toHaveBeenCalledWith('/knowledge/policies/home/draft/publish', {
      reason: 'Board approved the change',
      second_click: true,
      accept_warnings: true,
    })
  })

  it('applies the auto-fixes by saving the fixed text, and discards only after a confirm', async () => {
    current.draft = draft({
      check: check({
        ok: false,
        errors: [{ level: 'error', code: 'HEADING_BAD', message: 'Not a heading', line: 9 }],
        fixes: [
          {
            line: 9,
            before: '##HL-ELIG-03 - public - x',
            after: '## HL-ELIG-03 | public | x',
            why: 'Clause heading put in the form',
          },
        ],
        fixed_text: 'FIXED',
      }),
      clauses: null,
    })
    const user = userEvent.setup()
    await openHome(user)
    await user.click(screen.getByRole('tab', { name: /Change/ }))
    await user.click(await screen.findByRole('button', { name: 'Apply these fixes to the draft' }))
    expect(api.put).toHaveBeenCalledWith('/knowledge/policies/home/draft', {
      body: 'FIXED',
      origin: 'edit',
    })
    await user.click(screen.getByRole('button', { name: 'Discard the draft' }))
    expect(api.del).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Yes, discard' }))
    expect(api.del).toHaveBeenCalledWith('/knowledge/policies/home/draft')
  })

  it('needs every proposed clause ID checked before an old-format import becomes the draft', async () => {
    api.upload.mockResolvedValue({
      text: '1. Credit score\nA score of 720.',
      kind: 'txt',
      notes: ['Plain text is read line by line.'],
      check: check({
        ok: false,
        warnings: [],
        errors: [{ code: 'NO_CLAUSES', message: 'No clauses' }],
      }),
      suggest_legacy: true,
    })
    api.post.mockImplementation(async (path) =>
      path === '/knowledge/legacy'
        ? {
            text: '## HL-ELIG-03 | public | Credit score\nA score of 720.',
            mapping: [
              {
                line: 1,
                heading: 'Credit score',
                clause_id: 'HL-ELIG-03',
                how: 'matched',
                matched: 'Credit score',
              },
            ],
          }
        : {},
    )
    const user = userEvent.setup()
    await openHome(user)
    await user.click(screen.getByRole('tab', { name: 'Change' }))
    await user.click(screen.getByRole('tab', { name: 'Upload a file' }))
    const file = new File(['1. Credit score'], 'old.txt', { type: 'text/plain' })
    await user.upload(screen.getByLabelText(/A .md, .txt or .docx file/), file)
    expect(api.upload).toHaveBeenCalledWith('/knowledge/convert', expect.any(FormData))
    expect(await screen.findByText(/No clause headings were found/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Import as an old-format document' }))
    expect(await screen.findByText('same title as Credit score')).toBeInTheDocument()
    const use = screen.getAllByRole('button', { name: 'Use this as the draft' }).at(-1)
    expect(use).toBeDisabled()
    await user.click(screen.getByLabelText(/I have checked every clause ID/))
    await user.click(use)
    expect(api.put).toHaveBeenCalledWith('/knowledge/policies/home/draft', {
      body: '## HL-ELIG-03 | public | Credit score\nA score of 720.',
      origin: 'legacy',
    })
  })
})

describe('Knowledge base: history and learnings', () => {
  it('retires an older version only with a reason, and restores it into a draft', async () => {
    current.versions = [
      version(),
      version({ id: 'v0', version: '2025.04.01-1', status: 'superseded' }),
    ]
    const user = userEvent.setup()
    await openHome(user)
    await user.click(screen.getByRole('tab', { name: 'History' }))
    await user.click(await screen.findByRole('button', { name: 'Retire…' }))
    await user.type(
      screen.getByLabelText('Why are you making this change?'),
      'Wrong file last year',
    )
    await user.click(screen.getByRole('button', { name: 'Yes, retire' }))
    expect(api.post).toHaveBeenCalledWith('/knowledge/versions/v0/retire', {
      reason: 'Wrong file last year',
      second_click: true,
    })
    await user.click(screen.getByRole('button', { name: 'Restore as a draft' }))
    expect(api.post).toHaveBeenCalledWith('/knowledge/versions/v0/restore')
  })

  it('confirms a paused precedent again with a reason', async () => {
    current.learnings = {
      counts: { approved: 1, paused: 1, pending: 2, held: 0, retired: 0, expired: 0, rejected: 0 },
      uses_30d: 3,
      items: [
        {
          id: 'p1',
          status: 'paused',
          loan_type: 'home',
          rule_ids: ['HL-CIBIL-01'],
          summary: 'Borderline credit score; officer verified repayments.',
          valid_until: '2027-01-01',
          days_left: 40,
          times_used: 2,
          last_used: null,
          cases: ['CASE-2026-0001'],
          reviewed_by: 'Ada Admin',
          paused_reason: 'The home policy changed (version 2026.11.21-1).',
        },
      ],
    }
    const user = userEvent.setup()
    renderAdmin()
    await user.click(screen.getByRole('tab', { name: 'Learnings' }))
    expect(await screen.findByText(/The home policy changed/)).toBeInTheDocument()
    expect(screen.getByText(/cases CASE-2026-0001/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Confirm again…' }))
    await user.type(
      screen.getByLabelText('Why are you making this change?'),
      'Still holds after the change',
    )
    await user.click(screen.getByRole('button', { name: 'Yes, confirm' }))
    expect(api.post).toHaveBeenCalledWith('/knowledge/learnings/p1/reconfirm', {
      reason: 'Still holds after the change',
      second_click: true,
    })
  })
})

describe('Policies for officers', () => {
  it('reads and searches the policy in force with no way to change it', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <PolicyLibraryPage />
      </MemoryRouter>,
    )
    expect(
      await screen.findByText('A credit score of 700 or above is required.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Change' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Cited in/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Compare with drafts')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Question'), 'credit score floor')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(api.get).toHaveBeenCalledWith(
      '/knowledge/search?q=credit+score+floor&loan_type=home&draft=false',
    )
  })
})
