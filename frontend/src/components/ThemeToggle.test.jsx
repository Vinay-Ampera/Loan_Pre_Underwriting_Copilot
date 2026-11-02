import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import ThemeToggle from './ThemeToggle'

afterEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('ThemeToggle', () => {
  it('is a labelled three-way choice with system selected by default', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('radiogroup', { name: 'Colour theme' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'System theme' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Dark theme' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: 'Light theme' })).not.toBeChecked()
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })

  it('sets <html data-theme> and remembers the choice', async () => {
    const user = userEvent.setup()
    render(<ThemeToggle />)
    await user.click(screen.getByRole('radio', { name: 'Dark theme' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem('lc.theme')).toBe('dark')
    await user.click(screen.getByRole('radio', { name: 'Light theme' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    await user.click(screen.getByRole('radio', { name: 'System theme' }))
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
    expect(localStorage.getItem('lc.theme')).toBeNull()
  })

  it('starts from the stored choice', () => {
    localStorage.setItem('lc.theme', 'dark')
    render(<ThemeToggle />)
    expect(screen.getByRole('radio', { name: 'Dark theme' })).toBeChecked()
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })
})
