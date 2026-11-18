import { useEffect, useState } from 'react'
import { SIGNED_OUT_EVENT, getCurrentUser, hasSavedToken, login, logout, register } from '../api'

// Knows who is signed in, and how to sign in, create an account and sign out.
// The token itself is handled inside api.js; this hook only keeps the user for the page.
export function useAuth() {
  const [user, setUser] = useState(null) // { id, username }, or null when signed out
  // true while a saved token is being checked, so the page doesn't flash the sign-in form
  // at someone who is already signed in
  const [isCheckingSignIn, setIsCheckingSignIn] = useState(() => hasSavedToken())
  // a line for the sign-in form, set when the player was signed out without asking to be
  const [notice, setNotice] = useState('')

  // On first load: if a token was saved by an earlier visit, ask the backend whose it is.
  useEffect(() => {
    if (!hasSavedToken()) {
      return
    }
    getCurrentUser()
      .then((currentUser) => setUser(currentUser))
      .catch(() => {
        // an expired or unknown token: api.js has already cleared it, so stay signed out
      })
      .finally(() => setIsCheckingSignIn(false))
  }, [])

  // api.js announces when the backend rejects the token mid-session (it expired, or the
  // account signed out elsewhere). Drop the user so the sign-in form comes back.
  useEffect(() => {
    function handleSignedOut() {
      // This only fires when a saved sign-in was sent and refused, so the player did have one.
      // Say why the form is back, rather than dropping them on it without a word.
      setUser(null)
      setNotice('Your sign-in has ended. Please sign in again.')
    }
    window.addEventListener(SIGNED_OUT_EVENT, handleSignedOut)
    return () => window.removeEventListener(SIGNED_OUT_EVENT, handleSignedOut)
  }, [])

  // These two let errors (wrong password, username taken) reach the form, which shows them.
  async function signIn(username, password) {
    setUser(await login(username, password))
    setNotice('')
  }

  async function createAccount(username, password) {
    setUser(await register(username, password))
    setNotice('')
  }

  async function signOut() {
    try {
      await logout()
    } catch {
      // the token is forgotten locally either way, so the player is signed out here
    }
    setUser(null)
  }

  return { user, isCheckingSignIn, notice, signIn, createAccount, signOut }
}
