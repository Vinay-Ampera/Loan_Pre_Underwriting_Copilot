import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

test('the login page has the contact sentence, no weights and no footer', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByText("Can't sign in? Contact your admin.")).toBeVisible()
  await expect(page.locator('a[href^="mailto:"], a[href^="tel:"]')).toHaveCount(0)
  await expect(page.getByLabel('Score weights')).toHaveCount(0)
  await expect(page.getByRole('contentinfo')).toHaveCount(0)
})

test('an officer sees the footer and the officer Help guide with weights and bands', async ({
  page,
}) => {
  await signIn(page, 'officer')
  const footer = page.getByRole('contentinfo')
  await expect(footer).toContainText('Pramaan, sample bank, synthetic data only')
  await expect(footer).toContainText(/Version \d/)
  await footer.getByRole('link', { name: 'Help' }).click()
  await expect(page).toHaveURL(/\/help$/)
  await expect(page.getByText('Guide for loan officers')).toBeVisible()
  await expect(page.getByRole('list', { name: 'Score weights' })).toContainText('Income and FOIR')
  await expect(page.getByRole('list', { name: 'Score bands' })).toContainText(
    'Below 60: recommend reject',
  )
  await expect(page.getByRole('heading', { name: 'The precedent queue' })).toHaveCount(0)
  const nav = page.getByRole('navigation', { name: 'Main' })
  await nav.getByRole('link', { name: 'Home' }).click() // sidebar still works, footer stays
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('contentinfo')).toBeVisible()
  await nav.getByRole('link', { name: 'Help' }).click()
  await expect(page).toHaveURL(/\/help$/)
})

test('an admin sees the footer and the admin Help guide only', async ({ page }) => {
  await signIn(page, 'admin')
  await expect(page.getByRole('contentinfo')).toBeVisible()
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Help' }).click()
  await expect(page.getByText('Guide for admins')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'The precedent queue' })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Score weights' })).toHaveCount(0)
})

test('signing out removes the footer', async ({ page }) => {
  await signIn(page, 'officer')
  await expect(page.getByRole('contentinfo')).toBeVisible()
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('contentinfo')).toHaveCount(0)
})
