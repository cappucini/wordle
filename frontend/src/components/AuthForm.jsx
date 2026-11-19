// The sign-in form, which can switch to creating an account.
import { useState } from 'react'
import { errorText } from '../errorText'
import { getGameIdFromUrl } from '../gameUrl'

// The sign-in form. One form does both jobs: signing in, and creating an account.
// `notice` is an optional line explaining why the form is showing, for example after a
// sign-in has expired.
function AuthForm({ onSignIn, onCreateAccount, notice }) {
  const [mode, setMode] = useState('sign-in') // 'sign-in' or 'create'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  // the problem to show under the fields, or '' when there is none
  const [message, setMessage] = useState('')
  // true while a request is on its way, so the form cannot be sent twice
  const [isSending, setIsSending] = useState(false)

  const isCreating = mode === 'create'
  // a game ID in the address bar means this visitor followed someone's invite link
  const hasInvite = getGameIdFromUrl() !== null

  // Runs when the form is sent, by the button or by Enter in a field. Checks the fields,
  // then signs in or creates the account, and shows a message if that fails.
  async function handleSubmit(event) {
    event.preventDefault() // stop the browser from reloading the page, its default for forms
    if (isSending) {
      return
    }
    const problem = checkInputs(username, password, isCreating)
    if (problem !== '') {
      setMessage(problem)
      return
    }

    setIsSending(true)
    setMessage('')
    try {
      if (isCreating) {
        await onCreateAccount(username.trim(), password)
      } else {
        await onSignIn(username.trim(), password)
      }
      // on success the page swaps this form for the game, so there is nothing more to do here
    } catch (error) {
      setMessage(authErrorText(error, isCreating))
      setIsSending(false)
    }
  }

  // Flips between signing in and creating an account. What was typed is kept.
  function switchMode() {
    setMode(isCreating ? 'sign-in' : 'create')
    setMessage('')
  }

  return (
    <form className="auth-form" onSubmit={handleSubmit}>
      <h2 className="auth-heading">{isCreating ? 'Create an account' : 'Sign in to play'}</h2>

      {notice !== '' && <p className="field-hint">{notice}</p>}
      {/* someone arriving through a shared link should know why they are being asked to sign in */}
      {notice === '' && hasInvite && (
        <p className="field-hint">You've been invited to a game. Sign in or create an account to join it.</p>
      )}

      <label className="field">
        <span>Username</span>
        <input
          type="text"
          value={username}
          // a "controlled" input: React holds the text in state, and each keystroke updates it
          onChange={(event) => setUsername(event.target.value)}
          // autoComplete tells the browser's password manager what each field is for
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          autoFocus
        />
      </label>

      <label className="field">
        <span>Password</span>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete={isCreating ? 'new-password' : 'current-password'}
        />
      </label>

      {isCreating && (
        <p className="field-hint">
          Username: 3 to 20 letters, numbers or underscores. Password: at least 8 characters.
        </p>
      )}

      {/* role="alert" makes screen readers read the message out as soon as it appears */}
      <p className="message" role="alert">
        {message}
      </p>

      <button className="new-game" type="submit" disabled={isSending}>
        {isCreating ? 'Create account' : 'Sign in'}
      </button>

      {/* type="button" keeps this one from sending the form; it only switches the mode */}
      <button className="link-button" type="button" onClick={switchMode}>
        {isCreating ? 'I already have an account' : 'New here? Create an account'}
      </button>
    </form>
  )
}

// The backend answers INVALID_REQUEST when a username or password doesn't have a valid shape
// (too short, or with characters that aren't allowed). The general wording for that code talks
// about links and games, which makes no sense on this form, so it gets its own sentence here.
function authErrorText(error, isCreating) {
  if (error.code === 'INVALID_REQUEST') {
    if (isCreating) {
      return 'Usernames are 3 to 20 letters, numbers or underscores. Passwords need at least 8 characters.'
    }
    // no account can have a username or password of that shape, so it is simply wrong
    return 'Wrong username or password.'
  }
  return errorText(error)
}

// Catches the obvious problems before sending anything, so the player gets a plain sentence.
// The backend checks the same rules again; this is only for a quicker, friendlier answer.
function checkInputs(username, password, isCreating) {
  const name = username.trim()
  if (name === '' || password === '') {
    return 'Enter a username and a password.'
  }
  if (!isCreating) {
    return '' // when signing in, let the backend decide; it answers "wrong username or password"
  }
  // the pattern matches only when every character is a letter, a digit or an underscore
  if (name.length < 3 || name.length > 20 || !/^[a-zA-Z0-9_]+$/.test(name)) {
    return 'Usernames are 3 to 20 letters, numbers or underscores.'
  }
  if (password.trim() === '') {
    return "Passwords can't be only spaces."
  }
  if (password.length < 8) {
    return 'Passwords need at least 8 characters.'
  }
  if (password.length > 128) {
    return 'Passwords can be at most 128 characters.'
  }
  return ''
}

export default AuthForm
