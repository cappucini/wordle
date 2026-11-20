// useGame: the game screen's state and actions. The backend is replaced by fakes (api.js is
// mocked), so each test decides what the "server" answers and checks what the hook does with it.
import { act, fireEvent, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import { CONFIG, ERICA, SAM, apiError, makeGame, makeGuess } from '../test/factories'
import { useGame } from './useGame'

// With no second argument, every function api.js exports becomes a fake that returns
// undefined, and its constants keep their values. beforeEach gives the fakes their answers.
vi.mock('../api')

// the game the fake backend hands out, unless a test sets up another
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
  // some tests fake the clock; always put the real one back
  vi.useRealTimers()
})

// Renders the hook and waits until it has loaded the rules.
async function renderGame() {
  // renderHook runs the hook inside a throwaway component; result.current is always
  // what the hook returned last
  const rendered = renderHook(() => useGame(ERICA))
  await waitFor(() => expect(rendered.result.current.config).not.toBeNull())
  return rendered.result
}

// Renders the hook and starts a new game, as clicking "New game" does.
async function renderStartedGame() {
  const result = await renderGame()
  // act() waits for the state changes that startGame causes before the test carries on
  await act(() => result.current.startGame())
  return result
}

// Sends keys to the hook one at a time, letting React redraw after each, as real typing
// does. `...keys` gathers every argument after the first into an array.
async function press(result, ...keys) {
  for (const key of keys) {
    await act(() => result.current.pressKey(key))
  }
}

// Types a word: one key press per letter.
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

    const { result } = renderHook(() => useGame(ERICA))

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

  // The server accepts a game ID in capitals or without hyphens, and answers with the ID
  // in its usual spelling. The page must then treat the two as the same game.
  it('rewrites the address to the game ID as the server spells it', async () => {
    window.history.replaceState({}, '', '/?game=GAME-1')

    const result = await renderGame()

    await waitFor(() => expect(result.current.game).toEqual(NEW_GAME))
    expect(api.joinGame).toHaveBeenCalledWith('GAME-1')
    expect(window.location.search).toBe('?game=game-1')
  })

  it('clears the row after a guess in a game opened through a differently spelled link', async () => {
    window.history.replaceState({}, '', '/?game=GAME-1')
    const afterGuess = makeGame({ id: 'game-1', guesses: [makeGuess('slate', 'AACAC')] })
    const result = await renderGame()
    await waitFor(() => expect(result.current.game).toEqual(NEW_GAME))
    api.getGame.mockResolvedValue(afterGuess)

    await type(result, 'slate')
    await press(result, 'Enter')

    expect(result.current.game).toEqual(afterGuess)
    expect(result.current.typedWord).toBe('')

    // a second Enter has nothing to send: the same word must not be guessed twice
    await press(result, 'Enter')

    expect(api.submitGuess).toHaveBeenCalledExactlyOnceWith('game-1', 'slate')
    expect(result.current.message).toBe('Not enough letters')
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

  it('ignores keys while another game is loading, so a guess cannot land in the game being left', async () => {
    const result = await renderStartedGame()
    api.joinGame.mockReturnValue(new Promise(() => {})) // the other game is slow to arrive

    await act(async () => result.current.openGame('game-2'))
    await type(result, 'crane')
    await press(result, 'Enter')

    expect(result.current.typedWord).toBe('')
    expect(api.submitGuess).not.toHaveBeenCalled()
  })

  it('takes keys again once the other game has loaded', async () => {
    const result = await renderStartedGame()
    api.joinGame.mockResolvedValue(makeGame({ id: 'game-2' }))

    await act(async () => result.current.openGame('game-2'))
    await type(result, 'cr')

    expect(result.current.typedWord).toBe('cr')
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

  it('ignores the physical keyboard while typing is paused, and keeps what was typed', async () => {
    api.createGame.mockResolvedValue(NEW_GAME)
    // initialProps and rerender() let the test change the hook's arguments while it is in use
    const { result, rerender } = renderHook(({ paused }) => useGame(ERICA, { isTypingPaused: paused }), {
      initialProps: { paused: false },
    })
    await waitFor(() => expect(result.current.config).not.toBeNull())
    await act(() => result.current.startGame())
    await act(async () => {
      fireEvent.keyDown(window, { key: 'c' })
    })

    rerender({ paused: true })
    await act(async () => {
      fireEvent.keyDown(window, { key: 'r' })
    })
    expect(result.current.typedWord).toBe('c')

    rerender({ paused: false })
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
  // every socket created, oldest first (emptied before each live-update test)
  static opened = []

  // Records itself in FakeSocket.opened, so a test can find it with latestSocket().
  constructor(gameId) {
    this.gameId = gameId
    this.isClosed = false
    FakeSocket.opened.push(this)
  }

  // What the page calls to hang up. It only notes that this happened.
  close() {
    this.isClosed = true
  }

  // --- what the "server" does ---
  // The connection opens.
  async serverAccepts() {
    await act(async () => this.onopen())
  }

  // A notice arrives: the game has changed.
  async serverSaysGameChanged() {
    await act(async () => this.onmessage({ data: '{"type":"game_updated"}' }))
  }

  // The connection ends. 1006 is the code a browser reports when a connection just drops.
  async serverCloses(code = 1006) {
    await act(async () => this.onclose({ code: code }))
  }
}

// The connection opened most recently.
function latestSocket() {
  return FakeSocket.opened.at(-1)
}

describe("useGame: other players' guesses", () => {
  const SHARED = makeGame({ id: 'game-1', players: [ERICA, SAM] })
  const WITH_SAMS_GUESS = { ...SHARED, guesses: [makeGuess('slate', 'AACAC', 'sam')] }

  beforeEach(() => {
    FakeSocket.opened = []
    // from here on, opening a connection makes a FakeSocket the test can drive
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
    const { result } = renderHook(() => useGame(ERICA))
    await act(async () => {
      // advancing by 0 lets the answers already on their way (the rules, the games) arrive
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
    const rendered = renderHook(() => useGame(ERICA))
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
      const { result } = renderHook(() => useGame(ERICA))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0) // let the rules and the games list arrive
      })
      await act(() => result.current.startGame())
      await latestSocket().serverAccepts()
      api.getGame.mockClear()
      return result
    }

    // Moves the fake clock forward, running any timers that come due, and lets React redraw.
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
      const rendered = renderHook(() => useGame(ERICA))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      await act(() => rendered.result.current.startGame())
      await latestSocket().serverCloses()

      rendered.unmount()
      await wait(20_000)

      expect(FakeSocket.opened).toHaveLength(1)
    })

    describe('and stays down', () => {
      // WebSockets blocked by the network, the server restarting, or too many tabs open:
      // the board must still pick up other players' guesses, just more slowly.

      it('checks for changes every five seconds while there is no connection', async () => {
        const result = await renderSharedGameWithFakeClock()
        await latestSocket().serverCloses()
        api.getGame.mockResolvedValue(WITH_SAMS_GUESS)

        await wait(4999)
        expect(api.getGame).not.toHaveBeenCalled()
        await wait(1)

        expect(api.getGame).toHaveBeenCalledWith('game-1')
        expect(result.current.game.guesses).toHaveLength(1)
        await wait(5000)
        expect(api.getGame).toHaveBeenCalledTimes(2)
      })

      it('goes quiet again once the connection is back', async () => {
        await renderSharedGameWithFakeClock()
        await latestSocket().serverCloses()
        await wait(1000) // reconnects
        await latestSocket().serverAccepts() // one catch-up check on opening
        api.getGame.mockClear()

        await wait(60_000)

        expect(api.getGame).not.toHaveBeenCalled()
      })

      it('checks every five seconds when a connection can never be made at all', async () => {
        vi.useFakeTimers()
        api.createGame.mockResolvedValue(SHARED)
        const { result } = renderHook(() => useGame(ERICA))
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0)
        })
        await act(() => result.current.startGame())
        api.getGame.mockResolvedValue(WITH_SAMS_GUESS)

        await latestSocket().serverCloses() // refused by the network before it ever opened
        await wait(5000)

        expect(result.current.game.guesses).toHaveLength(1)
      })

      it('stops checking when the game is over', async () => {
        const result = await renderSharedGameWithFakeClock()
        await latestSocket().serverCloses()
        api.getGame.mockResolvedValue({ ...SHARED, status: 'lost', answer: 'crane' })
        await wait(5000)
        expect(result.current.game.status).toBe('lost')
        api.getGame.mockClear()

        await wait(60_000)

        expect(api.getGame).not.toHaveBeenCalled()
      })

      it('stops checking when the page goes away', async () => {
        vi.useFakeTimers()
        api.createGame.mockResolvedValue(SHARED)
        const rendered = renderHook(() => useGame(ERICA))
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0)
        })
        await act(() => rendered.result.current.startGame())
        await latestSocket().serverCloses()
        api.getGame.mockClear()

        rendered.unmount()
        await wait(60_000)

        expect(api.getGame).not.toHaveBeenCalled()
      })

      it('does not check while the tab is in the background', async () => {
        await renderSharedGameWithFakeClock()
        await latestSocket().serverCloses()
        // document.hidden cannot be assigned to, so the test fakes the getter behind it
        const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)

        await wait(30_000)
        expect(api.getGame).not.toHaveBeenCalled()

        hidden.mockReturnValue(false) // the player comes back to the tab
        await wait(5000)
        expect(api.getGame).toHaveBeenCalled()
      })

      it('survives the browser refusing to create a connection at all', async () => {
        // browsers throw for an insecure ws:// address on an https page, for example
        vi.useFakeTimers()
        api.createGame.mockResolvedValue(SHARED)
        api.openGameSocket.mockImplementation(() => {
          throw new DOMException('The operation is insecure.', 'SecurityError')
        })
        const { result } = renderHook(() => useGame(ERICA))
        await act(async () => {
          await vi.advanceTimersByTimeAsync(0)
        })

        await act(() => result.current.startGame()) // must not crash the page
        api.getGame.mockResolvedValue(WITH_SAMS_GUESS)
        await wait(5000)

        // the game is playable, and the board still updates by checking on a timer
        expect(result.current.game.guesses).toHaveLength(1)
        expect(api.openGameSocket).toHaveBeenCalledOnce() // no point asking the browser again
      })

      it('checks every five seconds, without reconnecting, when the player has too many tabs open', async () => {
        const result = await renderSharedGameWithFakeClock()
        api.getGame.mockResolvedValue(WITH_SAMS_GUESS)

        await latestSocket().serverCloses(4429)
        await wait(30_000)

        expect(FakeSocket.opened).toHaveLength(1) // asking again would only be refused again
        expect(result.current.game.guesses).toHaveLength(1)
      })
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

    it('checks at once when the server says the sign-in has ended', async () => {
      await renderSharedGameWithFakeClock()
      api.getGame.mockRejectedValue(apiError('NOT_AUTHENTICATED'))

      await latestSocket().serverCloses(4401)

      // If the sign-in really has ended, this request gets a 401 and api.js sends the
      // player back to the sign-in form, which takes this whole screen away.
      expect(api.getGame).toHaveBeenCalledExactlyOnceWith('game-1')
    })

    it('reconnects after a 4401 if the sign-in turns out to be fine', async () => {
      // the server closes a connection at the expiry time it knew when the connection
      // opened; a sign-in that was extended since then is still good
      const result = await renderSharedGameWithFakeClock()
      api.getGame.mockResolvedValue(WITH_SAMS_GUESS)

      await latestSocket().serverCloses(4401)
      await wait(1000)

      expect(FakeSocket.opened).toHaveLength(2)
      expect(result.current.game.guesses).toHaveLength(1)
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

// Builds `count` games with the ids old-1, old-2, and so on.
function manyGames(count) {
  return Array.from({ length: count }, (_, index) => makeGame({ id: 'old-' + (index + 1) }))
}

// The ids of the games "Your games" is showing, in order.
function listedIds(result) {
  return result.current.games.map((game) => game.id)
}

describe('useGame: "Your games" after Show more', () => {
  // Renders the hook, waits for the first page of ten, then fetches a second page the way
  // "Show more" does.
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


describe('useGame: whose game is in the address', () => {
  // The browser's history remembers game addresses. On a shared computer the next person
  // to sign in must not be joined to the previous person's game by pressing Back.
  const NOT_A_PLAYER = "You're not a player in that game."

  // Presses the browser's Back button and waits for the "popstate" event that follows.
  // The test browser fires it a moment later, not straight away, hence the promise.
  async function goBack() {
    await act(async () => {
      window.history.back()
      await new Promise((resolve) => window.addEventListener('popstate', resolve, { once: true }))
    })
  }

  it('joins a game from a freshly opened link', async () => {
    window.history.replaceState(null, '', '/?game=invite')
    api.joinGame.mockResolvedValue(makeGame({ id: 'invite' }))

    const result = await renderGame()

    // ?. gives undefined instead of throwing while game is still null
    await waitFor(() => expect(result.current.game?.id).toBe('invite'))
    expect(api.joinGame).toHaveBeenCalledExactlyOnceWith('invite')
  })

  it("does not join a game that Back returns to if another player opened it", async () => {
    // sam played here first: his games are in the history
    const sams = renderHook(() => useGame(SAM))
    await waitFor(() => expect(sams.result.current.config).not.toBeNull())
    api.createGame.mockResolvedValue(makeGame({ id: 'sams-game' }))
    await act(() => sams.result.current.startGame())
    api.createGame.mockResolvedValue(makeGame({ id: 'sams-second-game' }))
    await act(() => sams.result.current.startGame())
    sams.unmount() // sam signs out...
    window.history.replaceState({}, '', '/') // ...which clears the address

    // erica signs in on the same browser and presses Back
    api.joinGame.mockClear()
    api.getGame.mockRejectedValue(apiError('NOT_A_PLAYER'))
    const result = await renderGame()
    await goBack()

    await waitFor(() => expect(result.current.message).toBe(NOT_A_PLAYER))
    expect(api.joinGame).not.toHaveBeenCalled()
    expect(result.current.game).toBeNull()
    expect(window.location.search).toBe('')
  })

  it('still opens that game if this player is in it too', async () => {
    const sams = renderHook(() => useGame(SAM))
    await waitFor(() => expect(sams.result.current.config).not.toBeNull())
    api.createGame.mockResolvedValue(makeGame({ id: 'shared', players: [SAM, ERICA] }))
    await act(() => sams.result.current.startGame())
    api.createGame.mockResolvedValue(makeGame({ id: 'another' }))
    await act(() => sams.result.current.startGame())
    sams.unmount()
    window.history.replaceState({}, '', '/')

    api.joinGame.mockClear()
    api.getGame.mockResolvedValue(makeGame({ id: 'shared', players: [SAM, ERICA] }))
    const result = await renderGame()
    await goBack()

    await waitFor(() => expect(result.current.game?.id).toBe('shared'))
    expect(api.joinGame).not.toHaveBeenCalled() // opened by reading it, not by joining
  })

  it('does not join the game left in the address when a different player signs in', async () => {
    // sam's sign-in expired with his game still in the address bar; nothing cleared it
    const sams = renderHook(() => useGame(SAM))
    await waitFor(() => expect(sams.result.current.config).not.toBeNull())
    api.createGame.mockResolvedValue(makeGame({ id: 'sams-game' }))
    await act(() => sams.result.current.startGame())
    sams.unmount()
    expect(window.location.search).toBe('?game=sams-game')

    api.joinGame.mockClear()
    api.getGame.mockRejectedValue(apiError('NOT_A_PLAYER'))
    const result = await renderGame() // erica signs in

    await waitFor(() => expect(result.current.message).toBe(NOT_A_PLAYER))
    expect(api.joinGame).not.toHaveBeenCalled()
    expect(window.location.search).toBe('')
  })

  it('reopens your own game when you sign in again after your sign-in expired', async () => {
    const first = renderHook(() => useGame(ERICA))
    await waitFor(() => expect(first.result.current.config).not.toBeNull())
    api.createGame.mockResolvedValue(makeGame({ id: 'ericas-game' }))
    await act(() => first.result.current.startGame())
    first.unmount()

    api.joinGame.mockResolvedValue(makeGame({ id: 'ericas-game' }))
    const result = await renderGame() // the same player signs back in

    await waitFor(() => expect(result.current.game?.id).toBe('ericas-game'))
  })

  it('goes Back and Forward between your own games', async () => {
    const result = await renderGame()
    api.createGame.mockResolvedValue(makeGame({ id: 'first' }))
    await act(() => result.current.startGame())
    api.createGame.mockResolvedValue(makeGame({ id: 'second' }))
    await act(() => result.current.startGame())
    api.joinGame.mockImplementation(async (id) => makeGame({ id: id }))

    await goBack()

    await waitFor(() => expect(result.current.game?.id).toBe('first'))
    expect(window.location.search).toBe('?game=first')
  })

  it('remembers that a joined invite is now yours, so a later player cannot rejoin it by Back', async () => {
    window.history.replaceState(null, '', '/?game=invite')
    api.joinGame.mockResolvedValue(makeGame({ id: 'invite' }))
    const first = await renderGame()
    await waitFor(() => expect(first.current.game?.id).toBe('invite'))

    // the address still says ?game=invite, but it is now marked as opened by erica
    api.joinGame.mockClear()
    api.getGame.mockRejectedValue(apiError('NOT_A_PLAYER'))
    const sams = renderHook(() => useGame(SAM))

    await waitFor(() => expect(sams.result.current.message).toBe(NOT_A_PLAYER))
    expect(api.joinGame).not.toHaveBeenCalled()
  })
})
