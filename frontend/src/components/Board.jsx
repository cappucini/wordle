// Names longer than this are shortened beside a row; hovering shows the full name.
const MAX_NAME_LENGTH = 12

// Cuts a long name down to MAX_NAME_LENGTH characters and adds an ellipsis.
function shortenName(name) {
  if (name.length <= MAX_NAME_LENGTH) {
    return name
  }
  return name.slice(0, MAX_NAME_LENGTH) + '…'
}

// The grid of tiles: one row per allowed guess, one tile per letter.
// Rows already played show their results, the next row shows what is being typed,
// and the rest are empty.
function Board({ game, typedWord, hasError }) {
  const rows = []
  // with more than one player, each guess is labelled with who made it
  const isShared = game.players.length > 1

  for (let rowIndex = 0; rowIndex < game.max_guesses; rowIndex++) {
    const guess = game.guesses[rowIndex] // undefined for rows not played yet
    // the first row without a guess, as long as the game is still going
    const isTypingRow = rowIndex === game.guesses.length && game.status === 'in_progress'
    const tiles = []

    for (let column = 0; column < game.word_length; column++) {
      let letter = ''
      let result = ''
      if (guess !== undefined) {
        letter = guess.word[column]
        result = guess.results[column]
      } else if (isTypingRow) {
        // positions not typed yet are undefined; ?? '' turns them into an empty tile
        letter = typedWord[column] ?? ''
      }

      // the class sets the colour: the result if there is one, or "filled" for a typed letter
      let className = 'tile'
      if (result !== '') {
        className += ' ' + result
      } else if (letter !== '') {
        className += ' filled'
      }

      tiles.push(
        <div
          key={column}
          className={className}
          // --delay is a CSS custom property set on this one tile: 80ms more for each column.
          // role="img" with an aria-label makes a screen reader announce the tile as one thing.
          style={{ '--delay': column * 80 + 'ms' }}
          role="img"
          aria-label={describeTile(letter, result)}
        >
          {letter}
        </div>,
      )
    }

    rows.push(
      <div key={rowIndex} className="board-row">
        <div className={isTypingRow && hasError ? 'row shake' : 'row'}>{tiles}</div>
        {/* in a shared game, name the player who made this guess */}
        {isShared && guess !== undefined && guess.guessed_by && (
          <span className="guesser" title={'Guessed by ' + guess.guessed_by}>
            {shortenName(guess.guessed_by)}
          </span>
        )}
      </div>,
    )
  }

  // --columns is a CSS custom property: App.css reads it to size the tiles and the grid
  return (
    <div className="board" style={{ '--columns': game.word_length }}>
      {rows}
    </div>
  )
}

// What a screen reader says for one tile, so the result isn't shown by colour alone.
function describeTile(letter, result) {
  if (letter === '') {
    return 'empty'
  }
  if (result === 'correct') {
    return letter + ', correct position'
  }
  if (result === 'present') {
    return letter + ', in the word but in a different position'
  }
  if (result === 'absent') {
    return letter + ', not in the word'
  }
  return letter
}

export default Board
