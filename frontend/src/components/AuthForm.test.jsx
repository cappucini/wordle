// AuthForm: the sign-in and create-account form. Its two handlers are fakes, so these tests
// check what the form sends and what it says, without a backend.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { apiError } from '../test/factories'
import AuthForm from './AuthForm'

// Draws the form with fake handlers that succeed and no notice. Pass props to replace any
// of those. Returns the handlers, so a test can check how they were called.
function renderForm(props) {
  const handlers = {
    onSignIn: vi.fn().mockResolvedValue(),
    onCreateAccount: vi.fn().mockResolvedValue(),
  }
  // props is spread last, so whatever the test passed wins over the defaults
  render(<AuthForm notice="" {...handlers} {...props} />)
  return handlers
}

// Types into the two fields. An empty string leaves that field untouched.
async function fillIn(username, password) {
  if (username !== '') {
    await userEvent.type(screen.getByLabelText('Username'), username)
  }
  if (password !== '') {
    await userEvent.type(screen.getByLabelText('Password'), password)
  }
}

// Clicks the link that turns the sign-in form into the create-account form.
async function switchToCreate() {
  await userEvent.click(screen.getByRole('button', { name: 'New here? Create an account' }))
}

// The line where the form reports problems (it has role="alert").
function message() {
  return screen.getByRole('alert')
}

describe('AuthForm: signing in', () => {
  it('starts as a sign-in form', () => {
    renderForm()

    expect(screen.getByRole('heading', { name: 'Sign in to play' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(message()).toBeEmptyDOMElement()
  })

  it('sends the username and password', async () => {
    const { onSignIn, onCreateAccount } = renderForm()

    await fillIn('erica', 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(onSignIn).toHaveBeenCalledExactlyOnceWith('erica', 'correct horse')
    expect(onCreateAccount).not.toHaveBeenCalled()
  })

  it('can be submitted with the Enter key', async () => {
    const { onSignIn } = renderForm()

    await fillIn('erica', 'correct horse{Enter}')

    expect(onSignIn).toHaveBeenCalledOnce()
  })

  it('trims spaces around the username but leaves the password alone', async () => {
    const { onSignIn } = renderForm()

    await fillIn('  erica  ', '  spaced out  ')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(onSignIn).toHaveBeenCalledWith('erica', '  spaced out  ')
  })

  it.each([
    ['', ''],
    ['erica', ''],
    ['', 'correct horse'],
    ['   ', 'correct horse'],
  ])('asks for both fields when username is "%s" and password is "%s"', async (username, password) => {
    const { onSignIn } = renderForm()

    await fillIn(username, password)
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(message()).toHaveTextContent('Enter a username and a password.')
    expect(onSignIn).not.toHaveBeenCalled()
  })

  it('leaves it to the backend to judge a short password when signing in', async () => {
    const { onSignIn } = renderForm()

    await fillIn('erica', 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(onSignIn).toHaveBeenCalledWith('erica', 'short')
  })

  it.each([
    ['INVALID_CREDENTIALS', 'Wrong username or password.'],
    // a username or password of a shape no account can have is simply wrong
    ['INVALID_REQUEST', 'Wrong username or password.'],
    ['NETWORK_ERROR', "Can't reach the game server. Is it running?"],
    ['TOO_MANY_ATTEMPTS', 'Too many attempts. Wait a few minutes and try again.'],
    ['SOMETHING_NEW', 'Something went wrong. Please try again.'],
  ])('explains a %s error', async (code, text) => {
    renderForm({ onSignIn: vi.fn().mockRejectedValue(apiError(code)) })

    await fillIn('erica', 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(message()).toHaveTextContent(text)
  })

  it('cannot be sent twice while the first attempt is in flight', async () => {
    let finish
    // a sign-in that stays unanswered until the test calls finish()
    const onSignIn = vi.fn(() => new Promise((resolve) => (finish = resolve)))
    renderForm({ onSignIn: onSignIn })
    await fillIn('erica', 'correct horse')

    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Password'), '{Enter}')
    expect(onSignIn).toHaveBeenCalledOnce()
    finish()
  })

  it('can be tried again after a failure', async () => {
    renderForm({ onSignIn: vi.fn().mockRejectedValue(apiError('INVALID_CREDENTIALS')) })
    await fillIn('erica', 'wrong password')

    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
  })
})

describe('AuthForm: creating an account', () => {
  it('switches to the create form and explains the rules', async () => {
    renderForm()

    await switchToCreate()

    expect(screen.getByRole('heading', { name: 'Create an account' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument()
    expect(
      screen.getByText('Username: 3 to 20 letters, numbers or underscores. Password: at least 8 characters.'),
    ).toBeInTheDocument()
  })

  it('sends the username and password to create the account', async () => {
    const { onSignIn, onCreateAccount } = renderForm()
    await switchToCreate()

    await fillIn('erica_2', 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(onCreateAccount).toHaveBeenCalledExactlyOnceWith('erica_2', 'correct horse')
    expect(onSignIn).not.toHaveBeenCalled()
  })

  it.each([
    ['ab', 'too short'],
    ['a'.repeat(21), 'too long'],
    ['eri ca', 'a space'],
    ['erica!', 'punctuation'],
  ])('refuses the username "%s" (%s) before sending anything', async (username) => {
    const { onCreateAccount } = renderForm()
    await switchToCreate()

    await fillIn(username, 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(message()).toHaveTextContent('Usernames are 3 to 20 letters, numbers or underscores.')
    expect(onCreateAccount).not.toHaveBeenCalled()
  })

  it.each(['abc', 'a'.repeat(20), 'Erica_2'])('accepts the username "%s"', async (username) => {
    const { onCreateAccount } = renderForm()
    await switchToCreate()

    await fillIn(username, 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(onCreateAccount).toHaveBeenCalledWith(username, 'correct horse')
  })

  it('refuses a password under 8 characters before sending anything', async () => {
    const { onCreateAccount } = renderForm()
    await switchToCreate()

    await fillIn('erica', '1234567')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(message()).toHaveTextContent('Passwords need at least 8 characters.')
    expect(onCreateAccount).not.toHaveBeenCalled()
  })

  it('refuses a password made only of spaces before sending anything', async () => {
    const { onCreateAccount } = renderForm()
    await switchToCreate()

    await fillIn('erica', '          ')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(message()).toHaveTextContent("Passwords can't be only spaces.")
    expect(onCreateAccount).not.toHaveBeenCalled()
  })

  it('refuses a password over 128 characters with a sentence about its length', async () => {
    const { onCreateAccount } = renderForm()
    await switchToCreate()
    await userEvent.type(screen.getByLabelText('Username'), 'erica')
    await userEvent.click(screen.getByLabelText('Password'))
    // pasted in one go rather than typed one key at a time
    await userEvent.paste('p'.repeat(129))

    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(message()).toHaveTextContent('Passwords can be at most 128 characters.')
    expect(onCreateAccount).not.toHaveBeenCalled()
  })

  it('accepts a password of exactly 128 characters', async () => {
    const { onCreateAccount } = renderForm()
    await switchToCreate()
    await userEvent.type(screen.getByLabelText('Username'), 'erica')
    await userEvent.click(screen.getByLabelText('Password'))
    await userEvent.paste('p'.repeat(128))

    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(onCreateAccount).toHaveBeenCalledOnce()
  })

  it('accepts a password of exactly 8 characters', async () => {
    const { onCreateAccount } = renderForm()
    await switchToCreate()

    await fillIn('erica', '12345678')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(onCreateAccount).toHaveBeenCalledOnce()
  })

  it.each([
    ['USERNAME_TAKEN', 'That username is taken. Try another, or sign in.'],
    [
      'INVALID_REQUEST',
      'Usernames are 3 to 20 letters, numbers or underscores. Passwords need at least 8 characters.',
    ],
  ])('explains a %s error', async (code, text) => {
    renderForm({ onCreateAccount: vi.fn().mockRejectedValue(apiError(code)) })
    await switchToCreate()

    await fillIn('erica', 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(message()).toHaveTextContent(text)
  })

  it('clears the message and keeps what was typed when switching back', async () => {
    renderForm()
    await switchToCreate()
    await fillIn('ab', 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(message()).not.toBeEmptyDOMElement()

    await userEvent.click(screen.getByRole('button', { name: 'I already have an account' }))

    expect(screen.getByRole('heading', { name: 'Sign in to play' })).toBeInTheDocument()
    expect(message()).toBeEmptyDOMElement()
    expect(screen.getByLabelText('Username')).toHaveValue('ab')
  })
})

describe('AuthForm: why the form is showing', () => {
  it('shows the notice it was given', () => {
    renderForm({ notice: 'Your sign-in has ended. Please sign in again.' })

    expect(screen.getByText('Your sign-in has ended. Please sign in again.')).toBeInTheDocument()
  })

  it('tells a visitor who followed an invite link why they must sign in', () => {
    window.history.replaceState({}, '', '/?game=3f2b8c1e')

    renderForm()

    expect(
      screen.getByText("You've been invited to a game. Sign in or create an account to join it."),
    ).toBeInTheDocument()
  })

  it('does not mention an invite on a plain visit', () => {
    renderForm()

    expect(screen.queryByText(/invited to a game/)).toBeNull()
  })

  it('shows the notice rather than the invite line when there are both', () => {
    window.history.replaceState({}, '', '/?game=3f2b8c1e')

    renderForm({ notice: 'Your sign-in has ended. Please sign in again.' })

    expect(screen.getByText('Your sign-in has ended. Please sign in again.')).toBeInTheDocument()
    expect(screen.queryByText(/invited to a game/)).toBeNull()
  })
})
