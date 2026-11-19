// Decides what the player reads when something goes wrong.
// The backend sends a stable code with every error (see api.js); the wording is chosen here,
// so technical details such as "game_id: Input should be a valid UUID" never reach the screen.

const FRIENDLY_MESSAGES = {
  GAME_NOT_FOUND: "That game doesn't exist. Start a new one?",
  GAME_OVER: 'This game has already finished.',
  INVALID_REQUEST: "That link or request isn't valid. Start a new game?",
  NETWORK_ERROR: "Can't reach the game server. Is it running?",
  NOT_AUTHENTICATED: 'Please sign in to continue.',
  INVALID_CREDENTIALS: 'Wrong username or password.',
  USERNAME_TAKEN: 'That username is taken. Try another, or sign in.',
  NOT_A_PLAYER: "You're not a player in that game.",
  GAME_FULL: 'That game already has the maximum number of players.',
  CSRF_CHECK_FAILED: 'This page is out of date. Refresh it and try again.',
  NO_WORDS_AVAILABLE: "The word lists aren't loaded yet. Try again in a moment.",
  TOO_MANY_ATTEMPTS: 'Too many attempts. Wait a few minutes and try again.',
}

// shown for any code that is not in the table above
const FALLBACK_MESSAGE = 'Something went wrong. Please try again.'

// Returns the sentence to show the player for an error thrown by api.js.
export function errorText(error) {
  // Word errors keep the backend's wording, because it names the word and the reason,
  // for example: 'zzzzz' is not in the word list
  if (error.code === 'INVALID_GUESS') {
    return error.message
  }

  // Look up error code in the table of friendly messages. 
  const friendly = FRIENDLY_MESSAGES[error.code]
  // if there is an entry for that code, return that sentence
  if (friendly !== undefined) {
    return friendly
  }
  // otherwise return fallback message
  return FALLBACK_MESSAGE
}
