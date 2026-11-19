// The API is on the same host as the page, on port 8000. Using the page's own hostname matters
// for the session cookie: the browser treats "localhost" and "127.0.0.1" as different sites,
// and only sends the cookie when the page and the API are on the same one.
const API_URL = 'http://' + window.location.hostname + ':8000/api/v1'

// ---- how the page stays signed in ----
// The session itself is a cookie that only the browser and the backend can see; JavaScript
// cannot read it, so there is nothing here to steal. The browser attaches it to each request
// because of `credentials: 'include'` below.
//
// What the page does hold is the CSRF token: a second value the backend hands over at sign-in.
// It is sent back in a header on every request that changes something, which proves the request
// came from this page and not from another website. It lives only in this variable, so a
// refresh forgets it and the page asks the backend for it again (see getCurrentUser).
let csrfToken = null

// the page listens for this to go back to the sign-in form when the backend ends the session
export const SIGNED_OUT_EVENT = 'wordle:signed-out'

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
    // send the session cookie along, and accept one when signing in
    credentials: 'include',
  }
  // requests that change something carry the CSRF token; reading data (GET) doesn't need it
  if (method !== 'GET' && csrfToken !== null) {
    options.headers['X-CSRF-Token'] = csrfToken
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
    if (error.code === 'NOT_AUTHENTICATED' && csrfToken !== null) {
      // The page believed it was signed in, and the backend says the session is gone
      // (it expired, or was signed out elsewhere). Tell the page to show sign-in again.
      // A visitor who was never signed in gets the same 401, but there is nothing to announce.
      csrfToken = null
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
  csrfToken = result.csrf_token
  return result.user
}

// Signs in to an existing account. Returns the user.
export async function login(username, password) {
  const result = await sendRequest('POST', '/sessions', { username: username, password: password })
  csrfToken = result.csrf_token
  return result.user
}

// Ends the session on the server (which also removes the cookie), and forgets the CSRF token
// even if that request fails.
export async function logout() {
  try {
    await sendRequest('DELETE', '/sessions/current')
  } finally {
    csrfToken = null
  }
}

// Asks the backend who is signed in, and picks up the CSRF token for this session.
// The page calls this when it loads, because it has no other way to know: it cannot see
// the cookie. Fails with NOT_AUTHENTICATED when nobody is signed in.
export async function getCurrentUser() {
  const result = await sendRequest('GET', '/users/me')
  csrfToken = result.csrf_token
  return result.user
}
