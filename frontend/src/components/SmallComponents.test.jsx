// GameResult, GameList, NewGameControls and Players: the smaller pieces of the game screen.
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CONFIG, ERICA, SAM, makeGame, makeGuess } from '../test/factories'
import GameList from './GameList'
import GameResult from './GameResult'
import NewGameControls from './NewGameControls'
import Players from './Players'

// a third player, to fill a three-player game
const THIRD = { id: 'user-third', username: 'third' }

describe('GameResult', () => {
  it('shows nothing while the game is in progress', () => {
    const { container } = render(<GameResult game={makeGame()} currentUser={ERICA} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('says "1 guess" for a win on the first try', () => {
    const game = makeGame({ status: 'won', answer: 'crane', guesses: [makeGuess('crane', 'CCCCC')] })

    render(<GameResult game={game} currentUser={ERICA} />)

    expect(screen.getByText('You got it in 1 guess!')).toBeInTheDocument()
  })

  it('says "guesses" for a win that took more than one', () => {
    const game = makeGame({
      status: 'won',
      answer: 'crane',
      guesses: [makeGuess('slate', 'AACAC'), makeGuess('react', 'PPCPA'), makeGuess('crane', 'CCCCC')],
    })

    render(<GameResult game={game} currentUser={ERICA} />)

    expect(screen.getByText('You got it in 3 guesses!')).toBeInTheDocument()
  })

  it("names the player who got it when it wasn't you", () => {
    const game = makeGame({
      status: 'won',
      answer: 'crane',
      players: [ERICA, SAM],
      guesses: [makeGuess('slate', 'AACAC', 'erica'), makeGuess('crane', 'CCCCC', 'sam')],
    })

    render(<GameResult game={game} currentUser={ERICA} />)

    expect(screen.getByRole('status')).toHaveTextContent('sam got it in 2 guesses!')
  })

  it('says "You got it" to the player who made the winning guess in a shared game', () => {
    const game = makeGame({
      status: 'won',
      answer: 'crane',
      players: [ERICA, SAM],
      guesses: [makeGuess('slate', 'AACAC', 'erica'), makeGuess('crane', 'CCCCC', 'sam')],
    })

    render(<GameResult game={game} currentUser={SAM} />)

    expect(screen.getByRole('status')).toHaveTextContent('You got it in 2 guesses!')
  })

  it('reveals the answer after a loss', () => {
    render(<GameResult game={makeGame({ status: 'lost', answer: 'crane' })} currentUser={ERICA} />)

    expect(screen.getByText(/Out of guesses\. The word was/)).toHaveTextContent(
      'Out of guesses. The word was crane.',
    )
  })

  it.each(['won', 'lost'])('announces a %s game to screen readers', (status) => {
    render(<GameResult game={makeGame({ status: status, answer: 'crane', guesses: [makeGuess('crane', 'CCCCC')] })} currentUser={ERICA} />)

    // role="status" is read out when it appears, without moving the player's focus
    expect(screen.getByRole('status')).toHaveTextContent(/You got it|Out of guesses/)
  })
})

describe('GameList', () => {
  // Draws the list with fake handlers, no games and no more pages. Pass props to change
  // any of that. Returns the handlers, so a test can check how they were called.
  function renderList(props) {
    const handlers = { onOpen: vi.fn(), onLoadMore: vi.fn() }
    render(<GameList games={[]} currentGameId={null} hasMore={false} {...handlers} {...props} />)
    return handlers
  }

  it('shows nothing when the player has no games', () => {
    renderList({ games: [] })

    expect(screen.queryByText('Your games')).toBeNull()
  })

  it('describes each game: length, status and guesses used', () => {
    renderList({
      games: [
        makeGame({ id: 'a', guesses: [makeGuess('slate', 'AACAC'), makeGuess('react', 'PPCPA')] }),
        makeGame({ id: 'b', word_length: 7, status: 'won', guesses: [makeGuess('kitchen', 'CCCCCCC')] }),
        makeGame({ id: 'c', status: 'lost' }),
      ],
    })

    const [first, second, third] = within(screen.getByRole('region', { name: 'Your games' })).getAllByRole('listitem')
    expect(first).toHaveTextContent('5 letters')
    expect(first).toHaveTextContent('in progress')
    expect(first).toHaveTextContent('2 of 6 guesses')
    expect(second).toHaveTextContent('7 letters')
    expect(second).toHaveTextContent('won')
    expect(second).toHaveTextContent('1 of 8 guesses')
    expect(third).toHaveTextContent('lost')
  })

  it('shows the player count only for shared games', () => {
    renderList({
      games: [makeGame({ id: 'solo' }), makeGame({ id: 'shared', players: [ERICA, SAM] })],
    })

    const [solo, shared] = screen.getAllByRole('listitem')
    expect(solo).not.toHaveTextContent('players')
    expect(shared).toHaveTextContent('0 of 6 guesses, 2 players')
  })

  it('draws each game in miniature: a row of squares per guess, coloured by result', () => {
    const game = makeGame({ id: 'a', guesses: [makeGuess('slate', 'AACAC'), makeGuess('react', 'PPCPA')] })

    const { container } = render(
      <GameList games={[game]} currentGameId={null} hasMore={false} onOpen={() => {}} onLoadMore={() => {}} />,
    )

    const rows = container.querySelectorAll('.game-list-mini > span')
    expect(rows).toHaveLength(2)
    expect([...rows[0].children].map((square) => square.className)).toEqual([
      'absent', 'absent', 'correct', 'absent', 'correct',
    ])
    expect([...rows[1].children].map((square) => square.className)).toEqual([
      'present', 'present', 'correct', 'present', 'absent',
    ])
  })

  it('hides the miniature from screen readers, since the words beside it say the same', () => {
    const { container } = render(
      <GameList games={[makeGame({ guesses: [makeGuess('slate', 'AACAC')] })]} currentGameId={null} hasMore={false} onOpen={() => {}} onLoadMore={() => {}} />,
    )

    expect(container.querySelector('.game-list-mini')).toHaveAttribute('aria-hidden', 'true')
  })

  it('draws no squares for a game with no guesses yet', () => {
    const { container } = render(
      <GameList games={[makeGame()]} currentGameId={null} hasMore={false} onOpen={() => {}} onLoadMore={() => {}} />,
    )

    expect(container.querySelectorAll('.game-list-mini i')).toHaveLength(0)
  })

  it('tells the stylesheet how many columns and rows to fit, so the squares stay square', () => {
    // App.css sizes every square from these two numbers: the largest whole size at which
    // this many columns and rows fit the miniature's fixed box
    const game = makeGame({
      word_length: 8,
      guesses: [makeGuess('notebook', 'APPPPAAA'), makeGuess('textbook', 'PPAAPPAA'), makeGuess('absolute', 'CCCCCCCC')],
    })

    const { container } = render(
      <GameList games={[game]} currentGameId={null} hasMore={false} onOpen={() => {}} onLoadMore={() => {}} />,
    )

    const mini = container.querySelector('.game-list-mini')
    expect(mini.style.getPropertyValue('--cols')).toBe('8')
    expect(mini.style.getPropertyValue('--rows')).toBe('3')
  })

  it('still describes a sensible grid for a game with no guesses yet', () => {
    const { container } = render(
      <GameList games={[makeGame()]} currentGameId={null} hasMore={false} onOpen={() => {}} onLoadMore={() => {}} />,
    )

    const mini = container.querySelector('.game-list-mini')
    expect(mini.style.getPropertyValue('--cols')).toBe('5')
    expect(mini.style.getPropertyValue('--rows')).toBe('1') // never zero: the size is found by dividing by it
  })

  it('draws every guess of the longest possible game, nine rows of eight', () => {
    // the miniature has a fixed size (see App.css), so the row stays the same height
    // Array.from({ length: 9 }, fn) builds an array of nine items by calling fn nine times
    const nineGuesses = Array.from({ length: 9 }, () => makeGuess('notebook', 'APPPPAAA'))
    const game = makeGame({ id: 'long', word_length: 8, status: 'lost', guesses: nineGuesses })

    const { container } = render(
      <GameList games={[game]} currentGameId={null} hasMore={false} onOpen={() => {}} onLoadMore={() => {}} />,
    )

    expect(container.querySelectorAll('.game-list-mini > span')).toHaveLength(9)
    expect(container.querySelectorAll('.game-list-mini i')).toHaveLength(72)
  })

  it('marks the game that is open', () => {
    renderList({ games: [makeGame({ id: 'a' }), makeGame({ id: 'b' })], currentGameId: 'b' })

    const [first, second] = screen.getAllByRole('button')
    expect(first).not.toHaveAttribute('aria-current')
    expect(second).toHaveAttribute('aria-current', 'true')
  })

  it('opens the game that was clicked', async () => {
    const { onOpen } = renderList({ games: [makeGame({ id: 'a' }), makeGame({ id: 'b' })] })

    await userEvent.click(screen.getAllByRole('button')[1])

    expect(onOpen).toHaveBeenCalledExactlyOnceWith('b')
  })

  it('gives up focus after a game is opened with the keyboard', async () => {
    // otherwise the Enter that submits the first guess would press this button again
    renderList({ games: [makeGame({ id: 'a' })] })
    const button = screen.getByRole('button')
    button.focus()

    await userEvent.keyboard('{Enter}')

    expect(button).not.toHaveFocus()
  })

  it('offers "Show more" only when there is another page', async () => {
    const { onLoadMore } = renderList({ games: [makeGame()], hasMore: true })

    await userEvent.click(screen.getByRole('button', { name: 'Show more' }))

    expect(onLoadMore).toHaveBeenCalledOnce()
  })

  it('hides "Show more" on the last page', () => {
    renderList({ games: [makeGame()], hasMore: false })

    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull()
  })
})

describe('NewGameControls', () => {
  // Draws the controls with the usual rules (lengths 5 to 8) and 5 chosen. Pass props to
  // change that. Returns the fake handlers.
  function renderControls(props) {
    const handlers = { onChangeLength: vi.fn(), onStart: vi.fn() }
    render(<NewGameControls config={CONFIG} wordLength={5} {...handlers} {...props} />)
    return handlers
  }

  // The buttons inside the "Word length" group, one per length.
  function lengthButtons() {
    return within(screen.getByRole('group', { name: 'Word length' })).getAllByRole('button')
  }

  it('offers the word lengths the backend allows', () => {
    renderControls()

    expect(lengthButtons().map((button) => button.textContent)).toEqual(['5', '6', '7', '8'])
  })

  it('takes the lengths from the config, not from a fixed list', () => {
    renderControls({ config: { ...CONFIG, min_word_length: 4, max_word_length: 6 }, wordLength: 4 })

    expect(lengthButtons().map((button) => button.textContent)).toEqual(['4', '5', '6'])
  })

  it('marks the chosen length as pressed', () => {
    renderControls({ wordLength: 7 })

    expect(screen.getByRole('button', { name: '7' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '5' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('reports a newly chosen length', async () => {
    const { onChangeLength } = renderControls()

    await userEvent.click(screen.getByRole('button', { name: '8' }))

    expect(onChangeLength).toHaveBeenCalledExactlyOnceWith(8)
  })

  it('starts a game when "New game" is clicked, and gives up focus', async () => {
    const { onStart } = renderControls()
    const button = screen.getByRole('button', { name: 'New game' })

    await userEvent.click(button)

    expect(onStart).toHaveBeenCalledOnce()
    // otherwise the Enter that submits the first guess would start another game
    expect(button).not.toHaveFocus()
  })
})

describe('NewGameControls: when there are too many lengths for a row of buttons', () => {
  // twelve possible lengths, 4 to 15: more than the eight a row of buttons holds
  const WIDE_CONFIG = { ...CONFIG, min_word_length: 4, max_word_length: 15 }

  // Draws the controls with twelve lengths on offer, which is enough to get the stepper.
  function renderStepper(props) {
    const handlers = { onChangeLength: vi.fn(), onStart: vi.fn() }
    render(<NewGameControls config={WIDE_CONFIG} wordLength={7} {...handlers} {...props} />)
    return handlers
  }

  // Searches limited to the "Word length" group, so the "New game" button is left out.
  function picker() {
    return within(screen.getByRole('group', { name: 'Word length' }))
  }

  it('still shows a row of buttons for exactly eight lengths', () => {
    render(
      <NewGameControls
        config={{ ...CONFIG, min_word_length: 5, max_word_length: 12 }}
        wordLength={5}
        onChangeLength={() => {}}
        onStart={() => {}}
      />,
    )

    expect(picker().getAllByRole('button').map((button) => button.textContent)).toEqual([
      '5', '6', '7', '8', '9', '10', '11', '12',
    ])
  })

  it('switches to a stepper for nine or more: the chosen length between a minus and a plus', () => {
    renderStepper()

    expect(picker().getAllByRole('button')).toHaveLength(2)
    expect(picker().getByRole('button', { name: 'Fewer letters' })).toBeInTheDocument()
    expect(picker().getByRole('button', { name: 'More letters' })).toBeInTheDocument()
    // the <output> element has the role "status"
    expect(picker().getByRole('status')).toHaveTextContent('7')
  })

  it('goes up one letter on plus and down one on minus', async () => {
    const { onChangeLength } = renderStepper()

    await userEvent.click(picker().getByRole('button', { name: 'More letters' }))
    await userEvent.click(picker().getByRole('button', { name: 'Fewer letters' }))

    expect(onChangeLength.mock.calls).toEqual([[8], [6]])
  })

  it('cannot go below the shortest length', async () => {
    const { onChangeLength } = renderStepper({ wordLength: 4 })
    const fewer = picker().getByRole('button', { name: 'Fewer letters' })

    expect(fewer).toBeDisabled()
    await userEvent.click(fewer)
    expect(onChangeLength).not.toHaveBeenCalled()
    expect(picker().getByRole('button', { name: 'More letters' })).toBeEnabled()
  })

  it('cannot go above the longest length', async () => {
    const { onChangeLength } = renderStepper({ wordLength: 15 })
    const more = picker().getByRole('button', { name: 'More letters' })

    expect(more).toBeDisabled()
    await userEvent.click(more)
    expect(onChangeLength).not.toHaveBeenCalled()
    expect(picker().getByRole('button', { name: 'Fewer letters' })).toBeEnabled()
  })

  it('says what the number counts, and still starts a game', async () => {
    const { onStart } = renderStepper()

    expect(picker().getByText('letters')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'New game' }))
    expect(onStart).toHaveBeenCalledOnce()
  })
})

describe('Players', () => {
  afterEach(() => {
    // one test below fakes the clock; put the real one back for the others
    vi.useRealTimers()
  })

  // The "Copy invite link" button, or null when it is not offered or shows another label.
  function inviteButton() {
    return screen.queryByRole('button', { name: 'Copy invite link' })
  }

  it('lists the players and marks which one is you', () => {
    render(<Players game={makeGame({ players: [ERICA, SAM] })} currentUser={SAM} />)

    const [first, second] = within(screen.getByRole('region', { name: 'Players' })).getAllByRole('listitem')
    expect(first).toHaveTextContent(/^erica$/)
    expect(second).toHaveTextContent(/^sam \(you\)$/)
  })

  it('shows how many of the places are taken', () => {
    render(<Players game={makeGame({ players: [ERICA, SAM] })} currentUser={ERICA} />)

    expect(screen.getByText('2 of 3 players')).toBeInTheDocument()
  })

  it('offers the invite link while there is room', () => {
    render(<Players game={makeGame()} currentUser={ERICA} />)

    expect(inviteButton()).toBeInTheDocument()
  })

  it('hides the invite link when the game is full', () => {
    render(<Players game={makeGame({ players: [ERICA, SAM, THIRD] })} currentUser={ERICA} />)

    expect(inviteButton()).toBeNull()
  })

  it('hides the invite link once the game is over', () => {
    render(<Players game={makeGame({ status: 'won' })} currentUser={ERICA} />)

    expect(inviteButton()).toBeNull()
  })

  it('copies the page address, confirms it, then goes back to normal', async () => {
    // fake the clock, so the three-second wait can be skipped instead of sat through
    vi.useFakeTimers()
    const writeText = vi.fn().mockResolvedValue()
    // a stand-in for the browser's clipboard, so the test can see what was copied
    vi.stubGlobal('navigator', { clipboard: { writeText: writeText } })
    window.history.replaceState({}, '', '/?game=game-1')
    render(<Players game={makeGame()} currentUser={ERICA} />)

    // fireEvent sends the click directly; the async act() lets the clipboard's promise
    // settle and React redraw before the checks
    await act(async () => {
      fireEvent.click(inviteButton())
    })

    expect(writeText).toHaveBeenCalledExactlyOnceWith(window.location.href)
    expect(window.location.href).toContain('?game=game-1')
    expect(screen.getByRole('button', { name: 'Link copied!' })).toBeInTheDocument()

    act(() => {
      // jump the fake clock forward three seconds, which fires the timer that resets the label
      vi.advanceTimersByTime(3000)
    })
    expect(inviteButton()).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('gives up focus after the link is copied with the keyboard', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockResolvedValue() } })
    render(<Players game={makeGame()} currentUser={ERICA} />)
    const button = inviteButton()
    button.focus()

    await act(async () => {
      fireEvent.click(button, { detail: 0 }) // detail 0 is how a keyboard "click" arrives
    })

    expect(button).not.toHaveFocus()
    vi.unstubAllGlobals()
  })

  it('says so when the browser refuses to copy', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('blocked'))
    vi.stubGlobal('navigator', { clipboard: { writeText: writeText } })
    render(<Players game={makeGame()} currentUser={ERICA} />)

    await act(async () => {
      fireEvent.click(inviteButton())
    })

    expect(screen.getByRole('button', { name: /Couldn't copy/ })).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})
