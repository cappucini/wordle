// api.js: how the page talks to the backend. The network is replaced by a fake `fetch`,
// so these tests check exactly what would be sent and how each kind of answer is handled.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const API = 'http://localhost:8000/api/v1'

let api
let fetchMock

// A reply from the fake backend.
function reply(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status: status,
    json: async () => {
      if (body === undefined) {
        throw new SyntaxError('no JSON in this response')
      }
      return body
    },
  }
}

// The details of one request the page made: lastRequest() is the most recent.
function request(index) {
  const [url, options] = fetchMock.mock.calls.at(index)
  return {
    url: url,
    method: options.method,
    headers: options.headers,
    credentials: options.credentials,
    body: options.body === undefined ? undefined : JSON.parse(options.body),
  }
}

function lastRequest() {
  return request(-1)
}

async function signIn(csrfToken = 'csrf-123') {
  fetchMock.mockResolvedValueOnce(reply(201, { user: { id: 'u1', username: 'erica' }, csrf_token: csrfToken }))
  return api.login('erica', 'correct horse')
}

beforeEach(async () => {
  // api.js remembers the CSRF token in a module variable; a fresh copy per test forgets it
  vi.resetModules()
  fetchMock = vi.fn().mockResolvedValue(reply(200, {}))
  vi.stubGlobal('fetch', fetchMock)
  api = await import('./api')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api: what each call sends', () => {
  it('reads the config', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { min_word_length: 5 }))

    const config = await api.getConfig()

    expect(config).toEqual({ min_word_length: 5 })
    expect(lastRequest()).toMatchObject({ url: API + '/config', method: 'GET', body: undefined })
  })

  it('creates a game with the chosen word length', async () => {
    await api.createGame(7)

    expect(lastRequest()).toMatchObject({ url: API + '/games', method: 'POST', body: { word_length: 7 } })
  })

  it('reads a game', async () => {
    await api.getGame('game-1')

    expect(lastRequest()).toMatchObject({ url: API + '/games/game-1', method: 'GET' })
  })

  it('submits a guess', async () => {
    await api.submitGuess('game-1', 'crane')

    expect(lastRequest()).toMatchObject({
      url: API + '/games/game-1/guesses',
      method: 'POST',
      body: { word_guessed: 'crane' },
    })
  })

  it('joins a game', async () => {
    await api.joinGame('game-1')

    expect(lastRequest()).toMatchObject({ url: API + '/games/game-1/players', method: 'POST', body: undefined })
  })

  it('lists the first page of games, ten at a time', async () => {
    await api.listGames()

    expect(lastRequest()).toMatchObject({ url: API + '/games?limit=10', method: 'GET' })
  })

  it('can ask for more than ten games at once, to refresh a list that has been expanded', async () => {
    await api.listGames(null, 30)

    expect(lastRequest().url).toBe(API + '/games?limit=30')
  })

  it('lists the next page with the cursor made safe for a URL', async () => {
    await api.listGames('abc+/=')

    expect(lastRequest().url).toBe(API + '/games?limit=10&cursor=abc%2B%2F%3D')
  })

  it('creates an account and returns the user', async () => {
    fetchMock.mockResolvedValueOnce(reply(201, { user: { id: 'u1', username: 'erica' }, csrf_token: 't' }))

    const user = await api.register('erica', 'correct horse')

    expect(user).toEqual({ id: 'u1', username: 'erica' })
    expect(lastRequest()).toMatchObject({
      url: API + '/users',
      method: 'POST',
      body: { username: 'erica', password: 'correct horse' },
    })
  })

  it('signs in and returns the user', async () => {
    const user = await signIn()

    expect(user).toEqual({ id: 'u1', username: 'erica' })
    expect(lastRequest()).toMatchObject({
      url: API + '/sessions',
      method: 'POST',
      body: { username: 'erica', password: 'correct horse' },
    })
  })

  it('labels the body as JSON only when it sends one', async () => {
    await api.getConfig()
    await api.joinGame('game-1')
    await api.createGame(5)

    // a GET or a POST with nothing in it has no body to describe; leaving the header off
    // also spares the browser an extra "may I?" request before every read
    expect(request(0).headers).not.toHaveProperty('Content-Type')
    expect(request(1).headers).not.toHaveProperty('Content-Type')
    expect(request(2).headers['Content-Type']).toBe('application/json')
  })

  it('always sends the session cookie along', async () => {
    await api.getConfig()
    await api.createGame(5)

    expect(request(0).credentials).toBe('include')
    expect(request(1).credentials).toBe('include')
  })
})

describe('api: the live-update connection', () => {
  it("opens a WebSocket to the game's address on the backend", () => {
    const opened = []
    vi.stubGlobal(
      'WebSocket',
      class {
        constructor(url) {
          opened.push(url)
        }
      },
    )

    api.openGameSocket('game-1')

    expect(opened).toEqual(['ws://localhost:8000/api/v1/games/game-1/ws'])
  })

  it('knows the codes the backend closes a refused connection with', () => {
    expect(api.SOCKET_CLOSED_NOT_AUTHENTICATED).toBe(4401)
    expect(api.SOCKET_CLOSED_NOT_A_PLAYER).toBe(4403)
    expect(api.SOCKET_CLOSED_GAME_NOT_FOUND).toBe(4404)
  })
})

describe('api: the CSRF token', () => {
  it('is not sent before signing in', async () => {
    await api.createGame(5)

    expect(lastRequest().headers).not.toHaveProperty('X-CSRF-Token')
  })

  it('is sent on requests that change something after signing in', async () => {
    await signIn('csrf-123')

    await api.createGame(5)
    expect(lastRequest().headers['X-CSRF-Token']).toBe('csrf-123')
    await api.submitGuess('game-1', 'crane')
    expect(lastRequest().headers['X-CSRF-Token']).toBe('csrf-123')
    await api.joinGame('game-1')
    expect(lastRequest().headers['X-CSRF-Token']).toBe('csrf-123')
  })

  it('is not sent on requests that only read', async () => {
    await signIn()

    await api.getGame('game-1')
    expect(lastRequest().headers).not.toHaveProperty('X-CSRF-Token')
    await api.listGames()
    expect(lastRequest().headers).not.toHaveProperty('X-CSRF-Token')
  })

  it('is picked up again after a refresh, from "who is signed in?"', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { user: { id: 'u1', username: 'erica' }, csrf_token: 'after-refresh' }))

    const user = await api.getCurrentUser()
    await api.createGame(5)

    expect(user).toEqual({ id: 'u1', username: 'erica' })
    expect(request(0)).toMatchObject({ url: API + '/users/me', method: 'GET' })
    expect(lastRequest().headers['X-CSRF-Token']).toBe('after-refresh')
  })

  it('is also given at sign-up', async () => {
    fetchMock.mockResolvedValueOnce(reply(201, { user: { id: 'u1', username: 'erica' }, csrf_token: 'from-sign-up' }))
    await api.register('erica', 'correct horse')

    await api.createGame(5)

    expect(lastRequest().headers['X-CSRF-Token']).toBe('from-sign-up')
  })

  it('is sent with the sign-out request and then forgotten', async () => {
    await signIn('csrf-123')
    fetchMock.mockResolvedValueOnce(reply(204))

    await api.logout()

    expect(lastRequest()).toMatchObject({ url: API + '/sessions/current', method: 'DELETE' })
    expect(lastRequest().headers['X-CSRF-Token']).toBe('csrf-123')
    await api.createGame(5)
    expect(lastRequest().headers).not.toHaveProperty('X-CSRF-Token')
  })

  it('is forgotten even when the sign-out request fails', async () => {
    await signIn('csrf-123')
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    await expect(api.logout()).rejects.toMatchObject({ code: 'NETWORK_ERROR' })

    await api.createGame(5)
    expect(lastRequest().headers).not.toHaveProperty('X-CSRF-Token')
  })
})

describe('api: when something goes wrong', () => {
  it("turns the backend's error into an Error with its code, message and status", async () => {
    fetchMock.mockResolvedValueOnce(reply(409, { code: 'GAME_OVER', detail: 'This game is already over' }))

    await expect(api.submitGuess('game-1', 'crane')).rejects.toMatchObject({
      message: 'This game is already over',
      code: 'GAME_OVER',
      status: 409,
    })
  })

  it('copes with an error that is not JSON, such as a crash page', async () => {
    fetchMock.mockResolvedValueOnce(reply(500))

    const error = await api.getGame('game-1').catch((caught) => caught)

    expect(error.message).toBe('Request failed (500)')
    expect(error.code).toBeUndefined()
    expect(error.status).toBe(500)
  })

  it('reports an unreachable server in its own words, whatever the browser says', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    await expect(api.getConfig()).rejects.toMatchObject({
      message: 'Could not reach the server',
      code: 'NETWORK_ERROR',
    })
  })

  it('copes with a successful answer that has no body', async () => {
    await signIn()
    fetchMock.mockResolvedValueOnce(reply(204))

    await expect(api.logout()).resolves.toBeUndefined()
  })
})

describe('api: when the backend ends the session', () => {
  const NOT_AUTHENTICATED = { code: 'NOT_AUTHENTICATED', detail: 'Your sign-in has expired. Sign in again' }

  function listenForSignedOut() {
    const listener = vi.fn()
    window.addEventListener(api.SIGNED_OUT_EVENT, listener)
    return listener
  }

  it('announces it to the page and forgets the CSRF token', async () => {
    await signIn('csrf-123')
    const listener = listenForSignedOut()
    fetchMock.mockResolvedValueOnce(reply(401, NOT_AUTHENTICATED))

    await expect(api.getGame('game-1')).rejects.toMatchObject({ code: 'NOT_AUTHENTICATED', status: 401 })

    expect(listener).toHaveBeenCalledOnce()
    await api.createGame(5)
    expect(lastRequest().headers).not.toHaveProperty('X-CSRF-Token')
    window.removeEventListener(api.SIGNED_OUT_EVENT, listener)
  })

  it('announces it only once, however many requests fail afterwards', async () => {
    await signIn()
    const listener = listenForSignedOut()
    fetchMock.mockResolvedValue(reply(401, NOT_AUTHENTICATED))

    await api.getGame('game-1').catch(() => {})
    await api.listGames().catch(() => {})

    expect(listener).toHaveBeenCalledOnce()
    window.removeEventListener(api.SIGNED_OUT_EVENT, listener)
  })

  it('announces nothing for a visitor who was never signed in', async () => {
    const listener = listenForSignedOut()
    fetchMock.mockResolvedValueOnce(reply(401, NOT_AUTHENTICATED))

    await expect(api.getCurrentUser()).rejects.toMatchObject({ code: 'NOT_AUTHENTICATED' })

    expect(listener).not.toHaveBeenCalled()
    window.removeEventListener(api.SIGNED_OUT_EVENT, listener)
  })

  it('announces nothing for other errors', async () => {
    await signIn()
    const listener = listenForSignedOut()
    fetchMock.mockResolvedValueOnce(reply(403, { code: 'NOT_A_PLAYER', detail: 'You are not a player in this game' }))

    await api.getGame('game-1').catch(() => {})

    expect(listener).not.toHaveBeenCalled()
    window.removeEventListener(api.SIGNED_OUT_EVENT, listener)
  })
})
