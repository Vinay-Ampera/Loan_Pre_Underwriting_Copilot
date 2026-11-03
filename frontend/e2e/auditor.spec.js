import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

test('the auditor reads everything, sees it read-only, and the server refuses every write', async ({
  page,
}) => {
  await signIn(page, 'auditor')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await page.getByRole('button', { name: /E2E Auditor/ }).click()
  await expect(page.getByText(/this account changes nothing/)).toBeVisible()
  await page.keyboard.press('Escape')

  const nav = page.getByRole('navigation', { name: 'Main' })
  for (const name of ['Overview', 'Cases', 'Messages', 'Audit log', 'Users', 'Help']) {
    await expect(nav.getByRole('link', { name })).toBeVisible()
  }
  await expect(nav.getByRole('link', { name: 'New case' })).toHaveCount(0)

  await nav.getByRole('link', { name: 'Cases' }).click()
  await expect(page.getByRole('link', { name: 'CASE-2026-9001' })).toBeVisible() // another officer's case
  await expect(page.getByRole('link', { name: 'New case' })).toHaveCount(0)

  await nav.getByRole('link', { name: 'Audit log' }).click()
  await expect(page.getByRole('heading', { name: 'Audit log' })).toBeVisible()
  await nav.getByRole('link', { name: 'Users' }).click()
  await expect(page.getByRole('cell', { name: 'E2E Officer' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Disable|Reset/ })).toHaveCount(0)

  await page.goto('/cases/new') // typing the address does not help
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()

  const token = await page.evaluate(() => JSON.parse(sessionStorage.getItem('lc.session')).token)
  const headers = { Authorization: `Bearer ${token}` }
  const id = '00000000-0000-0000-0000-000000000000'
  for (const [method, url] of [
    ['post', '/api/v1/cases'],
    ['post', `/api/v1/cases/${id}/confirm`],
    ['post', `/api/v1/cases/${id}/override`],
    ['post', `/api/v1/cases/${id}/documents`],
    ['get', `/api/v1/cases/${id}/documents/${id}/file`],
    ['post', `/api/v1/cases/${id}/messages`],
    ['post', '/api/v1/admin/users'],
    ['post', `/api/v1/admin/precedents/${id}/approve`],
  ]) {
    const res = await page.request[method](url, { headers, data: {} })
    expect(res.status(), `${method} ${url}`).toBe(403)
  }
})

test('an admin sees the auditor account but cannot manage it', async ({ page }) => {
  await signIn(page, 'admin')
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Users' }).click()
  await expect(page.getByRole('button', { name: 'Disable E2E Auditor' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Reset password for E2E Auditor' })).toBeDisabled()
  await page.getByRole('button', { name: 'Add user' }).click()
  await page.getByLabel('Role').selectOption('admin')
  await expect(page.getByText('You are creating an admin.')).toBeVisible()
})
