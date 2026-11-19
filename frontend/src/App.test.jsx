// App: the whole page with a fake backend. Checks the two screens (sign-in form, game) and
// the moves between them, and one full guess from key press to coloured tiles.
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import App from './App'
import { CONFIG, ERICA, apiError, makeGame, makeGuess } from './test/factories'

// keep api.js's constants; replace every function that would call the backend
vi.mock('./api', async (importOriginal) => {
  const real = await importOriginal()
  return {
    // every constant api.js exports (event names, close codes, page sizes) keeps its real value
    ...Object.fromEntries(Object.entries(real).filter(([, value]) => typeof value !== 'function')),
    openGameSocket: vi.fn(),
    getConfig: vi.fn(),
    getGame: vi.fn(),
    createGame: vi.fn(),
    submitGuess: vi.fn(),
    listGames: vi.fn(),
    joinGame: vi.fn(),
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    getCurrentUser: vi.fn(),
  }
})

const NEW_GAME = makeGame({ id: 'game-1' })

beforeEach(() => {
  api.getCurrentUser.mockRejectedValue(apiError('NOT_AUTHENTICATED')) // a visitor, unless a test says otherwise
  api.getConfig.mockResolvedValue(CONFIG)
  api.listGames.mockResolvedValue({ items: [], next_cursor: null })
  api.createGame.mockResolvedValue(NEW_GAME)
  api.joinGame.mockResolvedValue(NEW_GAME)
  api.getGame.mockResolvedValue(NEW_GAME)
  api.submitGuess.mockResolvedValue({})
  api.login.mockResolvedValue(ERICA)
  api.register.mockResolvedValue(ERICA)
  api.logout.mockResolvedValue(null)
  api.openGameSocket.mockImplementation(() => ({ close() {} })) // a connection that stays quiet
})

async function renderSignedIn() {
  api.getCurrentUser.mockResolvedValue(ERICA)
  render(<App />)
  await screen.findByText('Signed in as')
  await screen.findByRole('button', { name: 'New game' })
}

describe('App: signing in and out', () => {
  it('says "Loading..." until it knows whether anyone is signed in', async () => {
    let answer
    api.getCurrentUser.mockReturnValue(new Promise((resolve) => (answer = resolve)))

    render(<App />)

    expect(screen.getByText('Loading...')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sign in to play' })).toBeNull()
    await act(async () => answer(ERICA))
  })

  it('shows the sign-in form to a visitor', async () => {
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Sign in to play' })).toBeInTheDocument()
    expect(screen.queryByText('Signed in as')).toBeNull()
  })

  it('says so on the form when the server cannot be reached', async () => {
    api.getCurrentUser.mockRejectedValue(apiError('NETWORK_ERROR'))

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Sign in to play' })).toBeInTheDocument()
    expect(screen.getByText("Can't reach the game server. Is it running?")).toBeInTheDocument()
  })

  it('shows no such warning to an ordinary visitor', async () => {
    render(<App />)

    await screen.findByRole('heading', { name: 'Sign in to play' })
    expect(screen.queryByText(/Can't reach the game server/)).toBeNull()
  })

  it('explains the game beside the sign-in form', async () => {
    render(<App />)

    await screen.findByRole('heading', { name: 'Sign in to play' })
    expect(screen.getByRole('region', { name: 'How to play' })).toBeInTheDocument()
    expect(screen.getByText('Green: the right letter in the right place.')).toBeInTheDocument()
  })

  it('does not show the explanation once signed in', async () => {
    await renderSignedIn()

    expect(screen.queryByRole('region', { name: 'How to play' })).toBeNull()
  })

  it('goes straight to the game for someone already signed in', async () => {
    await renderSignedIn()

    expect(screen.getByText('Signed in as').parentElement).toHaveTextContent('Signed in as erica')
    expect(screen.queryByRole('heading', { name: 'Sign in to play' })).toBeNull()
  })

  it('moves from the form to the game after signing in', async () => {
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Username'), 'erica')
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse')

    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(api.login).toHaveBeenCalledExactlyOnceWith('erica', 'correct horse')
    expect(await screen.findByText('Signed in as')).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).toBeNull()
  })

  it('moves from the form to the game after creating an account', async () => {
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'New here? Create an account' }))
    await userEvent.type(screen.getByLabelText('Username'), 'erica')
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse')

    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(api.register).toHaveBeenCalledExactlyOnceWith('erica', 'correct horse')
    expect(await screen.findByText('Signed in as')).toBeInTheDocument()
  })

  it('stays on the form with a message when the password is wrong', async () => {
    api.login.mockRejectedValue(apiError('INVALID_CREDENTIALS'))
    render(<App />)
    await userEvent.type(await screen.findByLabelText('Username'), 'erica')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong password')

    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Wrong username or password.')).toBeInTheDocument()
    expect(screen.queryByText('Signed in as')).toBeNull()
  })

  it('returns to the form on "Sign out" and forgets which game was open', async () => {
    window.history.replaceState({}, '', '/?game=game-1')
    await renderSignedIn()

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(api.logout).toHaveBeenCalledOnce()
    expect(await screen.findByRole('heading', { name: 'Sign in to play' })).toBeInTheDocument()
    // otherwise the next person to sign in on this browser would be joined to that game
    expect(window.location.search).toBe('')
  })

  it("does not join the next player to the previous player's game when they press Back", async () => {
    // erica plays two games on a shared computer, then signs out
    await renderSignedIn()
    api.createGame.mockResolvedValue(makeGame({ id: 'ericas-first' }))
    await userEvent.click(screen.getByRole('button', { name: 'New game' }))
    await waitFor(() => expect(window.location.search).toBe('?game=ericas-first'))
    api.createGame.mockResolvedValue(makeGame({ id: 'ericas-second' }))
    await userEvent.click(screen.getByRole('button', { name: 'New game' }))
    await waitFor(() => expect(window.location.search).toBe('?game=ericas-second'))
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    // sam signs in on the same browser and presses Back
    api.login.mockResolvedValue({ id: 'user-sam', username: 'sam' })
    api.getGame.mockRejectedValue(apiError('NOT_A_PLAYER'))
    api.joinGame.mockClear()
    await userEvent.type(await screen.findByLabelText('Username'), 'sam')
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await screen.findByRole('button', { name: 'New game' })
    act(() => window.history.back())

    expect(await screen.findByText("You're not a player in that game.")).toBeInTheDocument()
    expect(api.joinGame).not.toHaveBeenCalled()
    expect(screen.queryByRole('img')).toBeNull() // no board
  })

  it('returns to the form even when the sign-out request fails', async () => {
    api.logout.mockRejectedValue(apiError('NETWORK_ERROR'))
    await renderSignedIn()

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('heading', { name: 'Sign in to play' })).toBeInTheDocument()
  })

  it('returns to the form with an explanation when the backend ends the session', async () => {
    await renderSignedIn()

    act(() => {
      window.dispatchEvent(new Event(api.SIGNED_OUT_EVENT))
    })

    expect(await screen.findByRole('heading', { name: 'Sign in to play' })).toBeInTheDocument()
    expect(screen.getByText('Your sign-in has ended. Please sign in again.')).toBeInTheDocument()
  })
})

describe('App: the game screen', () => {
  it('explains how to start when no game is open', async () => {
    await renderSignedIn()

    expect(screen.getByText(/Pick a word length and start a game/)).toHaveTextContent(
      'Share a game\'s link to play it together with up to 2 friends.',
    )
    expect(screen.queryByRole('img')).toBeNull() // no board yet
  })

  it('shows the board, players and keyboard after "New game"', async () => {
    await renderSignedIn()

    await userEvent.click(screen.getByRole('button', { name: 'New game' }))

    expect(await screen.findAllByRole('img')).toHaveLength(30)
    expect(screen.getByRole('region', { name: 'Players' })).toHaveTextContent('erica (you)')
    expect(screen.getByRole('button', { name: 'Enter' })).toBeEnabled()
    expect(screen.queryByText(/Pick a word length/)).toBeNull()
  })

  it('plays a winning guess from the keyboard to the result banner', async () => {
    const won = makeGame({ id: 'game-1', status: 'won', answer: 'crane', guesses: [makeGuess('crane', 'CCCCC')] })
    await renderSignedIn()
    await userEvent.click(screen.getByRole('button', { name: 'New game' }))
    await screen.findAllByRole('img')
    api.getGame.mockResolvedValue(won)

    await userEvent.keyboard('crane')
    expect(screen.getAllByRole('img').slice(0, 5).map((tile) => tile.textContent)).toEqual(['c', 'r', 'a', 'n', 'e'])
    await userEvent.keyboard('{Enter}')

    expect(await screen.findByText('You got it in 1 guess!')).toBeInTheDocument()
    expect(api.submitGuess).toHaveBeenCalledExactlyOnceWith('game-1', 'crane')
    expect(screen.getAllByRole('img')[0]).toHaveAccessibleName('c, correct position')
    expect(screen.getByRole('button', { name: 'Enter' })).toBeDisabled()
  })

  it('shows the message for a rejected word in the status line', async () => {
    api.submitGuess.mockRejectedValue(apiError('INVALID_GUESS', "'zzzzz' is not in the word list"))
    await renderSignedIn()
    await userEvent.click(screen.getByRole('button', { name: 'New game' }))
    await screen.findAllByRole('img')

    await userEvent.keyboard('zzzzz{Enter}')

    expect(await screen.findByRole('status')).toHaveTextContent("'zzzzz' is not in the word list")
  })

  it('types with the on-screen keyboard too', async () => {
    await renderSignedIn()
    await userEvent.click(screen.getByRole('button', { name: 'New game' }))
    await screen.findAllByRole('img')
    const keyboard = within(screen.getByLabelText('Keyboard'))

    await userEvent.click(keyboard.getByRole('button', { name: 'c' }))
    await userEvent.click(keyboard.getByRole('button', { name: 'r' }))
    await userEvent.click(keyboard.getByRole('button', { name: 'Backspace' }))

    expect(screen.getAllByRole('img').slice(0, 2).map((tile) => tile.textContent)).toEqual(['c', ''])
  })

  it('lets a keyboard-only player open a game from the list and submit a guess with Enter', async () => {
    const listed = makeGame({ id: 'game-0' })
    api.listGames.mockResolvedValue({ items: [listed], next_cursor: null })
    api.joinGame.mockResolvedValue(listed)
    api.getGame.mockResolvedValue(listed)
    await renderSignedIn()
    const list = await screen.findByRole('region', { name: 'Your games' })

    within(list).getByRole('button').focus()
    await userEvent.keyboard('{Enter}') // opens the game
    await screen.findAllByRole('img')
    await userEvent.keyboard('crane{Enter}') // types a guess and submits it

    expect(api.submitGuess).toHaveBeenCalledExactlyOnceWith('game-0', 'crane')
  })

  it('does not treat an address ending in "?game=" as an invite', async () => {
    window.history.replaceState({}, '', '/?game=')

    await renderSignedIn()

    expect(api.joinGame).not.toHaveBeenCalled()
    expect(screen.getByText(/Pick a word length and start a game/)).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })

  it("tells the other players who won, not \"You got it\"", async () => {
    window.history.replaceState({}, '', '/?game=shared')
    api.joinGame.mockResolvedValue(
      makeGame({
        id: 'shared',
        status: 'won',
        answer: 'crane',
        players: [ERICA, { id: 'user-sam', username: 'sam' }],
        guesses: [makeGuess('crane', 'CCCCC', 'sam')],
      }),
    )

    await renderSignedIn()

    expect(await screen.findByText('sam got it in 1 guess!')).toBeInTheDocument()
  })

  it('lists the player\'s games and opens the one clicked', async () => {
    const older = makeGame({ id: 'game-0', word_length: 6, status: 'lost', answer: 'planet' })
    api.listGames.mockResolvedValue({ items: [older], next_cursor: null })
    api.joinGame.mockResolvedValue(older)
    await renderSignedIn()
    const list = await screen.findByRole('region', { name: 'Your games' })

    await userEvent.click(within(list).getByRole('button', { name: /6 letters/ }))

    expect(await screen.findByText(/Out of guesses/)).toHaveTextContent('The word was planet.')
    expect(window.location.search).toBe('?game=game-0')
  })
})

describe('App: when something unexpected breaks while drawing the page', () => {
  it('shows a message and a way to reload instead of a blank page', async () => {
    // the browser and React both report the error to the console; keep the test output clean
    vi.spyOn(console, 'error').mockImplementation(() => {})
    // a game missing its guesses makes the board fail while drawing
    api.getCurrentUser.mockResolvedValue(ERICA)
    window.history.replaceState(null, '', '/?game=broken')
    api.joinGame.mockResolvedValue({ ...makeGame({ id: 'broken' }), guesses: null })

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong.')
    expect(screen.getByRole('button', { name: 'Reload the page' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Wordle' })).toBeInTheDocument() // the title is still there
  })
})

describe('App: the "How to play" panel', () => {
  function rulesButton() {
    return screen.getByRole('button', { name: 'How to play' })
  }

  function rulesPanel() {
    return screen.queryByRole('region', { name: 'How to play' })
  }

  async function renderPlaying() {
    await renderSignedIn()
    await userEvent.click(screen.getByRole('button', { name: 'New game' }))
    await screen.findAllByRole('img')
  }

  function typedLetters() {
    return screen.getAllByRole('img').slice(0, 5).map((tile) => tile.textContent).join('')
  }

  it('is closed until asked for', async () => {
    await renderSignedIn()

    expect(rulesButton()).toHaveAttribute('aria-expanded', 'false')
    expect(rulesPanel()).toBeNull()
  })

  it('opens from the button in the bar and shows the rules', async () => {
    await renderPlaying()

    await userEvent.click(rulesButton())

    expect(rulesButton()).toHaveAttribute('aria-expanded', 'true')
    const panel = within(rulesPanel())
    expect(panel.getByText('Green: the right letter in the right place.')).toBeInTheDocument()
    expect(panel.getByText('Yellow: in the word, but somewhere else.')).toBeInTheDocument()
    expect(panel.getByText('Grey: not in the word.')).toBeInTheDocument()
    expect(panel.getByText(/one more guess than the word has letters/)).toBeInTheDocument()
  })

  it("takes its numbers from the game's settings, not from fixed text", async () => {
    // the range of word lengths can change on the backend; the rules must follow it
    api.getConfig.mockResolvedValue({ ...CONFIG, min_word_length: 4, max_word_length: 12, extra_guesses: 2 })
    await renderSignedIn()

    await userEvent.click(rulesButton())

    expect(
      within(rulesPanel()).getByText(
        'Words run from 4 to 12 letters, and you get 2 more guesses than the word has letters.',
      ),
    ).toBeInTheDocument()
  })

  it('leaves the board on screen behind it', async () => {
    await renderPlaying()

    await userEvent.click(rulesButton())

    expect(screen.getAllByRole('img')).toHaveLength(30)
    expect(screen.getByRole('button', { name: 'Enter' })).toBeInTheDocument()
  })

  it('closes when the button is clicked again', async () => {
    await renderPlaying()
    await userEvent.click(rulesButton())

    await userEvent.click(rulesButton())

    expect(rulesPanel()).toBeNull()
  })

  it('closes on Escape', async () => {
    await renderPlaying()
    await userEvent.click(rulesButton())

    await userEvent.keyboard('{Escape}')

    expect(rulesPanel()).toBeNull()
    expect(rulesButton()).toHaveAttribute('aria-expanded', 'false')
  })

  it('closes when the player clicks anywhere outside it', async () => {
    await renderPlaying()
    await userEvent.click(rulesButton())

    await userEvent.click(screen.getByRole('region', { name: 'Players' }))

    expect(rulesPanel()).toBeNull()
  })

  it('stays open when the player clicks inside it', async () => {
    await renderPlaying()
    await userEvent.click(rulesButton())

    await userEvent.click(within(rulesPanel()).getByText('Grey: not in the word.'))

    expect(rulesPanel()).not.toBeNull()
  })

  it('opens and closes with the ? key', async () => {
    await renderPlaying()

    await userEvent.keyboard('?')
    expect(rulesPanel()).not.toBeNull()

    await userEvent.keyboard('?')
    expect(rulesPanel()).toBeNull()
  })

  it('does not type on the board while it is open', async () => {
    await renderPlaying()
    await userEvent.click(rulesButton())

    await userEvent.keyboard('crane{Enter}')

    expect(typedLetters()).toBe('')
    expect(api.submitGuess).not.toHaveBeenCalled()
  })

  it('keeps a half-typed word, and typing carries on once it is closed', async () => {
    await renderPlaying()
    await userEvent.keyboard('cr')

    await userEvent.keyboard('?')
    await userEvent.keyboard('{Escape}')
    await userEvent.keyboard('a')

    expect(typedLetters()).toBe('cra')
  })

  it('gives Enter back to the board after being opened and closed from the keyboard', async () => {
    // a player who never touches the mouse: Tab to the button, Enter to open, Escape to close.
    // Focus must not stay on the button, or the next Enter opens the rules instead of guessing.
    await renderPlaying()
    rulesButton().focus()
    await userEvent.keyboard('{Enter}')
    expect(rulesPanel()).not.toBeNull()

    await userEvent.keyboard('{Escape}')
    await userEvent.keyboard('crane{Enter}')

    expect(rulesPanel()).toBeNull()
    expect(api.submitGuess).toHaveBeenCalledExactlyOnceWith('game-1', 'crane')
  })

  it('is available before any game is started', async () => {
    await renderSignedIn()

    await userEvent.click(rulesButton())

    expect(rulesPanel()).not.toBeNull()
  })

  it('is not offered on the sign-in page, which already shows the rules', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Sign in to play' })

    expect(screen.queryByRole('button', { name: 'How to play' })).toBeNull()
  })
})
