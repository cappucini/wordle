import { blurAfterMouseClick } from '../focus'

const STATUS_TEXT = {
  in_progress: 'in progress',
  won: 'won',
  lost: 'lost',
}

// "Your games": every game the signed-in player is in, newest first.
// Clicking one opens it. More are fetched a page at a time with "Show more".
function GameList({ games, currentGameId, hasMore, onOpen, onLoadMore }) {
  if (games.length === 0) {
    return null
  }

  return (
    <section className="game-list" aria-label="Your games">
      <h2 className="game-list-heading">Your games</h2>
      <ul>
        {games.map((game) => {
          const isCurrent = game.id === currentGameId
          const guessesUsed = game.guesses.length
          return (
            <li key={game.id}>
              <button
                className={isCurrent ? 'game-list-item current' : 'game-list-item'}
                aria-current={isCurrent ? 'true' : undefined}
                onClick={(event) => {
                  onOpen(game.id)
                  // Always give up focus, even when opened from the keyboard: the next thing
                  // the player does is type a word and press Enter, and with focus still
                  // here that Enter would press this button again instead of guessing.
                  event.currentTarget.blur()
                }}
              >
                <span className="game-list-main">{game.word_length} letters</span>
                <span className={'game-list-status ' + game.status}>{STATUS_TEXT[game.status]}</span>
                <span className="game-list-detail">
                  {guessesUsed} of {game.max_guesses} guesses
                  {game.players.length > 1 && ' · ' + game.players.length + ' players'}
                </span>
              </button>
            </li>
          )
        })}
      </ul>

      {hasMore && (
        <button
          className="link-button"
          onClick={(event) => {
            onLoadMore()
            blurAfterMouseClick(event)
          }}
        >
          Show more
        </button>
      )}
    </section>
  )
}

export default GameList
