import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

const REPORT = 'The upload page froze after the third file was added.'
const unreadLabel = (n) => (n === 0 ? 'Notifications, none unread' : `Notifications, ${n} unread`)

test('a problem report reaches the admin inbox, reading it lowers the count, and notice emails can be turned off', async ({
  page,
  browser,
}) => {
  // the officer files a report: every active admin gets a notice in the same transaction
  await signIn(page, 'officer')
  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Report a problem' })
    .click()
  await page.getByLabel('What happened?').fill(REPORT)
  await page.getByRole('button', { name: 'Send report' }).click()
  await expect(page.getByText('Thank you. Your report was sent to the admin.')).toBeVisible()

  const admin = await (await browser.newContext()).newPage()
  await signIn(admin, 'admin')
  const bell = admin.getByRole('button', { name: /^Notifications, \d+ unread$/ })
  await expect(bell).toBeVisible()
  const before = Number((await bell.getAttribute('aria-label')).match(/\d+/)[0])
  await bell.click()
  await expect(admin.getByRole('heading', { name: 'Inbox' })).toBeVisible()

  // the notice is fixed text: no name, no case detail, nothing from the report itself
  const row = admin
    .getByRole('list', { name: 'Notifications' })
    .getByRole('listitem')
    .filter({ hasText: 'A new problem report' })
    .first()
  await expect(row).toContainText('Open the Issues page to read it.')
  await expect(row).not.toContainText(REPORT)
  await row.getByRole('button', { name: 'Mark read: A new problem report' }).click()
  await expect(admin.getByRole('button', { name: unreadLabel(before - 1) })).toBeVisible()

  // a click opens the page the notice points at, where the report can be read
  await row.getByRole('button', { name: /A new problem report/ }).click()
  await expect(admin.getByRole('heading', { name: 'Issues' })).toBeVisible()
  await expect(admin.getByText(REPORT)).toBeVisible()

  // each person chooses whether "you have a new notice" emails are sent; the choice is kept
  await admin.getByRole('button', { name: /E2E Admin/ }).click()
  const box = admin.getByRole('menuitemcheckbox', { name: 'Email me about new notices' })
  await expect(box).toHaveAttribute('aria-checked', 'true')
  await box.click()
  await expect(box).toHaveAttribute('aria-checked', 'false')
  await admin.reload()
  await admin.getByRole('button', { name: /E2E Admin/ }).click()
  await expect(
    admin.getByRole('menuitemcheckbox', { name: 'Email me about new notices' }),
  ).toHaveAttribute('aria-checked', 'false')

  // the auditor has no inbox at all
  const auditor = await (await browser.newContext()).newPage()
  await signIn(auditor, 'auditor')
  await expect(auditor.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(auditor.getByRole('button', { name: /^Notifications/ })).toHaveCount(0)
})
