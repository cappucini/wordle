import './App.css'
import Board from './components/Board'
import GameResult from './components/GameResult'
import Keyboard from './components/Keyboard'
import NewGameControls from './components/NewGameControls'
import Title from './components/Title'
import { useGame } from './hooks/useGame'

// The page. It gets the game's state and actions from useGame and lays out the pieces.
function App() {
  const {
    // game's rules from backend, used by NewGameControls to build length buttons
    config,
    // length of word player picked, used by NewGameConrols to build length buttons
    wordLength,
    // function that is called when length button is clicked
    setWordLength,
    // game on the screen, used by Board, GameResult, and Keyboard
    game,
    // true while game named in address bar is being fetched, used by App to hide the "Pick a word length" hint
    isLoadingGame,
    // letters of word typed so far
    typedWord,
    // text for the player, usually an error. Empty if there is nothin. Used by Board to fill current row
    message,
    // true when problem is with the word being typed, used by Board to shake the row
    rowHasProblem,
    // function called when "New game" is xlicked
    startGame,
    // handles one key: adds a leter, deletes one, or submits the guess
    pressKey,
  } = useGame()

  if (config === null) {
    return <p className="message">{message || 'Loading...'}</p>
  }

  return (
    <main className="app">
      <Title />

      <NewGameControls
        config={config}
        wordLength={wordLength}
        onChangeLength={setWordLength}
        onStart={startGame}
      />

      <p className="message" role="status">
        {message}
      </p>
      {/*show this only if there's no game and we aren't waiting for one"*/}
      {game === null && !isLoadingGame && (
        <p className="hint">
          Pick a word length and start a game. You get one more guess than the word has letters.
        </p>
      )}

      {game !== null && (
        <>
          {/* Display the board, passing in game (to get word length, guesses so far), the typed word, and the if the row being typed in has an error */}
          <Board game={game} typedWord={typedWord} hasError={rowHasProblem} />
          {/* Show game result if you won or lost */}
          <GameResult game={game} />
          {/* Display on-screen keyboard, disabling it once the gable is over */}
          <Keyboard guesses={game.guesses} onKey={pressKey} disabled={game.status !== 'in_progress'} />
        </>
      )}
    </main>
  )
}

export default App
