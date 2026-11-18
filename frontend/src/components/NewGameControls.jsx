import { blurAfterMouseClick } from '../focus'

// The word-length buttons and the "New game" button.
// The allowed lengths come from the backend's rules, not from a list written here.
function NewGameControls({ config, wordLength, onChangeLength, onStart }) {
  // list all allowed options
  const lengthOptions = []
  for (let length = config.min_word_length; length <= config.max_word_length; length++) {
    lengthOptions.push(length)
  }
  // create a selectable button for every single possible length
  return (
    <section className="controls" aria-label="New game">
      <div className="length-picker" role="group" aria-label="Word length">
        {lengthOptions.map((length) => (
          <button
            key={length}
            className={length === wordLength ? 'length-option selected' : 'length-option'}
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
