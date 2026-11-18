// The banner shown when a game ends. Shows nothing while the game is in progress.
// The answer is only available here because the backend reveals it once the game is over.
function GameResult({ game }) {
  if (game.status === 'won') {
    const guessCount = game.guesses.length
    return (
      <p className="result won">
        You got it in {guessCount} {guessCount === 1 ? 'guess' : 'guesses'}!
      </p>
    )
  }
  if (game.status === 'lost') {
    return (
      <p className="result lost">
        Out of guesses. The word was <strong>{game.answer}</strong>.
      </p>
    )
  }
  return null
}

export default GameResult
