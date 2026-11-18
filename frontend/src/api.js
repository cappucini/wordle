const API_URL = 'http://localhost:8000/api/v1'

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

//TODO: add a funcion that list games, add REST filtering in route, then service that works with backend