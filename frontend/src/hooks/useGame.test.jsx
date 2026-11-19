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

describe("useGame: other players' guesses", () => {
  const SHARED = makeGame({ id: 'game-1', players: [ERICA, SAM] })

  // The clock is faked before the game starts, because the 3-second timer is created
  // the moment a game is on screen.
  async function renderGameWithFakeClock(game) {
    api.createGame.mockResolvedValue(game)
    vi.useFakeTimers()
    const { result } = renderHook(() => useGame())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0) // let the rules and the games list arrive
    })
    await act(() => result.current.startGame())
    return result
  }

  function renderSharedGameWithFakeClock() {
    return renderGameWithFakeClock(SHARED)
  }

  // lets the 3-second check fire and its answer arrive
  async function waitForNextCheck() {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })
  }

  it("shows another player's guess at the next check, without a refresh", async () => {
    const withSamsGuess = { ...SHARED, guesses: [makeGuess('slate', 'AACAC', 'sam')] }
    const result = await renderSharedGameWithFakeClock()
    api.getGame.mockResolvedValue(withSamsGuess)

    await waitForNextCheck()

    expect(api.getGame).toHaveBeenCalledWith('game-1')
    expect(result.current.game.guesses).toHaveLength(1)
    expect(result.current.game.guesses[0].guessed_by).toBe('sam')
  })

  it('does not check before three seconds have passed', async () => {
    await renderSharedGameWithFakeClock()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2900)
    })

    expect(api.getGame).not.toHaveBeenCalled()
  })

  it('keeps the letters being typed when the board updates', async () => {
    const result = await renderSharedGameWithFakeClock()
    await type(result, 'cr')
    api.getGame.mockResolvedValue({ ...SHARED, guesses: [makeGuess('slate', 'AACAC', 'sam')] })

    await waitForNextCheck()

    expect(result.current.typedWord).toBe('cr')
  })

  it('never replaces the board with an older copy of itself', async () => {
    const oneGuess = { ...SHARED, guesses: [makeGuess('slate', 'AACAC', 'sam')] }
    const result = await renderSharedGameWithFakeClock()
    api.getGame.mockResolvedValue(oneGuess)
    await waitForNextCheck()

    api.getGame.mockResolvedValue(SHARED) // a late answer from before the guess
    await waitForNextCheck()

    expect(result.current.game.guesses).toHaveLength(1)
  })

  it('shows a newly joined player', async () => {
    const result = await renderGameWithFakeClock(NEW_GAME)
    api.getGame.mockResolvedValue(SHARED)

    await waitForNextCheck()

    expect(result.current.game.players).toHaveLength(2)
  })

  it('stops checking once the game is over', async () => {
    const result = await renderSharedGameWithFakeClock()
    api.getGame.mockResolvedValue({ ...SHARED, status: 'won', answer: 'crane', guesses: [makeGuess('crane', 'CCCCC', 'sam')] })
    await waitForNextCheck()
    expect(result.current.game.status).toBe('won')
    api.getGame.mockClear()

    await waitForNextCheck()
    await waitForNextCheck()

    expect(api.getGame).not.toHaveBeenCalled()
  })

  it('shrugs off a check that fails and tries again next time', async () => {
    const result = await renderSharedGameWithFakeClock()
    api.getGame.mockRejectedValueOnce(apiError('NETWORK_ERROR'))
    await waitForNextCheck()
    expect(result.current.message).toBe('')

    api.getGame.mockResolvedValue({ ...SHARED, guesses: [makeGuess('slate', 'AACAC', 'sam')] })
    await waitForNextCheck()

    expect(result.current.game.guesses).toHaveLength(1)
  })
})
