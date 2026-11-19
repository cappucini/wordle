// Keyboard: the on-screen keys, how they are coloured, and what they report when clicked.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeGuess } from '../test/factories'
import Keyboard from './Keyboard'

// The on-screen key with this name, found by the name a screen reader would use.
function key(name) {
  return screen.getByRole('button', { name: name })
}

describe('Keyboard', () => {
  it('has a key for every letter, plus Enter and Backspace', () => {
    render(<Keyboard guesses={[]} onKey={() => {}} disabled={false} />)

    expect(screen.getAllByRole('button')).toHaveLength(28)
    for (const letter of 'abcdefghijklmnopqrstuvwxyz') {
      expect(key(letter)).toBeInTheDocument()
    }
    expect(key('Enter')).toBeInTheDocument()
    expect(key('Backspace')).toBeInTheDocument()
  })

  it('is a labelled group, so screen readers announce "Keyboard" on entering it', () => {
    render(<Keyboard guesses={[]} onKey={() => {}} disabled={false} />)

    expect(screen.getByRole('group', { name: 'Keyboard' })).toBeInTheDocument()
  })

  it('reports the key that was clicked', async () => {
    const onKey = vi.fn()
    render(<Keyboard guesses={[]} onKey={onKey} disabled={false} />)

    await userEvent.click(key('q'))
    await userEvent.click(key('Enter'))
    await userEvent.click(key('Backspace'))

    expect(onKey.mock.calls).toEqual([['q'], ['Enter'], ['Backspace']])
  })

  it('colours each guessed letter by its result and leaves the rest plain', () => {
    render(<Keyboard guesses={[makeGuess('react', 'PPCPA')]} onKey={() => {}} disabled={false} />)

    expect(key('a')).toHaveClass('correct')
    expect(key('r')).toHaveClass('present')
    expect(key('t')).toHaveClass('absent')
    for (const result of ['correct', 'present', 'absent']) {
      expect(key('z')).not.toHaveClass(result)
    }
  })

  it('upgrades a key when a later guess does better', () => {
    const guesses = [
      makeGuess('react', 'PPCPA'), // c is present
      makeGuess('crane', 'CCCCC'), // c is now correct
    ]

    render(<Keyboard guesses={guesses} onKey={() => {}} disabled={false} />)

    expect(key('c')).toHaveClass('correct')
    expect(key('c')).not.toHaveClass('present')
  })

  it('never downgrades a key when a later guess does worse', () => {
    const guesses = [
      makeGuess('crane', 'CCCCC'), // e is correct
      makeGuess('elect', 'PAAPA'), // e is present, then absent
    ]

    render(<Keyboard guesses={guesses} onKey={() => {}} disabled={false} />)

    expect(key('e')).toHaveClass('correct')
    expect(key('e')).not.toHaveClass('present')
    expect(key('e')).not.toHaveClass('absent')
  })

  it('shows the best result when one guess has the same letter twice', () => {
    // "eerie" against "crane": the first two e's are absent, the last is correct
    render(<Keyboard guesses={[makeGuess('eerie', 'AAPAC')]} onKey={() => {}} disabled={false} />)

    expect(key('e')).toHaveClass('correct')
  })

  it('ranks present above absent', () => {
    const guesses = [makeGuess('elect', 'AAAPA'), makeGuess('elect', 'PAAPA')]

    render(<Keyboard guesses={guesses} onKey={() => {}} disabled={false} />)

    expect(key('e')).toHaveClass('present')
  })

  it('cannot be used once the game is over', async () => {
    const onKey = vi.fn()
    render(<Keyboard guesses={[]} onKey={onKey} disabled={true} />)

    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled()
    }
    await userEvent.click(key('q'))
    expect(onKey).not.toHaveBeenCalled()
  })
})
