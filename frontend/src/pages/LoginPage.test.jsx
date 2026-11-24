import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const signIn = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ login: vi.fn(), verifyTwoStep: vi.fn() }))
vi.mock('../App', () => ({ useSession: () => ({ signIn }) }))

import { login, verifyTwoStep } from '../api/client'
import LoginPage from './LoginPage'

const SESSION = { access_token: 't', user: { id: 'u1', role: 'admin' }, session: {} }

beforeEach(() => {
  signIn.mockReset()
  login.mockReset()
  verifyTwoStep.mockReset()
})

async function passwordStep(user) {
  await user.type(screen.getByLabelText('Email'), 'ada@example.test')
  await user.type(screen.getByLabelText('Password'), 'secret password')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
}

describe('LoginPage', () => {
  it('keeps the five stages and the human-confirms line, but no score weights or bands', () => {
    render(<LoginPage />)
    expect(screen.getByRole('list', { name: 'The five underwriting stages' })).toBeInTheDocument()
    expect(screen.getByText('A human confirms every case.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Score weights')).toBeNull()
    expect(screen.queryByText(/recommend approve|recommend reject|refer/i)).toBeNull()
    expect(screen.queryByText(/100 points/)).toBeNull()
  })

  it('shows only the plain contact sentence, with no email, phone or link, and no footer', () => {
    const { container } = render(<LoginPage />)
    expect(screen.getByText("Can't sign in? Contact your admin.")).toBeInTheDocument()
    expect(container.querySelector('a[href^="mailto:"], a[href^="tel:"]')).toBeNull()
    expect(screen.queryByRole('contentinfo')).toBeNull()
  })

  it('shows and hides the password with a toggle button', () => {
    render(<LoginPage />)
    const field = screen.getByLabelText('Password')
    expect(field).toHaveAttribute('type', 'password')
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(field).toHaveAttribute('type', 'text')
    fireEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(field).toHaveAttribute('type', 'password')
  })

  it('signs an officer straight in after the password', async () => {
    const user = userEvent.setup()
    login.mockResolvedValue(SESSION)
    render(<LoginPage />)
    await passwordStep(user)
    expect(signIn).toHaveBeenCalledWith(SESSION)
    expect(verifyTwoStep).not.toHaveBeenCalled()
  })

  it('asks an admin for the code from their authenticator app, then signs in', async () => {
    const user = userEvent.setup()
    login.mockResolvedValue({ mfa: 'code', mfa_token: 'm1' })
    verifyTwoStep.mockResolvedValue(SESSION)
    render(<LoginPage />)
    await passwordStep(user)
    expect(signIn).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { name: 'Enter your code' })).toBeInTheDocument()
    expect(screen.getByText(/Google Authenticator, Microsoft Authenticator/)).toBeInTheDocument()
    await user.type(screen.getByLabelText('6-digit code'), '123456')
    await user.click(screen.getByRole('button', { name: 'Verify and sign in' }))
    expect(verifyTwoStep).toHaveBeenCalledWith('m1', '123456')
    expect(signIn).toHaveBeenCalledWith(SESSION)
  })

  it('keeps the person on the code step after a wrong code', async () => {
    const user = userEvent.setup()
    login.mockResolvedValue({ mfa: 'code', mfa_token: 'm1' })
    verifyTwoStep.mockRejectedValue(Object.assign(new Error('That code is not right.'), {}))
    render(<LoginPage />)
    await passwordStep(user)
    await user.type(screen.getByLabelText('6-digit code'), '000000')
    await user.click(screen.getByRole('button', { name: 'Verify and sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('That code is not right.')
    expect(screen.getByLabelText('6-digit code')).toBeInTheDocument()
  })

  it('goes back to the password when the 2-step wait ran out', async () => {
    const user = userEvent.setup()
    login.mockResolvedValue({ mfa: 'code', mfa_token: 'm1' })
    verifyTwoStep.mockRejectedValue(
      Object.assign(new Error('This sign-in took too long.'), { reason: 'restart' }),
    )
    render(<LoginPage />)
    await passwordStep(user)
    await user.type(screen.getByLabelText('6-digit code'), '123456')
    await user.click(screen.getByRole('button', { name: 'Verify and sign in' }))
    expect(await screen.findByRole('status')).toHaveTextContent('This sign-in took too long.')
    expect(screen.getByLabelText('Password')).toHaveValue('')
  })

  it('takes a recovery code and says how many are left', async () => {
    const user = userEvent.setup()
    login.mockResolvedValue({ mfa: 'code', mfa_token: 'm1' })
    verifyTwoStep.mockResolvedValue({ ...SESSION, recovery_codes_left: 2 })
    render(<LoginPage />)
    await passwordStep(user)
    await user.click(screen.getByRole('button', { name: 'Lost your phone? Use a recovery code' }))
    await user.type(screen.getByLabelText('Recovery code'), 'abcde-fghjk')
    await user.click(screen.getByRole('button', { name: 'Verify and sign in' }))
    expect(verifyTwoStep).toHaveBeenCalledWith('m1', 'abcde-fghjk')
    expect(screen.getByText('2 recovery codes')).toBeInTheDocument()
    expect(signIn).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Continue to Pramaan' }))
    expect(signIn).toHaveBeenCalled()
  })

  it('sets up 2-step with a QR code and shows the recovery codes before going on', async () => {
    const user = userEvent.setup()
    const setup = { qr: 'data:image/svg+xml,x', key: 'ABCD EFGH', account: 'ada@example.test' }
    login.mockResolvedValue({ mfa: 'setup', mfa_token: 'm1', setup })
    const codes = ['aaaaa-bbbbb', 'ccccc-ddddd']
    verifyTwoStep.mockResolvedValue({ ...SESSION, recovery_codes: codes })
    render(<LoginPage />)
    await passwordStep(user)
    expect(screen.getByRole('heading', { name: 'Set up 2-step verification' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /QR code/ })).toHaveAttribute('src', setup.qr)
    expect(screen.getByTestId('two-step-key')).toHaveTextContent('ABCD EFGH')
    await user.type(screen.getByLabelText('6-digit code'), '654321')
    await user.click(screen.getByRole('button', { name: 'Turn on and sign in' }))
    const list = screen.getByRole('list', { name: 'Recovery codes' })
    expect(list).toHaveTextContent('aaaaa-bbbbb')
    const go = screen.getByRole('button', { name: 'Continue to Pramaan' })
    expect(go).toBeDisabled() // only after "I have saved these codes"
    await user.click(screen.getByLabelText('I have saved these codes'))
    await user.click(go)
    expect(signIn).toHaveBeenCalledWith({ ...SESSION, recovery_codes: codes })
  })
})
