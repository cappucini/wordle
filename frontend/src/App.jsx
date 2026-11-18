import './App.css'
import GameScreen from './GameScreen'
import AuthForm from './components/AuthForm'
import Title from './components/Title'
import { clearGameIdFromUrl } from './gameUrl'
import { useAuth } from './hooks/useAuth'

// The page. It decides between two screens: the sign-in form, or the game.
function App() {
  const {
    // the signed-in player ({ id, username }), or null
    user,
    // true while a saved sign-in is being checked on first load
    isCheckingSignIn,
    // a line shown above the sign-in form when the player was signed out unexpectedly
    notice,
    // functions the sign-in form calls
    signIn,
    createAccount,
    // function called when "Sign out" is clicked
    signOut,
  } = useAuth()

  function handleSignOut() {
    // Forget which game was open. Otherwise the next person to sign in on this browser
    // would be taken to it, and opening a game's link is how a player joins it.
    clearGameIdFromUrl()
    signOut()
  }

  return (
    <main className="app">
      <Title />

      {isCheckingSignIn && <p className="message">Loading...</p>}

      {!isCheckingSignIn && user === null && (
        <AuthForm onSignIn={signIn} onCreateAccount={createAccount} notice={notice} />
      )}

      {/* key={user.id} gives each player a fresh game screen, so signing in as someone else
          never shows the previous player's game for a moment */}
      {!isCheckingSignIn && user !== null && (
        <GameScreen key={user.id} user={user} onSignOut={handleSignOut} />
      )}
    </main>
  )
}

export default App
