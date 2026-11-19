// HowToPlay and Rules: the explanation of the game, shown beside the sign-in form and in
// the panel a player can open while playing.
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import HowToPlay, { Rules } from './HowToPlay'

describe('HowToPlay', () => {
  it('says what the game is', () => {
    render(<HowToPlay />)

    expect(screen.getByRole('heading', { name: 'Guess the word, alone or together.' })).toBeInTheDocument()
    expect(
      screen.getByText('Words run from 5 to 8 letters, and you get one more guess than the word has letters.'),
    ).toBeInTheDocument()
  })

  it('explains the three colours, in the order green, yellow, grey', () => {
    render(<HowToPlay />)

    // each <dd> has the role "definition"; within() searches only inside the section
    const meanings = within(screen.getByRole('region', { name: 'How to play' }))
      .getAllByRole('definition')
      .map((meaning) => meaning.textContent)

    expect(meanings).toEqual([
      'Green: the right letter in the right place.',
      'Yellow: in the word, but somewhere else.',
      'Grey: not in the word.',
    ])
  })

  it('colours each sample tile with the result it explains', () => {
    const { container } = render(<HowToPlay />)

    // the spread turns the list the browser returns into a real array, which has map()
    const tiles = [...container.querySelectorAll('.legend .tile')]

    expect(tiles.map((tile) => tile.className)).toEqual(['tile correct', 'tile present', 'tile absent'])
  })

  it('keeps the sample tiles out of the way of screen readers and of the real board', () => {
    render(<HowToPlay />)

    // real board tiles are announced as images; these are decoration beside their meaning
    expect(screen.queryByRole('img')).toBeNull()
  })
})

describe('Rules', () => {
  it("states the game's real limits when it is given them", () => {
    render(<Rules minLength={4} maxLength={15} extraGuesses={1} />)

    expect(
      screen.getByText('Words run from 4 to 15 letters, and you get one more guess than the word has letters.'),
    ).toBeInTheDocument()
  })

  it('counts the extra guesses when there is more than one', () => {
    render(<Rules minLength={5} maxLength={8} extraGuesses={3} />)

    expect(
      screen.getByText('Words run from 5 to 8 letters, and you get 3 more guesses than the word has letters.'),
    ).toBeInTheDocument()
  })

  it('says so plainly when every word is the same length', () => {
    render(<Rules minLength={5} maxLength={5} extraGuesses={1} />)

    expect(
      screen.getByText('Words have 5 letters, and you get one more guess than the word has letters.'),
    ).toBeInTheDocument()
  })
})
