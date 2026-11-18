import Board from './components/Board'
import GameList from './components/GameList'
import GameResult from './components/GameResult'
import Keyboard from './components/Keyboard'
import NewGameControls from './components/NewGameControls'
import Players from './components/Players'
import { blurAfterMouseClick } from './focus'
import { useGame } from './hooks/useGame'

// The game page, shown once a player has signed in.
// It gets the game's state and actions from useGame and lays out the pieces.
function GameScreen({ user, onSignOut }) {
  const {
    // game's rules from backend, used by NewGameControls to build length buttons
    config,
    // length of word player picked, used by NewGameConrols to build length buttons
    wordLength,
    // function that is called when length button is clicked
    setWordLength,
    // game on the screen, used by Board, GameResult, and Keyboard
    game,
    // true while game named in address bar is being fetched, used to hide the "Pick a word length" hint
    isLoadingGame,
    // letters of word typed so far, used by Board to fill current row
    typedWord,
    // text for the player, usually an error. Empty if there is nothing.
    message,
    // true when problem is with the word being typed, used by Board to shake the row
    rowHasProblem,
    // function called when "New game" is clicked
    startGame,
    // handles one key: adds a letter, deletes one, or submits the guess
    pressKey,
    // the signed-in player's games, for the "Your games" list
    games,
    // true when "Your games" has another page to fetch
    hasMoreGames,
    // fetches that next page
    loadMoreGames,
    // switches to another game from the list
    openGame,
  } = useGame()

  if (config === null) {
    return <p className="message">{message || 'Loading...'}</p>
  }

  return (
    <>
      <p className="signed-in">
        Signed in as <strong>{user.username}</strong>
        <button
          className="link-button"
          onClick={(event) => {
            onSignOut()
            blurAfterMouseClick(event)
          }}
        >
          Sign out
        </button>
      </p>

      <NewGameControls
        config={config}
        wordLength={wordLength}
        onChangeLength={setWordLength}
        onStart={startGame}
      />

      <p className="message" role="status">
        {message}
      </p>
      {/* show this only if there's no game and we aren't waiting for one */}
      {game === null && !isLoadingGame && (
        <p className="hint">
          Pick a word length and start a game. You get one more guess than the word has letters.
          Share a game's link to play it together with up to {config.max_players_per_game - 1} friends.
        </p>
      )}

      {game !== null && (
        <>
          {/* Who is in this game, and the invite link */}
          <Players game={game} currentUser={user} />
          {/* Display the board, passing in game (to get word length, guesses so far), the typed word, and if the row being typed in has an error */}
          <Board game={game} typedWord={typedWord} hasError={rowHasProblem} />
          {/* Show game result if you won or lost */}
          <GameResult game={game} />
          {/* Display on-screen keyboard, disabling it once the game is over */}
          <Keyboard guesses={game.guesses} onKey={pressKey} disabled={game.status !== 'in_progress'} />
        </>
      )}

      <GameList
        games={games}
        currentGameId={game !== null ? game.id : null}
        hasMore={hasMoreGames}
        onOpen={openGame}
        onLoadMore={loadMoreGames}
      />
    </>
  )
}

export default GameScreen
