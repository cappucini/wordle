import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import HowToPlay from './HowToPlay'

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

    const tiles = [...container.querySelectorAll('.legend .tile')]

    expect(tiles.map((tile) => tile.className)).toEqual(['tile correct', 'tile present', 'tile absent'])
  })

  it('keeps the sample tiles out of the way of screen readers and of the real board', () => {
    render(<HowToPlay />)

    // real board tiles are announced as images; these are decoration beside their meaning
    expect(screen.queryByRole('img')).toBeNull()
  })
})
