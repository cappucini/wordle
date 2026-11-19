import { useEffect, useRef } from 'react'
import { blurAfterMouseClick } from '../focus'

const STATUS_TEXT = {
  in_progress: 'in progress',
  won: 'won',
  lost: 'lost',
}

// "Your games": every game the signed-in player is in, newest first.
// Clicking one opens it. More are fetched a page at a time with "Show more".
//
// On a wide screen the list has a fixed height and scrolls inside itself (see App.css), so
// a long list never pushes the board down the page.
function GameList({ games, currentGameId, hasMore, onOpen, onLoadMore }) {
  const listRef = useRef(null)

  // Keep the open game in view inside the scrolling list, for example after going Back to
  // an older game. Only the list itself is scrolled, never the page: on a phone the list
  // sits below the board, and jumping the page down to it would take the board away.
  useEffect(() => {
    const list = listRef.current
    if (list === null) {
      return
    }
    const current = list.querySelector('[aria-current="true"]')
    if (current === null) {
      return
    }
    const listBox = list.getBoundingClientRect()
    const itemBox = current.getBoundingClientRect()
    if (itemBox.top < listBox.top) {
      list.scrollTop -= listBox.top - itemBox.top
    } else if (itemBox.bottom > listBox.bottom) {
      list.scrollTop += itemBox.bottom - listBox.bottom
    }
  }, [currentGameId, games])

  if (games.length === 0) {
    return null
  }

  return (
    <section className="game-list" aria-label="Your games">
      <h2 className="game-list-heading">Your games</h2>
      <ul ref={listRef}>
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
                {/* The game in miniature: one row of small squares per guess, coloured by result.
                    Decoration only; the words beside it say the same thing.
                    --cols and --rows tell App.css how big a grid to fit into its fixed box,
                    so it can pick one square size that fits both ways. */}
                <span
                  className="game-list-mini"
                  data-testid="game-mini"
                  aria-hidden="true"
                  style={{ '--cols': game.word_length, '--rows': Math.max(guessesUsed, 1) }}
                >
                  {game.guesses.map((guess) => (
                    <span key={guess.number}>
                      {guess.results.map((result, index) => (
                        <i key={index} className={result} />
                      ))}
                    </span>
                  ))}
                </span>
                <span className="game-list-main">{game.word_length} letters</span>
                <span className={'game-list-status ' + game.status}>{STATUS_TEXT[game.status]}</span>
                <span className="game-list-detail">
                  {guessesUsed} of {game.max_guesses} guesses
                  {game.players.length > 1 && ', ' + game.players.length + ' players'}
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
