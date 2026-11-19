import { blurAfterMouseClick } from '../focus'

const KEYBOARD_ROWS = [
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
  ['Enter', 'z', 'x', 'c', 'v', 'b', 'n', 'm', 'Backspace'],
]

// when a letter has been guessed more than once, the keyboard shows its best result
const RESULT_RANK = { absent: 0, present: 1, correct: 2 }

// The on-screen keyboard. Each key is coloured by the best result that letter has had,
// and pressing one calls the same handler as the physical keyboard.
function Keyboard({ guesses, onKey, disabled }) {
  const letterResults = bestResultPerLetter(guesses)

  return (
    <div className="keyboard" role="group" aria-label="Keyboard">
      {KEYBOARD_ROWS.map((row, rowIndex) => (
        <div className="keyboard-row" key={rowIndex}>
          {row.map((key) => {
            const result = letterResults[key] ?? ''
            const isWide = key === 'Enter' || key === 'Backspace'
            return (
              <button
                key={key}
                className={'key ' + result + (isWide ? ' wide' : '')}
                disabled={disabled}
                aria-label={key === 'Backspace' ? 'Backspace' : key}
                onClick={(event) => {
                  onKey(key)
                  blurAfterMouseClick(event)
                }}
              >
                {key === 'Backspace' ? '⌫' : key}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}

// For each guessed letter, the best result it has had so far: correct beats present beats absent.
function bestResultPerLetter(guesses) {
  const best = {}
  for (const guess of guesses) {
    for (let index = 0; index < guess.word.length; index++) {
      const letter = guess.word[index]
      const result = guess.results[index]
      if (best[letter] === undefined || RESULT_RANK[result] > RESULT_RANK[best[letter]]) {
        best[letter] = result
      }
    }
  }
  return best
}

export default Keyboard
