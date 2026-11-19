import { useEffect, useState } from 'react'
import { SIGNED_OUT_EVENT, getCurrentUser, login, logout, register } from '../api'
import { errorText } from '../errorText'

// Knows who is signed in, and how to sign in, create an account and sign out.
// The session lives in a cookie the page cannot read, so the only way to know who is signed
// in is to ask the backend. api.js does the asking; this hook keeps the answer for the page.
export function useAuth() {
  const [user, setUser] = useState(null) // { id, username }, or null when signed out
  // true until the backend has answered "who is signed in?", so the page doesn't flash
  // the sign-in form at someone who is already signed in
  const [isCheckingSignIn, setIsCheckingSignIn] = useState(true)
  // a line for the sign-in form, set when the player was signed out without asking to be
  const [notice, setNotice] = useState('')

  // On first load: ask the backend whether this browser has a session, and whose it is.
  useEffect(() => {
    getCurrentUser()
      .then((currentUser) => setUser(currentUser))
      .catch((error) => {
        // Nobody is signed in: stay signed out and show the form. If the reason is that the
        // server could not be reached, say so on the form rather than leaving the visitor
        // to find out when they try to sign in.
        if (error.code === 'NETWORK_ERROR') {
          setNotice(errorText(error))
        }
      })
      .finally(() => setIsCheckingSignIn(false))
  }, [])

  // api.js announces when the backend rejects the token mid-session (it expired, or the
  // account signed out elsewhere). Drop the user so the sign-in form comes back.
  useEffect(() => {
    function handleSignedOut() {
      // This only fires when the page was signed in and the backend then refused the session.
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
      // api.js forgets the CSRF token either way, so this page can no longer act as the player
    }
    setUser(null)
  }

  return { user, isCheckingSignIn, notice, signIn, createAccount, signOut }
}
