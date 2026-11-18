// The grid of tiles: one row per allowed guess, one tile per letter.
// Rows already played show their results, the next row shows what is being typed,
// and the rest are empty.
function Board({ game, typedWord, hasError }) {
  const rows = []

  for (let rowIndex = 0; rowIndex < game.max_guesses; rowIndex++) {
    const guess = game.guesses[rowIndex] // undefined for rows not played yet
    const isTypingRow = rowIndex === game.guesses.length && game.status === 'in_progress'
    const tiles = []

    for (let column = 0; column < game.word_length; column++) {
      let letter = ''
      let result = ''
      if (guess !== undefined) {
        letter = guess.word[column]
        result = guess.results[column]
      } else if (isTypingRow) {
        letter = typedWord[column] ?? ''
      }

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
          style={{ '--delay': column * 80 + 'ms' }}
          role="img"
          aria-label={describeTile(letter, result)}
        >
          {letter}
        </div>,
      )
    }

    rows.push(
      <div key={rowIndex} className={isTypingRow && hasError ? 'row shake' : 'row'}>
        {tiles}
      </div>,
    )
  }

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
