// The game screen a signed-in player sees: the top bar, the three panels (new game, players,
// your games), the board and the keyboard. The game's logic lives in hooks/useGame.js.
import Board from './components/Board'
import GameList from './components/GameList'
import GameResult from './components/GameResult'
import { Rules } from './components/HowToPlay'
import Keyboard from './components/Keyboard'
import NewGameControls from './components/NewGameControls'
import Players from './components/Players'
import { blurAfterMouseClick } from './focus'
import { useGame } from './hooks/useGame'
import { useRulesPanel } from './hooks/useRulesPanel'

// The game page, shown once a player has signed in.
// It gets the game's state and actions from useGame and lays out the pieces:
// the signed-in line, a row of three panels (the "label"), then the board and keyboard
// together in one boxed panel (the "well").
function GameScreen({ user, onSignOut }) {
  // the "How to play" panel, opened from the bar or with the ? key
  const {
    // `isOpen: isRulesOpen` takes the hook's `isOpen` and calls it isRulesOpen in this file
    isOpen: isRulesOpen,
    toggle: toggleRules,
    buttonRef: rulesButtonRef,
    panelRef: rulesPanelRef,
  } = useRulesPanel()
  const {
    // game's rules from backend, used by NewGameControls to build length buttons
    config,
    // why the rules could not be loaded ('' if they were), and a function to try again
    configError,
    retryConfig,
    // forgets any game still loading; called just before signing out
    cancelLoading,
    // length of word player picked, used by NewGameControls to build length buttons
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
    // while the rules are open, the keyboard belongs to the panel, not the board
  } = useGame(user, { isTypingPaused: isRulesOpen })

  // Signs out, then lets go of focus if the click came from the mouse. A game that finishes
  // loading after this must not put itself back in the address, where the next person to
  // sign in on this browser would find it, so loads under way are forgotten first.
  function handleSignOut(event) {
    cancelLoading()
    onSignOut()
    blurAfterMouseClick(event)
  }

  // The rules have not arrived yet, so the game cannot be drawn. Show a loading line, or
  // if loading them failed, why, with a way to try again. Signing out stays possible.
  if (config === null) {
    return (
      <>
        <p className="signed-in">
          <span className="signed-in-label">Signed in as</span> <strong>{user.username}</strong>
          <button className="link-button" onClick={handleSignOut}>
            Sign out
          </button>
        </p>
        <p className="message">{configError || 'Loading...'}</p>
        {configError !== '' && (
          <button className="new-game" onClick={retryConfig}>
            Try again
          </button>
        )}
      </>
    )
  }

  // <> ... </> is a fragment: it groups the pieces without adding an element to the page
  return (
    <>
      <p className="signed-in">
        <span className="signed-in-label">Signed in as</span> <strong>{user.username}</strong>
        {/* Opens the rules without leaving the game. On a phone the label shortens to "Rules";
            aria-label keeps its name the same for screen readers at every width. */}
        <button
          ref={rulesButtonRef}
          className="link-button rules-button"
          aria-label="How to play"
          // aria-expanded and aria-controls tell screen readers that this button opens the
          // element with id "rules-panel", and whether that panel is open right now
          aria-expanded={isRulesOpen}
          aria-controls="rules-panel"
          // open or close the panel, then let go of focus if the click came from the mouse
          onClick={(event) => {
            toggleRules()
            blurAfterMouseClick(event)
          }}
        >
          <span className="rules-long">How to play</span>
          <span className="rules-short">Rules</span>
        </button>
        <button className="link-button" onClick={handleSignOut}>
          Sign out
        </button>
      </p>

      {/* The rules, dropped down under the bar. The board stays visible behind it.
          Closes on Escape, on a click outside it, or with the button or the ? key again. */}
      {isRulesOpen && (
        <section id="rules-panel" ref={rulesPanelRef} className="rules-panel" aria-label="How to play">
          <h2 className="rules-heading">How to play</h2>
          <Rules
            minLength={config.min_word_length}
            maxLength={config.max_word_length}
            extraGuesses={config.extra_guesses}
          />
          <p className="field-hint">Press Esc or click outside to close. The ? key opens this again.</p>
        </section>
      )}

      {/* The label: three panels across the top. Starting a game, who is playing, and the
          player's other games. Players only shows once a game is open. */}
      <div className="label">
        <NewGameControls
          config={config}
          wordLength={wordLength}
          onChangeLength={setWordLength}
          onStart={startGame}
        />
        {/* Who is in this game, and the invite link */}
        {game !== null && <Players game={game} currentUser={user} />}
        <GameList
          games={games}
          // null when no game is open, so no row in the list is marked as the current one
          currentGameId={game !== null ? game.id : null}
          hasMore={hasMoreGames}
          onOpen={openGame}
          onLoadMore={loadMoreGames}
        />
      </div>

      {/* role="status" makes screen readers read a new message out without moving focus */}
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

      {/* The well: the board on the left and the keyboard beside it */}
      {game !== null && (
        <div className="well">
          <div className="well-board">
            {/* Display the board, passing in game (to get word length, guesses so far), the typed word, and if the row being typed in has an error */}
            <Board game={game} typedWord={typedWord} hasError={rowHasProblem} />
            {/* Show game result if you won or lost */}
            <GameResult game={game} currentUser={user} />
          </div>
          {/* Display on-screen keyboard, disabling it once the game is over */}
          <Keyboard guesses={game.guesses} onKey={pressKey} disabled={game.status !== 'in_progress'} />
          {/* decoration only: the printed dots along the well's edge */}
          <div className="well-screen" aria-hidden="true" />
        </div>
      )}
    </>
  )
}

export default GameScreen
