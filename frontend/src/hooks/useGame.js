import { useCallback, useEffect, useRef, useState } from 'react'
import { createGame, getConfig, getGame, submitGuess } from '../api'
import { errorText } from '../errorText'
import { clearGameIdFromUrl, getGameIdFromUrl, setGameIdInUrl } from '../gameUrl'

// Holds everything the game screen needs to know, and the actions that change it.
// Components only display what this returns; they never call the API themselves.
// This is called from App.jsx inside App() component
export function useGame() {
  // Every call useState() dedicates a piece of state with a given starting value.
  // They belong to the page's working memory, and will be wiped on refresh.
  const [config, setConfig] = useState(null) // the rules, from the backend
  const [wordLength, setWordLength] = useState(5) // the length picked for the next game
  const [game, setGame] = useState(null) // the game being played, from the backend
  const [typedWord, setTypedWord] = useState('') // the guess being typed
  const [message, setMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  // true when the message is about the word being typed, so only then does the row shake
  const [rowHasProblem, setRowHasProblem] = useState(false)
  // true while a game named in the address bar is being fetched, so the page can wait
  // instead of briefly showing the "start a game" hint
  const [isLoadingGame, setIsLoadingGame] = useState(() => getGameIdFromUrl() !== null)
  // a ref, not state: it must change immediately so a double-click can't start two games
  const isStartingGame = useRef(false)

  // This is called each time useGame() hook runs, registering load data functions.
  useEffect(() => {
    // sends request and returns a promise
    getConfig()
    // ...when the result arrives, run the function inside
      .then((rules) => {
        // store the rules from config including min_word_length, max_word_length, default_word_length, extra_guesses
        setConfig(rules)
        // set the word length from rules
        setWordLength(rules.default_word_length)
      })
      .catch((error) => setMessage(errorText(error)))
  }, [])

  // Show the game whose ID is in the address bar: on first load, and again whenever the
  // player uses the browser's Back or Forward buttons to move between games.
  useEffect(() => {
    // Counts the loads started here. If Back and Forward are pressed quickly, an older
    // request can finish after a newer one; its answer is ignored so the wrong game never shows.
    let latestLoad = 0

    function showGameFromUrl() {
      const gameId = getGameIdFromUrl()
      latestLoad += 1
      const thisLoad = latestLoad
      setTypedWord('')
      setRowHasProblem(false)

      if (gameId === null) {
        setGame(null)
        setMessage('') // don't leave a message from the previous game on screen
        setIsLoadingGame(false)
        return
      }
      setIsLoadingGame(true)
      getGame(gameId)
        .then((loadedGame) => {
          if (thisLoad !== latestLoad) {
            return // a newer load has started since; ignore this stale answer
          }
          setGame(loadedGame)
          setMessage('')
          setIsLoadingGame(false)
        })
        .catch((error) => {
          if (thisLoad !== latestLoad) {
            return
          }
          // the link points to a game that doesn't exist (or isn't a valid ID)
          clearGameIdFromUrl()
          setGame(null)
          setMessage(errorText(error))
          setIsLoadingGame(false)
        })
    }

    showGameFromUrl()
    window.addEventListener('popstate', showGameFromUrl)
    return () => window.removeEventListener('popstate', showGameFromUrl)
  }, [])

  async function startGame() {
    if (isStartingGame.current) {
      return // a new game is already being created; ignore the extra click
    }
    isStartingGame.current = true
    try {
      const newGame = await createGame(wordLength)
      setGameIdInUrl(newGame.id)
      setGame(newGame)
      setTypedWord('')
      setMessage('')
      setRowHasProblem(false)
    } catch (error) {
      setMessage(errorText(error))
      setRowHasProblem(false)
    } finally {
      isStartingGame.current = false
    }
  }

  // Registers a keyboard listener function
  // Every key press ends up here, including on-screen keyboard and physical keyboard.
  const pressKey = useCallback(
    async (key) => {
      // Ignore key when:
      // - no game has been started yet
      // - game is already won or lost
      // - we're in the process already of submitting guess to server
      if (game === null || game.status !== 'in_progress' || isSubmitting) {
        return
      }
      // if it's "Enter" on the on-screen Enter Key or the keyboard
      if (key === 'Enter') {
        // reject submission if there are not enough letters
        if (typedWord.length !== game.word_length) {
          setMessage('Not enough letters')
          // flag row
          setRowHasProblem(true)
          return
        }
        setIsSubmitting(true)
        try {
          // Step 1: send the guess.
          try {
            await submitGuess(game.id, typedWord)
          } catch (error) {
            setMessage(errorText(error))
            if (error.code === 'GAME_OVER') {
              // The game was finished somewhere else (another tab, or another player).
              // Reload it so this board shows the final result instead of staying stale.
              setTypedWord('')
              setRowHasProblem(false)
              setGame(await getGame(game.id))
            } else {
              // an invalid word lands here; the typed letters stay so the player can fix them
              setRowHasProblem(error.code === 'INVALID_GUESS')
            }
            return
          }

          // Step 2: the guess is saved. Clear the typed letters straight away, so that if the
          // reload below fails, pressing Enter again can't submit the same word a second time.
          setTypedWord('')
          setMessage('')
          setRowHasProblem(false)

          // Step 3: the server owns the game, so reload it rather than updating our own copy.
          setGame(await getGame(game.id))
        } catch (error) {
          // only a failed reload reaches here: the guess (if any) is safe on the server
          setMessage(errorText(error))
        } finally {
          setIsSubmitting(false)
        }
      } else if (key === 'Backspace') {
        setTypedWord(typedWord.slice(0, -1))
        setMessage('')
        setRowHasProblem(false)
      } else if (/^[a-zA-Z]$/.test(key) && typedWord.length < game.word_length) {
        setTypedWord(typedWord + key.toLowerCase())
        setMessage('')
        setRowHasProblem(false)
      }
    },
    [game, typedWord, isSubmitting],
  )

  // Listen to the physical keyboard.
  useEffect(() => {
    function handleKeyDown(event) {
      // ignore browser event if Control, Command, or Option was held during a key press
      // Otherwise if you want to Cmd-R(Refresh), Cmd-C (copy), CmD-A (select all),
      // you may end up typing letters in your guess.
      if (event.ctrlKey || event.metaKey || event.altKey) {
        return // leave browser shortcuts such as Cmd+R alone
      }
      const isOnButton = event.target.tagName === 'BUTTON'
      if (isOnButton && (event.key === 'Enter' || event.key === ' ')) {
        return // the focused button handles its own click
      }
      pressKey(event.key)
    }

    // Attach key listener to the window, and re-attach when pressKey changes to always 
    // use the current state, removing the old listener so there is never more than one.
    // Start listening for key presses
    window.addEventListener('keydown', handleKeyDown)
    // how to stop listening
    return () => window.removeEventListener('keydown', handleKeyDown)
    // restart listening when pressKey is replaced
  }, [pressKey])

  return {
    config,
    wordLength,
    setWordLength,
    game,
    isLoadingGame,
    typedWord,
    message,
    rowHasProblem,
    startGame,
    pressKey,
  }
}
