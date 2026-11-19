// Board: the grid of tiles, checked through what a screen reader would be told.
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeGame, makeGuess, ERICA, SAM } from '../test/factories'
import Board from './Board'

// every tile is announced as an image with a label, so tiles are found the way a screen reader finds them
function tiles() {
  return screen.getAllByRole('img')
}

// The aria-label of every tile, in reading order.
function labels() {
  return tiles().map((tile) => tile.getAttribute('aria-label'))
}

describe('Board', () => {
  it('draws one row per allowed guess and one tile per letter', () => {
    render(<Board game={makeGame()} typedWord="" hasError={false} />)

    expect(tiles()).toHaveLength(6 * 5)
    expect(labels().every((label) => label === 'empty')).toBe(true)
  })

  it('draws a bigger board for a longer word', () => {
    render(<Board game={makeGame({ word_length: 8 })} typedWord="" hasError={false} />)

    expect(tiles()).toHaveLength(9 * 8)
  })

  it('shows a played guess with each letter and its result', () => {
    const game = makeGame({ guesses: [makeGuess('react', 'PPCPA')] })

    render(<Board game={game} typedWord="" hasError={false} />)

    expect(labels().slice(0, 5)).toEqual([
      'r, in the word but in a different position',
      'e, in the word but in a different position',
      'a, correct position',
      'c, in the word but in a different position',
      't, not in the word',
    ])
    expect(tiles().slice(0, 5).map((tile) => tile.textContent)).toEqual(['r', 'e', 'a', 'c', 't'])
  })

  it('colours each tile by its result', () => {
    const game = makeGame({ guesses: [makeGuess('react', 'PPCPA')] })

    render(<Board game={game} typedWord="" hasError={false} />)

    // the empty slots skip tiles: this takes the 1st, 3rd and 5th
    const [r, , a, , t] = tiles()
    expect(r).toHaveClass('tile', 'present')
    expect(a).toHaveClass('tile', 'correct')
    expect(t).toHaveClass('tile', 'absent')
  })

  it('shows the letters being typed in the first empty row', () => {
    const game = makeGame({ guesses: [makeGuess('slate', 'AACAC')] })

    render(<Board game={game} typedWord="cr" hasError={false} />)

    // row 1 is the played guess; row 2 is the one being typed
    expect(labels().slice(5, 10)).toEqual(['c', 'r', 'empty', 'empty', 'empty'])
    expect(tiles()[5]).toHaveClass('filled')
    expect(tiles()[7]).not.toHaveClass('filled')
    // and nothing spills into row 3
    expect(labels().slice(10, 15)).toEqual(['empty', 'empty', 'empty', 'empty', 'empty'])
  })

  it('does not show typed letters once the game is over', () => {
    const game = makeGame({ status: 'won', guesses: [makeGuess('crane', 'CCCCC')] })

    render(<Board game={game} typedWord="sl" hasError={false} />)

    expect(labels().slice(5)).toEqual(Array(25).fill('empty'))
  })

  it('shakes only the row being typed when the word has a problem', () => {
    const game = makeGame({ guesses: [makeGuess('slate', 'AACAC')] })

    const { container } = render(<Board game={game} typedWord="zzzzz" hasError={true} />)

    const shaking = container.querySelectorAll('.row.shake')
    expect(shaking).toHaveLength(1)
    expect(shaking[0]).toHaveTextContent('zzzzz')
  })

  it('does not shake when there is no problem', () => {
    const { container } = render(<Board game={makeGame()} typedWord="cr" hasError={false} />)

    expect(container.querySelector('.shake')).toBeNull()
  })

  it('does not name the guesser in a solo game', () => {
    const game = makeGame({ guesses: [makeGuess('slate', 'AACAC', ERICA.username)] })

    render(<Board game={game} typedWord="" hasError={false} />)

    expect(screen.queryByTitle(/Guessed by/)).toBeNull()
  })

  it('names who made each guess in a shared game', () => {
    const game = makeGame({
      players: [ERICA, SAM],
      guesses: [makeGuess('slate', 'AACAC', 'erica'), makeGuess('react', 'PPCPA', 'sam')],
    })

    render(<Board game={game} typedWord="" hasError={false} />)

    expect(screen.getByTitle('Guessed by erica')).toHaveTextContent('erica')
    expect(screen.getByTitle('Guessed by sam')).toHaveTextContent('sam')
  })

  it('shortens a long name and keeps the full name on hover', () => {
    const longName = 'a_very_long_username'
    const game = makeGame({
      players: [ERICA, { id: 'user-long', username: longName }],
      guesses: [makeGuess('slate', 'AACAC', longName)],
    })

    render(<Board game={game} typedWord="" hasError={false} />)

    const name = screen.getByTitle('Guessed by ' + longName)
    expect(name).toHaveTextContent('a_very_long_…')
    expect(name.textContent).toHaveLength(13) // 12 characters and the ellipsis
  })

  it('shows a 12-character name in full', () => {
    const game = makeGame({
      players: [ERICA, { id: 'user-12', username: 'twelve_chars' }],
      guesses: [makeGuess('slate', 'AACAC', 'twelve_chars')],
    })

    render(<Board game={game} typedWord="" hasError={false} />)

    expect(screen.getByTitle('Guessed by twelve_chars')).toHaveTextContent('twelve_chars')
  })
})
