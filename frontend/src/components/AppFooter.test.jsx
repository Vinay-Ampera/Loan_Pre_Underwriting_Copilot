import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it } from 'vitest'
import AppFooter from './AppFooter'

it('shows the sample-bank note, a Help link and the version', () => {
  render(
    <MemoryRouter>
      <AppFooter />
    </MemoryRouter>,
  )
  expect(screen.getByRole('contentinfo')).toHaveTextContent(
    'Pramaan, sample bank, synthetic data only',
  )
  expect(screen.getByRole('link', { name: 'Help' })).toHaveAttribute('href', '/help')
  expect(screen.getByText(/^Version \S+/)).toBeInTheDocument()
})
