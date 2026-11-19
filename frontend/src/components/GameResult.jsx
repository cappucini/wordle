// The banner shown when a game ends. Shows nothing while the game is in progress.
// The answer is only available here because the backend reveals it once the game is over.
// role="status" makes screen readers announce the result when it appears.
// In a shared game the win belongs to whoever made the last guess, so the others are told
// that player's name rather than "You got it".
function GameResult({ game, currentUser }) {
  if (game.status === 'won') {
    const guessCount = game.guesses.length
    const winner = game.guesses[guessCount - 1].guessed_by
    const someoneElseWon = winner && winner !== currentUser.username
    return (
      <p className="result won" role="status">
        {someoneElseWon ? winner : 'You'} got it in {guessCount} {guessCount === 1 ? 'guess' : 'guesses'}!
      </p>
    )
  }
  if (game.status === 'lost') {
    return (
      <p className="result lost" role="status">
        Out of guesses. The word was <strong>{game.answer}</strong>.
      </p>
    )
  }
  return null
}

export default GameResult
