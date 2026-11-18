const API_URL = 'http://localhost:8000/api/v1'

// ---- sign-in token ----
// After signing in, the backend gives the browser a token. It is kept in localStorage so a
// refresh keeps you signed in, and sent with every request so the backend knows who is asking.
const TOKEN_KEY = 'wordle-auth-token'

// the page listens for this to go back to the sign-in form when the backend rejects the token
export const SIGNED_OUT_EVENT = 'wordle:signed-out'

export function hasSavedToken() {
  return localStorage.getItem(TOKEN_KEY) !== null
}

function saveToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

// Turns the backend's error response into one sentence to show the player.
// Every error looks like: { "code": "GAME_OVER", "detail": "This game is already over" }
function getErrorMessage(body, statusCode) {
  if (body !== null && typeof body.detail === 'string') {
    return body.detail
  }

  // no usable body, for example a plain-text 500 from an unexpected crash
  return `Request failed (${statusCode})`
}


// Reads the response body as JSON. Returns null if there is no valid JSON.
async function readJson(response) {
  try {
    // waits for body to be read and parsed
    return await response.json()
  } catch {
    // handles any parsing filure
    return null
  }
}

// Sends one request to the backend. Every request here goes through the backend/
// Returns the response data, or throws an Error with a readable message.
async function sendRequest(method, path, data) {
  const options = {
    method: method,
    headers: { 'Content-Type': 'application/json' },
  }
  // say who is asking, if someone is signed in
  const token = localStorage.getItem(TOKEN_KEY)
  if (token !== null) {
    options.headers['Authorization'] = 'Bearer ' + token
  }
  // If .data argument is not there, on't 
  if (data !== undefined) {
    // convert to JSON
    options.body = JSON.stringify(data)
  }

  // return a promise as placeholder for result, wait for the server to reply
  let response
  try {
    response = await fetch(API_URL + path, options)
  } catch {
    // fetch itself only fails when no response arrives at all: the backend is down or unreachable.
    // The browser's own wording differs between browsers, so we use our own message and code.
    const error = new Error('Could not reach the server')
    error.code = 'NETWORK_ERROR'
    throw error
  }
  // wait for body to finish downloading to be parsed
  const body = await readJson(response)

  // check the status
  if (!response.ok) {
    const error = new Error(getErrorMessage(body, response.status))
    error.code = body !== null ? body.code : undefined
    error.status = response.status
    if (error.code === 'NOT_AUTHENTICATED') {
      // the token is missing, unknown or expired: forget it and tell the page to show sign-in
      clearToken()
      window.dispatchEvent(new Event(SIGNED_OUT_EVENT))
    }
    throw error
  }

  return body
}

// All 4 functions use the sendRequest() helper
// export makes these functions available when we import within App.jsx

//getConfig retrieves game rules to enable a word-length drop-down that allows users to 
// set the length of the words they want to guess
export function getConfig() {
  return sendRequest('GET', '/config')
}

// retrieves game details
export function getGame(gameId) {
  return sendRequest('GET', '/games/' + gameId)
}

export function createGame(wordLength) {
  return sendRequest('POST', '/games', { word_length: wordLength })
}

export function submitGuess(gameId, word) {
  return sendRequest('POST', '/games/' + gameId + '/guesses', { word_guessed: word })
}

// One page of the signed-in user's games, newest first.
// Pass the next_cursor from the previous page to get the following one.
export function listGames(cursor) {
  let path = '/games?limit=10'
  if (cursor) {
    path += '&cursor=' + encodeURIComponent(cursor)
  }
  return sendRequest('GET', path)
}

// Joins a game as a player and returns it. Used when a shared game link is opened.
// Safe to call for a game you are already in.
export function joinGame(gameId) {
  return sendRequest('POST', '/games/' + gameId + '/players')
}

// ---- accounts ----

// Creates an account and signs in. Returns the user: { id, username }
export async function register(username, password) {
  const result = await sendRequest('POST', '/users', { username: username, password: password })
  saveToken(result.token)
  return result.user
}

// Signs in to an existing account. Returns the user.
export async function login(username, password) {
  const result = await sendRequest('POST', '/sessions', { username: username, password: password })
  saveToken(result.token)
  return result.user
}

// Ends the sign-in on the server, and forgets the token even if that request fails.
export async function logout() {
  try {
    await sendRequest('DELETE', '/sessions/current')
  } finally {
    clearToken()
  }
}

// The user the saved token belongs to. Fails with NOT_AUTHENTICATED if it is no longer valid.
export function getCurrentUser() {
  return sendRequest('GET', '/users/me')
}
