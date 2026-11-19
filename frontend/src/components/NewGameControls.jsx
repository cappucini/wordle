// The "New game" panel: pick a word length, then start a game.
import { blurAfterMouseClick } from '../focus'

// A row of buttons shows every choice at once, which is best while there are few of them.
// Past this many, the row would wrap and crowd the panel, so the picker becomes a stepper:
// the chosen length between a minus and a plus, the same small size however many there are.
const MOST_LENGTHS_AS_BUTTONS = 8

// The word-length picker and the "New game" button.
// The allowed lengths come from the backend's rules, not from a list written here.
function NewGameControls({ config, wordLength, onChangeLength, onStart }) {
  // list all allowed options
  const lengthOptions = []
  for (let length = config.min_word_length; length <= config.max_word_length; length++) {
    lengthOptions.push(length)
  }
  // true when there are too many lengths to show as a row of buttons
  const useStepper = lengthOptions.length > MOST_LENGTHS_AS_BUTTONS

  return (
    <section className="controls" aria-label="New game">
      <div className="length-picker" role="group" aria-label="Word length">
        {/* few lengths: a selectable button for every one */}
        {!useStepper &&
          lengthOptions.map((length) => (
            <button
              key={length}
              className={length === wordLength ? 'length-option selected' : 'length-option'}
              // aria-pressed tells screen readers which length is the chosen one
              aria-pressed={length === wordLength}
              onClick={(event) => {
                onChangeLength(length)
                // takes keyboard focus after button so pressing enter again
                // goes to the game and doesn't press button again
                blurAfterMouseClick(event)
              }}
            >
              {length}
            </button>
          ))}

        {/* many lengths: one step down, the chosen length, one step up.
            <output> is announced by screen readers each time the number changes. */}
        {useStepper && (
          <>
            <button
              className="length-option"
              aria-label="Fewer letters"
              disabled={wordLength <= config.min_word_length}
              // the button is disabled at the shortest length, so this never goes below it
              onClick={(event) => {
                onChangeLength(wordLength - 1)
                blurAfterMouseClick(event)
              }}
            >
              −
            </button>
            <output className="length-value">{wordLength}</output>
            <button
              className="length-option"
              aria-label="More letters"
              disabled={wordLength >= config.max_word_length}
              // the button is disabled at the longest length, so this never goes above it
              onClick={(event) => {
                onChangeLength(wordLength + 1)
                blurAfterMouseClick(event)
              }}
            >
              +
            </button>
          </>
        )}
        <span className="length-label">letters</span>
      </div>

      <button
        className="new-game"
        onClick={(event) => {
          onStart()
          // Always give up focus here, even when the button was pressed from the keyboard.
          // The next thing the player does is type a word and press Enter, and with focus
          // still on this button that Enter would start yet another game.
          event.currentTarget.blur()
        }}
      >
        New game
      </button>
    </section>
  )
}

export default NewGameControls
