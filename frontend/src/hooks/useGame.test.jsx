// useGame: the game screen's state and actions. The backend is replaced by fakes (api.js is
// mocked), so each test decides what the "server" answers and checks what the hook does with it.
import { act, fireEvent, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import { CONFIG, ERICA, SAM, apiError, makeGame, makeGuess } from '../test/factories'
import { useGame } from './useGame'

vi.mock('../api')

const NEW_GAME = makeGame({ id: 'game-1' })

beforeEach(() => {
  api.getConfig.mockResolvedValue(CONFIG)
  api.listGames.mockResolvedValue({ items: [], next_cursor: null })
  api.createGame.mockResolvedValue(NEW_GAME)
  api.joinGame.mockResolvedValue(NEW_GAME)
  api.getGame.mockResolvedValue(NEW_GAME)
  api.submitGuess.mockResolvedValue({})
  // a connection that never says anything, for the tests that are not about live updates
  api.openGameSocket.mockImplementation(() => ({ close() {} }))
})

afterEach(() => {
  vi.useRealTimers()
})

// Renders the hook and waits until it has loaded the rules.
async function renderGame() {
  const rendered = renderHook(() => useGame())
  await waitFor(() => expect(rendered.result.current.config).not.toBeNull())
  return rendered.result
}

// Renders the hook and starts a new game, as clicking "New game" does.
async function renderStartedGame() {
  const result = await renderGame()
  await act(() => result.current.startGame())
  return result
}

async function press(result, ...keys) {
  for (const key of keys) {
    await act(() => result.current.pressKey(key))
  }
}

async function type(result, word) {
  await press(result, ...word.split(''))
}

describe('useGame: loading', () => {
  it('loads the rules and starts with the default word length', async () => {
    api.getConfig.mockResolvedValue({ ...CONFIG, default_word_length: 6 })

    const result = await renderGame()

    expect(result.current.config.max_word_length).toBe(8)
    expect(result.current.wordLength).toBe(6)
    expect(result.current.game).toBeNull()
  })

  it('shows a message when the rules cannot be loaded', async () => {
    api.getConfig.mockRejectedValue(apiError('NETWORK_ERROR'))

    const { result } = renderHook(() => useGame())

    await waitFor(() => expect(result.current.message).toBe("Can't reach the game server. Is it running?"))
    expect(result.current.config).toBeNull()
  })

  it('loads the first page of "Your games"', async () => {
    api.listGames.mockResolvedValue({ items: [makeGame({ id: 'old' })], next_cursor: 'next' })

    const result = await renderGame()

    await waitFor(() => expect(result.current.games).toHaveLength(1))
    expect(result.current.hasMoreGames).toBe(true)
  })

  it('adds the next page to the end of "Your games"', async () => {
    api.listGames.mockResolvedValueOnce({ items: [makeGame({ id: 'a' })], next_cursor: 'cursor-1' })
    const result = await renderGame()
    await waitFor(() => expect(result.current.hasMoreGames).toBe(true))
    api.listGames.mockResolvedValueOnce({ items: [makeGame({ id: 'b' })], next_cursor: null })

    await act(async () => result.current.loadMoreGames())

    expect(api.listGames).toHaveBeenLastCalledWith('cursor-1')
    expect(result.current.games.map((game) => game.id)).toEqual(['a', 'b'])
    expect(result.current.hasMoreGames).toBe(false)
  })
})

describe('useGame: opening a game from the address', () => {
  it('joins the game named in the address and shows it', async () => {
    window.history.replaceState({}, '', '/?game=game-1')

    const result = await renderGame()

    await waitFor(() => expect(result.current.game).toEqual(NEW_GAME))
    expect(api.joinGame).toHaveBeenCalledWith('game-1')
    expect(result.current.isLoadingGame).toBe(false)
  })

  it.each([
    ['GAME_FULL', 'That game already has the maximum number of players.'],
    ['GAME_NOT_FOUND', "That game doesn't exist. Start a new one?"],
    ['GAME_OVER', 'This game has already finished.'],
    ['INVALID_REQUEST', "That link or request isn't valid. Start a new game?"],
  ])('explains a %s link and takes it out of the address', async (code, text) => {
    window.history.replaceState({}, '', '/?game=some-game')
    api.joinGame.mockRejectedValue(apiError(code))

    const result = await renderGame()

    await waitFor(() => expect(result.current.message).toBe(text))
    expect(result.current.game).toBeNull()
    expect(window.location.search).toBe('')
  })

  it('opens another game from the list and puts it in the address', async () => {
    const other = makeGame({ id: 'game-2' })
    const result = await renderStartedGame()
    api.joinGame.mockResolvedValue(other)

    await act(async () => result.current.openGame('game-2'))

    expect(result.current.game).toEqual(other)
    expect(window.location.search).toBe('?game=game-2')
  })
})

describe('useGame: starting a game', () => {
  it('creates a game of the chosen length and puts it in the address', async () => {
    const result = await renderGame()
    act(() => result.current.setWordLength(7))

    await act(() => result.current.startGame())

    expect(api.createGame).toHaveBeenCalledExactlyOnceWith(7)
    expect(result.current.game).toEqual(NEW_GAME)
    expect(window.location.search).toBe('?game=game-1')
  })

  it('creates only one game when the button is double-clicked', async () => {
    const result = await renderGame()

    await act(async () => {
      result.current.startGame()
      await result.current.startGame()
    })

    expect(api.createGame).toHaveBeenCalledOnce()
  })

  it('shows a message when the game cannot be created', async () => {
    api.createGame.mockRejectedValue(apiError('NO_WORDS_AVAILABLE'))
    const result = await renderGame()

    await act(() => result.current.startGame())

    expect(result.current.message).toBe("The word lists aren't loaded yet. Try again in a moment.")
    expect(result.current.game).toBeNull()
  })
})

describe('useGame: typing', () => {
  it('adds letters, in lowercase', async () => {
    const result = await renderStartedGame()

    await press(result, 'c', 'R', 'a')

    expect(result.current.typedWord).toBe('cra')
  })

  it('stops at the length of the word', async () => {
    const result = await renderStartedGame()

    await type(result, 'cranes')

    expect(result.current.typedWord).toBe('crane')
  })

  it('removes the last letter on Backspace', async () => {
    const result = await renderStartedGame()

    await type(result, 'cra')
    await press(result, 'Backspace')

    expect(result.current.typedWord).toBe('cr')
  })

  it('ignores keys that are not letters', async () => {
    const result = await renderStartedGame()

    await press(result, 'c', '1', ' ', 'Shift', 'Tab', 'é', '-', 'r')

    expect(result.current.typedWord).toBe('cr')
  })

  it('keeps every letter when keys arrive faster than the screen redraws', async () => {
    const result = await renderStartedGame()

    // all five in one go, with no redraw in between
    await act(async () => {
      for (const letter of 'crane') {
        result.current.pressKey(letter)
      }
    })

    expect(result.current.typedWord).toBe('crane')
  })

  it('ignores keys before a game has started', async () => {
    const result = await renderGame()

    await press(result, 'c', 'Enter')

    expect(result.current.typedWord).toBe('')
    expect(api.submitGuess).not.toHaveBeenCalled()
  })

  it('listens to the physical keyboard', async () => {
    const result = await renderStartedGame()

    await act(async () => {
      fireEvent.keyDown(window, { key: 'c' })
    })
    await act(async () => {
      fireEvent.keyDown(window, { key: 'r' })
    })

    expect(result.current.typedWord).toBe('cr')
  })

  it.each(['ctrlKey', 'metaKey', 'altKey'])('leaves browser shortcuts alone (%s held)', async (modifier) => {
    const result = await renderStartedGame()

    await act(async () => {
      fireEvent.keyDown(window, { key: 'r', [modifier]: true })
    })

    expect(result.current.typedWord).toBe('')
  })

  it('lets a focused button handle its own Enter', async () => {
    const result = await renderStartedGame()
    await type(result, 'crane')
    const button = document.createElement('button')
    document.body.appendChild(button)

    await act(async () => {
      fireEvent.keyDown(button, { key: 'Enter' })
    })

    expect(api.submitGuess).not.toHaveBeenCalled()
    button.remove()
  })
})

describe('useGame: submitting a guess', () => {
  it('refuses a word that is too short without asking the server', async () => {
    const result = await renderStartedGame()

    await type(result, 'cra')
    await press(result, 'Enter')

    expect(result.current.message).toBe('Not enough letters')
    expect(result.current.rowHasProblem).toBe(true)
    expect(result.current.typedWord).toBe('cra')
    expect(api.submitGuess).not.toHaveBeenCalled()
  })

  it('clears the "not enough letters" message on the next key', async () => {
    const result = await renderStartedGame()
    await type(result, 'cra')
    await press(result, 'Enter')

    await press(result, 'n')

    expect(result.current.message).toBe('')
    expect(result.current.rowHasProblem).toBe(false)
  })

  it('sends a full word, then reloads the game and clears the row', async () => {
    const afterGuess = makeGame({ id: 'game-1', guesses: [makeGuess('slate', 'AACAC')] })
    const result = await renderStartedGame()
    api.getGame.mockResolvedValue(afterGuess)

    await type(result, 'slate')
    await press(result, 'Enter')

    expect(api.submitGuess).toHaveBeenCalledExactlyOnceWith('game-1', 'slate')
    expect(result.current.game).toEqual(afterGuess)
    expect(result.current.typedWord).toBe('')
    expect(result.current.message).toBe('')
  })

  it('keeps the letters and flags the row when the word is rejected', async () => {
    const result = await renderStartedGame()
    api.submitGuess.mockRejectedValue(apiError('INVALID_GUESS', "'zzzzz' is not in the word list"))

    await type(result, 'zzzzz')
    await press(result, 'Enter')

    expect(result.current.message).toBe("'zzzzz' is not in the word list")
    expect(result.current.rowHasProblem).toBe(true)
    expect(result.current.typedWord).toBe('zzzzz')
    expect(result.current.game).toEqual(NEW_GAME)
  })

  it('lets the player fix a rejected word and send it again', async () => {
    const result = await renderStartedGame()
    api.submitGuess.mockRejectedValueOnce(apiError('INVALID_GUESS', "'crana' is not in the word list"))
    await type(result, 'crana')
    await press(result, 'Enter')

    api.submitGuess.mockResolvedValueOnce({})
    await press(result, 'Backspace', 'e', 'Enter')

    expect(api.submitGuess).toHaveBeenLastCalledWith('game-1', 'crane')
    expect(result.current.rowHasProblem).toBe(false)
  })

  it('sends the guess once when Enter is pressed twice quickly', async () => {
    const result = await renderStartedGame()
    await type(result, 'crane')

    await act(async () => {
      result.current.pressKey('Enter')
      await result.current.pressKey('Enter')
    })

    expect(api.submitGuess).toHaveBeenCalledOnce()
  })

  it('shows the final board when someone else already finished the game', async () => {
    const finished = makeGame({ id: 'game-1', status: 'won', answer: 'crane', guesses: [makeGuess('crane', 'CCCCC', 'sam')] })
    const result = await renderStartedGame()
    api.submitGuess.mockRejectedValue(apiError('GAME_OVER'))
    api.getGame.mockResolvedValue(finished)

    await type(result, 'slate')
    await press(result, 'Enter')

    expect(result.current.message).toBe('This game has already finished.')
    expect(result.current.game).toEqual(finished)
    expect(result.current.typedWord).toBe('')
    expect(result.current.rowHasProblem).toBe(false)
  })

  it('does not flag the row for an error that is not about the word', async () => {
    const result = await renderStartedGame()
    api.submitGuess.mockRejectedValue(apiError('NETWORK_ERROR'))

    await type(result, 'crane')
    await press(result, 'Enter')

    expect(result.current.message).toBe("Can't reach the game server. Is it running?")
    expect(result.current.rowHasProblem).toBe(false)
    expect(result.current.typedWord).toBe('crane')
  })

  it('cannot resend a saved guess when reloading the game fails', async () => {
    const result = await renderStartedGame()
    api.getGame.mockRejectedValue(apiError('NETWORK_ERROR'))

    await type(result, 'crane')
    await press(result, 'Enter')

    expect(result.current.typedWord).toBe('')
    await press(result, 'Enter')
    expect(api.submitGuess).toHaveBeenCalledOnce()
  })

  it('ignores every key once the game is over', async () => {
    api.createGame.mockResolvedValue(makeGame({ id: 'game-1', status: 'lost', answer: 'crane' }))
    const result = await renderStartedGame()

    await type(result, 'crane')
    await press(result, 'Enter')

    expect(result.current.typedWord).toBe('')
    expect(api.submitGuess).not.toHaveBeenCalled()
  })
})

// Stands in for the browser's WebSocket. The test plays the server: it decides when the
// connection opens, when a notice arrives, and when (and with what code) it closes.
class FakeSocket {
  static opened = []

  constructor(gameId) {
    this.gameId = gameId
    this.isClosed = false
    FakeSocket.opened.push(this)
  }

  close() {
    this.isClosed = true
  }

  // --- what the "server" does ---
  async serverAccepts() {
    await act(async () => this.onopen())
  }

  async serverSaysGameChanged() {
    await act(async () => this.onmessage({ data: '{"type":"game_updated"}' }))
  }

  async serverCloses(code = 1006) {
    await act(async () => this.onclose({ code: code }))
  }
}

function latestSocket() {
  return FakeSocket.opened.at(-1)
}

describe("useGame: other players' guesses", () => {
  const SHARED = makeGame({ id: 'game-1', players: [ERICA, SAM] })
  const WITH_SAMS_GUESS = { ...SHARED, guesses: [makeGuess('slate', 'AACAC', 'sam')] }

  beforeEach(() => {
    FakeSocket.opened = []
    api.openGameSocket.mockImplementation((gameId) => new FakeSocket(gameId))
  })

  // Starts a shared game and lets its connection open.
  async function renderSharedGame() {
    api.createGame.mockResolvedValue(SHARED)
    const result = await renderStartedGame()
    await latestSocket().serverAccepts()
    api.getGame.mockClear()
    return result
  }

  it('opens a connection for the game on screen', async () => {
    await renderStartedGame()

    expect(api.openGameSocket).toHaveBeenCalledExactlyOnceWith('game-1')
  })

  it('opens no connection when there is no game', async () => {
    await renderGame()

    expect(api.openGameSocket).not.toHaveBeenCalled()
  })

  it('opens no connection for a game that is already over', async () => {
    api.createGame.mockResolvedValue(makeGame({ id: 'game-1', status: 'won', answer: 'crane' }))

    await renderStartedGame()

    expect(api.openGameSocket).not.toHaveBeenCalled()
  })

  it("shows another player's guess when the server says the game changed", async () => {
    const result = await renderSharedGame()
    api.getGame.mockResolvedValue(WITH_SAMS_GUESS)

    await latestSocket().serverSaysGameChanged()

    expect(api.getGame).toHaveBeenCalledExactlyOnceWith('game-1')
    expect(result.current.game.guesses).toHaveLength(1)
    expect(result.current.game.guesses[0].guessed_by).toBe('sam')
  })

  it('asks for nothing while the server is silent', async () => {
    vi.useFakeTimers()
    api.createGame.mockResolvedValue(SHARED)
    const { result } = renderHook(() => useGame())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(() => result.current.startGame())
    await latestSocket().serverAccepts()
    api.getGame.mockClear()

    // a minute passes with no notice: the old 3-second check would have asked 20 times
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })

    expect(api.getGame).not.toHaveBeenCalled()
  })

  it('looks for missed changes as soon as the connection opens', async () => {
    api.createGame.mockResolvedValue(SHARED)
    const result = await renderStartedGame()
    api.getGame.mockResolvedValue(WITH_SAMS_GUESS) // guessed before this page was connected

    await latestSocket().serverAccepts()

    expect(result.current.game.guesses).toHaveLength(1)
  })

  it('keeps the letters being typed when the board updates', async () => {
    const result = await renderSharedGame()
    await type(result, 'cr')
    api.getGame.mockResolvedValue(WITH_SAMS_GUESS)

    await latestSocket().serverSaysGameChanged()

    expect(result.current.typedWord).toBe('cr')
    expect(result.current.game.guesses).toHaveLength(1)
  })

  it('never replaces the board with an older copy of itself', async () => {
    const result = await renderSharedGame()
    api.getGame.mockResolvedValue(WITH_SAMS_GUESS)
    await latestSocket().serverSaysGameChanged()

    api.getGame.mockResolvedValue(SHARED) // a late answer from before the guess
    await latestSocket().serverSaysGameChanged()

    expect(result.current.game.guesses).toHaveLength(1)
  })

  it('shows a newly joined player', async () => {
    api.createGame.mockResolvedValue(NEW_GAME) // erica alone
    const result = await renderStartedGame()
    await latestSocket().serverAccepts()
    api.getGame.mockResolvedValue(SHARED)

    await latestSocket().serverSaysGameChanged()

    expect(result.current.game.players).toHaveLength(2)
  })

  it('shrugs off an update that fails and catches up on the next one', async () => {
    const result = await renderSharedGame()
    api.getGame.mockRejectedValueOnce(apiError('NETWORK_ERROR'))
    await latestSocket().serverSaysGameChanged()
    expect(result.current.message).toBe('')

    api.getGame.mockResolvedValue(WITH_SAMS_GUESS)
    await latestSocket().serverSaysGameChanged()

    expect(result.current.game.guesses).toHaveLength(1)
  })

  it('closes the connection once the game is over', async () => {
    const result = await renderSharedGame()
    const socket = latestSocket()
    api.getGame.mockResolvedValue({ ...SHARED, status: 'won', answer: 'crane', guesses: [makeGuess('crane', 'CCCCC', 'sam')] })

    await socket.serverSaysGameChanged()

    expect(result.current.game.status).toBe('won')
    expect(socket.isClosed).toBe(true)
    expect(FakeSocket.opened).toHaveLength(1) // and does not open another
  })

  it('closes the connection when the page goes away', async () => {
    api.createGame.mockResolvedValue(SHARED)
    const rendered = renderHook(() => useGame())
    await waitFor(() => expect(rendered.result.current.config).not.toBeNull())
    await act(() => rendered.result.current.startGame())
    const socket = latestSocket()

    rendered.unmount()

    expect(socket.isClosed).toBe(true)
  })

  it('swaps to a new connection when the player opens another game', async () => {
    const result = await renderSharedGame()
    const first = latestSocket()
    api.joinGame.mockResolvedValue(makeGame({ id: 'game-2' }))

    await act(async () => result.current.openGame('game-2'))

    expect(first.isClosed).toBe(true)
    expect(latestSocket().gameId).toBe('game-2')
    expect(FakeSocket.opened.filter((socket) => !socket.isClosed)).toHaveLength(1)
  })

  describe('when the connection drops', () => {
    // the clock is faked before the game starts, so the reconnect timer can be stepped through
    async function renderSharedGameWithFakeClock() {
      vi.useFakeTimers()
      api.createGame.mockResolvedValue(SHARED)
      const { result } = renderHook(() => useGame())
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0) // let the rules and the games list arrive
      })
      await act(() => result.current.startGame())
      await latestSocket().serverAccepts()
      api.getGame.mockClear()
      return result
    }

    async function wait(milliseconds) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(milliseconds)
      })
    }

    it('reconnects after a second', async () => {
      await renderSharedGameWithFakeClock()

      await latestSocket().serverCloses()
      await wait(999)
      expect(FakeSocket.opened).toHaveLength(1)
      await wait(1)

      expect(FakeSocket.opened).toHaveLength(2)
      expect(latestSocket().gameId).toBe('game-1')
    })

    it('catches up on what it missed once reconnected', async () => {
      const result = await renderSharedGameWithFakeClock()
      await latestSocket().serverCloses()
      api.getGame.mockResolvedValue(WITH_SAMS_GUESS) // sam guessed while this page was offline
      await wait(1000)

      await latestSocket().serverAccepts()

      expect(result.current.game.guesses).toHaveLength(1)
    })

    it('waits longer after each failed attempt, up to ten seconds', async () => {
      await renderSharedGameWithFakeClock()

      const waits = []
      for (let attempt = 0; attempt < 6; attempt++) {
        await latestSocket().serverCloses()
        const before = FakeSocket.opened.length
        let waited = 0
        while (FakeSocket.opened.length === before) {
          await wait(1000)
          waited += 1000
        }
        waits.push(waited)
      }

      expect(waits).toEqual([1000, 2000, 4000, 8000, 10000, 10000])
    })

    it('goes back to a one-second wait after a successful reconnect', async () => {
      await renderSharedGameWithFakeClock()
      await latestSocket().serverCloses()
      await wait(1000)
      await latestSocket().serverCloses() // second failure in a row: next wait is 2 seconds
      await wait(2000)
      await latestSocket().serverAccepts() // connected again

      await latestSocket().serverCloses()
      await wait(1000)

      expect(FakeSocket.opened).toHaveLength(4)
    })

    it('does not reconnect after the page has gone away', async () => {
      vi.useFakeTimers()
      api.createGame.mockResolvedValue(SHARED)
      const rendered = renderHook(() => useGame())
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      await act(() => rendered.result.current.startGame())
      await latestSocket().serverCloses()

      rendered.unmount()
      await wait(20_000)

      expect(FakeSocket.opened).toHaveLength(1)
    })

    it.each([
      [4403, 'not a player in the game'],
      [4404, 'the game does not exist'],
    ])('does not retry when the server refused with %i (%s)', async (code) => {
      await renderSharedGameWithFakeClock()

      await latestSocket().serverCloses(code)
      await wait(60_000)

      expect(FakeSocket.opened).toHaveLength(1)
      expect(api.getGame).not.toHaveBeenCalled()
    })

    it('does not retry when the sign-in has ended, and lets the page find that out', async () => {
      await renderSharedGameWithFakeClock()
      api.getGame.mockRejectedValue(apiError('NOT_AUTHENTICATED'))

      await latestSocket().serverCloses(4401)
      await wait(60_000)

      expect(FakeSocket.opened).toHaveLength(1)
      // this request is what makes api.js send the player back to the sign-in form
      expect(api.getGame).toHaveBeenCalledExactlyOnceWith('game-1')
    })
  })
})

// A fake backend holding a player's games, which pages through them the way the real one
// does: `limit` games at a time, with a cursor to continue from.
function serveGames(allGames) {
  api.listGames.mockImplementation(async (cursor, limit = 10) => {
    const start = cursor ? Number(cursor) : 0
    const end = start + limit
    return {
      items: allGames.slice(start, end),
      next_cursor: end < allGames.length ? String(end) : null,
    }
  })
}

function manyGames(count) {
  return Array.from({ length: count }, (_, index) => makeGame({ id: 'old-' + (index + 1) }))
}

function listedIds(result) {
  return result.current.games.map((game) => game.id)
}

describe('useGame: "Your games" after Show more', () => {
  async function renderWithTwoPagesShown(allGames) {
    serveGames(allGames)
    const result = await renderGame()
    await waitFor(() => expect(result.current.games).toHaveLength(10))
    await act(async () => result.current.loadMoreGames())
    expect(result.current.games).toHaveLength(20)
    return result
  }

  it('keeps the extra pages when a guess refreshes the list', async () => {
    const allGames = manyGames(25)
    const result = await renderWithTwoPagesShown(allGames)
    await act(() => result.current.startGame())
    api.getGame.mockResolvedValue(makeGame({ id: 'game-1', guesses: [makeGuess('slate', 'AACAC')] }))

    await type(result, 'slate')
    await press(result, 'Enter')

    expect(listedIds(result)).toEqual(allGames.slice(0, 20).map((game) => game.id))
    expect(result.current.hasMoreGames).toBe(true)
  })

  it('puts a new game at the top without dropping back to one page', async () => {
    const allGames = manyGames(25)
    const result = await renderWithTwoPagesShown(allGames)
    allGames.unshift(NEW_GAME) // the backend lists the newest game first

    await act(() => result.current.startGame())

    expect(result.current.games).toHaveLength(20)
    expect(listedIds(result)[0]).toBe('game-1')
    expect(listedIds(result).slice(1)).toEqual(allGames.slice(1, 20).map((game) => game.id))
    // the game pushed off the end is still reachable
    expect(result.current.hasMoreGames).toBe(true)
  })

  it('still shows one page when the player never asked for more', async () => {
    serveGames(manyGames(25))
    const result = await renderGame()
    await waitFor(() => expect(result.current.games).toHaveLength(10))

    await act(() => result.current.startGame())

    expect(result.current.games).toHaveLength(10)
  })

  it('adds the next page once when "Show more" is double-clicked', async () => {
    const allGames = manyGames(25)
    serveGames(allGames)
    const result = await renderGame()
    await waitFor(() => expect(result.current.games).toHaveLength(10))

    await act(async () => {
      result.current.loadMoreGames()
      result.current.loadMoreGames()
    })

    expect(listedIds(result)).toEqual(allGames.slice(0, 20).map((game) => game.id))
    const requestsForMore = api.listGames.mock.calls.filter(([cursor]) => cursor)
    expect(requestsForMore).toHaveLength(1)
  })

  it('can load a third page after the second', async () => {
    const allGames = manyGames(25)
    const result = await renderWithTwoPagesShown(allGames)

    await act(async () => result.current.loadMoreGames())

    expect(listedIds(result)).toEqual(allGames.map((game) => game.id))
    expect(result.current.hasMoreGames).toBe(false)
  })

  it('never lists a game twice when the list refreshes while the next page is loading', async () => {
    const allGames = manyGames(25)
    serveGames(allGames)
    const result = await renderGame()
    await waitFor(() => expect(result.current.games).toHaveLength(10))

    await act(async () => {
      result.current.loadMoreGames()
      await result.current.startGame() // refreshes the list while page two is on its way
    })

    expect(new Set(listedIds(result)).size).toBe(result.current.games.length)
  })

  it('"Show more" works again after a request for more fails', async () => {
    const allGames = manyGames(25)
    serveGames(allGames)
    const result = await renderGame()
    await waitFor(() => expect(result.current.games).toHaveLength(10))
    api.listGames.mockRejectedValueOnce(apiError('NETWORK_ERROR'))
    await act(async () => result.current.loadMoreGames())
    expect(result.current.games).toHaveLength(10)

    await act(async () => result.current.loadMoreGames())

    expect(result.current.games).toHaveLength(20)
  })
})

describe('useGame: a slow answer never replaces the game on screen', () => {
  // a request the test finishes by hand, to control which answer arrives last
  function pending() {
    let finish
    const promise = new Promise((resolve, reject) => {
      finish = { with: resolve, failingWith: reject }
    })
    return { promise, finish }
  }

  it('stays on the new game when a linked game finishes loading afterwards', async () => {
    window.history.replaceState({}, '', '/?game=linked')
    const slowJoin = pending()
    api.joinGame.mockReturnValue(slowJoin.promise)
    api.createGame.mockResolvedValue(makeGame({ id: 'brand-new' }))
    const result = await renderGame()

    await act(() => result.current.startGame()) // clicked before the linked game arrived
    await act(async () => slowJoin.finish.with(makeGame({ id: 'linked' })))

    expect(result.current.game.id).toBe('brand-new')
    expect(window.location.search).toBe('?game=brand-new')
    expect(result.current.isLoadingGame).toBe(false)
  })

  it('does not show an error from a linked game that failed after a new game started', async () => {
    window.history.replaceState({}, '', '/?game=linked')
    const slowJoin = pending()
    api.joinGame.mockReturnValue(slowJoin.promise)
    api.createGame.mockResolvedValue(makeGame({ id: 'brand-new' }))
    const result = await renderGame()

    await act(() => result.current.startGame())
    await act(async () => slowJoin.finish.failingWith(apiError('GAME_FULL')))

    expect(result.current.game.id).toBe('brand-new')
    expect(result.current.message).toBe('')
    expect(window.location.search).toBe('?game=brand-new')
  })

  it('stays on the game picked from the list when a slower "New game" finishes afterwards', async () => {
    const slowCreate = pending()
    api.createGame.mockReturnValue(slowCreate.promise)
    api.joinGame.mockResolvedValue(makeGame({ id: 'picked' }))
    const result = await renderGame()

    await act(async () => {
      result.current.startGame()
    })
    await act(async () => result.current.openGame('picked')) // the player's latest choice
    await act(async () => slowCreate.finish.with(makeGame({ id: 'brand-new' })))

    expect(result.current.game.id).toBe('picked')
    expect(window.location.search).toBe('?game=picked')
  })

  it('stays on game B when the reload after a guess in game A arrives late', async () => {
    api.createGame.mockResolvedValue(makeGame({ id: 'A' }))
    const result = await renderStartedGame()
    await type(result, 'slate')
    const slowReload = pending()
    api.getGame.mockReturnValue(slowReload.promise)
    api.joinGame.mockResolvedValue(makeGame({ id: 'B' }))

    await act(async () => {
      result.current.pressKey('Enter')
    })
    await act(async () => result.current.openGame('B'))
    await type(result, 'cr') // already typing in game B
    await act(async () => slowReload.finish.with(makeGame({ id: 'A', guesses: [makeGuess('slate', 'AACAC')] })))

    expect(result.current.game.id).toBe('B')
    expect(window.location.search).toBe('?game=B')
    expect(result.current.typedWord).toBe('cr')
  })

  it('does not wipe what is being typed in game B when the guess in game A is saved late', async () => {
    api.createGame.mockResolvedValue(makeGame({ id: 'A' }))
    const result = await renderStartedGame()
    await type(result, 'slate')
    const slowGuess = pending()
    api.submitGuess.mockReturnValue(slowGuess.promise)
    api.joinGame.mockResolvedValue(makeGame({ id: 'B' }))

    await act(async () => {
      result.current.pressKey('Enter')
    })
    await act(async () => result.current.openGame('B'))
    await act(async () => slowGuess.finish.with({}))

    expect(result.current.game.id).toBe('B')
    // game B can be played straight away: the finished guess released the keyboard
    await type(result, 'cr')
    expect(result.current.typedWord).toBe('cr')
  })

  it('does not show game A\'s rejected word on game B', async () => {
    api.createGame.mockResolvedValue(makeGame({ id: 'A' }))
    const result = await renderStartedGame()
    await type(result, 'zzzzz')
    const slowGuess = pending()
    api.submitGuess.mockReturnValue(slowGuess.promise)
    api.joinGame.mockResolvedValue(makeGame({ id: 'B' }))

    await act(async () => {
      result.current.pressKey('Enter')
    })
    await act(async () => result.current.openGame('B'))
    await act(async () => slowGuess.finish.failingWith(apiError('INVALID_GUESS', "'zzzzz' is not in the word list")))

    expect(result.current.game.id).toBe('B')
    expect(result.current.message).toBe('')
    expect(result.current.rowHasProblem).toBe(false)
  })

  it('stays on game B when game A turns out to be over', async () => {
    api.createGame.mockResolvedValue(makeGame({ id: 'A' }))
    const result = await renderStartedGame()
    await type(result, 'slate')
    const slowGuess = pending()
    api.submitGuess.mockReturnValue(slowGuess.promise)
    api.getGame.mockResolvedValue(makeGame({ id: 'A', status: 'won', answer: 'crane' }))
    api.joinGame.mockResolvedValue(makeGame({ id: 'B' }))

    await act(async () => {
      result.current.pressKey('Enter')
    })
    await act(async () => result.current.openGame('B'))
    await act(async () => slowGuess.finish.failingWith(apiError('GAME_OVER')))

    expect(result.current.game.id).toBe('B')
    expect(result.current.game.status).toBe('in_progress')
    expect(result.current.message).toBe('')
  })
})
