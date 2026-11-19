import { useCallback, useEffect, useRef, useState } from 'react'
import {
  GAMES_PAGE_SIZE,
  MAX_GAMES_PAGE_SIZE,
  SOCKET_CLOSED_GAME_NOT_FOUND,
  SOCKET_CLOSED_NOT_A_PLAYER,
  SOCKET_CLOSED_NOT_AUTHENTICATED,
  SOCKET_CLOSED_TOO_MANY_CONNECTIONS,
  createGame,
  getConfig,
  getGame,
  joinGame,
  listGames,
  openGameSocket,
  submitGuess,
} from '../api'
import { errorText } from '../errorText'
import { clearGameIdFromUrl, getGameIdFromUrl, setGameIdInUrl } from '../gameUrl'

// If the connection that reports other players' guesses drops, the page reconnects:
// after 1 second, then 2, 4, 8, and at most every 10 seconds after that.
const FIRST_RECONNECT_DELAY_MS = 1000
const LONGEST_RECONNECT_DELAY_MS = 10000

// While there is no connection (it dropped, or the network doesn't allow WebSockets at all),
// the page falls back to asking the server this often, so a shared board still updates.
const NO_CONNECTION_CHECK_MS = 5000

// close codes after which reconnecting is pointless: the backend refused on purpose
const REFUSED = [SOCKET_CLOSED_NOT_AUTHENTICATED, SOCKET_CLOSED_NOT_A_PLAYER, SOCKET_CLOSED_GAME_NOT_FOUND]

// Holds everything the game screen needs to know, and the actions that change it.
// Components only display what this returns; they never call the API themselves.
// This is called from GameScreen.jsx, which is only shown once a player has signed in.
export function useGame() {
  // Every call useState() dedicates a piece of state with a given starting value.
  // They belong to the page's working memory, and will be wiped on refresh.
  const [config, setConfig] = useState(null) // the rules, from the backend
  const [wordLength, setWordLength] = useState(5) // the length picked for the next game
  const [game, setGame] = useState(null) // the game being played, from the backend
  const [typedWord, setTypedWord] = useState('') // the guess being typed
  const [message, setMessage] = useState('')
  // Two refs that mirror what the key handler needs to read. A ref can be read the instant
  // it changes, where state only updates on the next redraw. Without them, key presses that
  // arrive in a quick burst would each see the same out-of-date word and overwrite each other,
  // and a second Enter could slip through before "submitting" had taken effect.
  const typedWordRef = useRef('')
  // the ID of the game a guess is being sent for, or null when none is. It names the game
  // so that a guess still on its way for one game doesn't lock the keyboard of another.
  const submittingForGame = useRef(null)

  // The one way to change the typed word: updates the ref (for the key handler) and the
  // state (for the screen) together, so they can never disagree.
  const changeTypedWord = useCallback((nextWord) => {
    typedWordRef.current = nextWord
    setTypedWord(nextWord)
  }, [])
  // true when the message is about the word being typed, so only then does the row shake
  const [rowHasProblem, setRowHasProblem] = useState(false)
  // true while a game named in the address bar is being fetched, so the page can wait
  // instead of briefly showing the "start a game" hint
  const [isLoadingGame, setIsLoadingGame] = useState(() => getGameIdFromUrl() !== null)
  // a ref, not state: it must change immediately so a double-click can't start two games
  const isStartingGame = useRef(false)
  // "Your games": the signed-in player's games, newest first, loaded a page at a time
  const [games, setGames] = useState([])
  const [nextGamesCursor, setNextGamesCursor] = useState(null) // null when there are no more pages
  // Counts the game loads started. If Back and Forward are pressed quickly, an older request
  // can finish after a newer one; its answer is ignored so the wrong game never shows.
  const latestLoad = useRef(0)

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

  // How many games "Your games" is showing, and whether a "Show more" request is under way.
  // Refs, because the functions below need the current values the moment they run.
  const shownGamesCount = useRef(0)
  const isLoadingMoreGames = useRef(false)

  // Fetch the player's games again from the top. Called on load and whenever the list may
  // have changed (a game was started, joined or finished).
  // It asks for as many games as are already showing, in whole pages, so a player who has
  // clicked "Show more" keeps those extra games instead of dropping back to the first page.
  const refreshGames = useCallback(() => {
    const pagesShown = Math.max(1, Math.ceil(shownGamesCount.current / GAMES_PAGE_SIZE))
    const limit = Math.min(pagesShown * GAMES_PAGE_SIZE, MAX_GAMES_PAGE_SIZE)
    listGames(null, limit)
      .then((page) => {
        shownGamesCount.current = page.items.length
        setGames(page.items)
        setNextGamesCursor(page.next_cursor)
      })
      .catch(() => {
        // the list is a convenience; a failure here shouldn't interrupt the game on screen
      })
  }, [])

  // Fetch the next page and add it to the end of the list.
  function loadMoreGames() {
    if (nextGamesCursor === null || isLoadingMoreGames.current) {
      return // nothing more to fetch, or the next page is already on its way (a double-click)
    }
    isLoadingMoreGames.current = true
    listGames(nextGamesCursor)
      .then((page) => {
        setGames((current) => {
          // The list may have been refreshed while this page was on its way, and then some
          // of these games are in it already. Only add the ones that aren't.
          const shownIds = new Set(current.map((game) => game.id))
          const merged = current.concat(page.items.filter((game) => !shownIds.has(game.id)))
          shownGamesCount.current = merged.length
          return merged
        })
        setNextGamesCursor(page.next_cursor)
      })
      .catch((error) => setMessage(errorText(error)))
      .finally(() => {
        isLoadingMoreGames.current = false
      })
  }

  // Show the game whose ID is in the address bar.
  // It joins the game first: opening a link someone shared is how a player joins their game.
  // Joining a game you are already in changes nothing, so this is also how your own games load.
  const showGameFromUrl = useCallback(() => {
    const gameId = getGameIdFromUrl()
    latestLoad.current += 1
    const thisLoad = latestLoad.current
    changeTypedWord('')
    setRowHasProblem(false)

    if (gameId === null) {
      setGame(null)
      setMessage('') // don't leave a message from the previous game on screen
      setIsLoadingGame(false)
      return
    }
    setIsLoadingGame(true)
    joinGame(gameId)
      .then((loadedGame) => {
        if (thisLoad !== latestLoad.current) {
          return // a newer load has started since; ignore this stale answer
        }
        setGame(loadedGame)
        setMessage('')
        setIsLoadingGame(false)
        refreshGames() // a game joined through a link now belongs in "Your games"
      })
      .catch((error) => {
        if (thisLoad !== latestLoad.current) {
          return
        }
        // the link points to a game that doesn't exist, isn't a valid ID, or is already full
        clearGameIdFromUrl()
        setGame(null)
        setMessage(errorText(error))
        setIsLoadingGame(false)
      })
  }, [refreshGames, changeTypedWord])

  // Run it on first load, and again whenever the player uses the browser's Back or Forward
  // buttons to move between games.
  useEffect(() => {
    showGameFromUrl()
    refreshGames()
    window.addEventListener('popstate', showGameFromUrl)
    return () => window.removeEventListener('popstate', showGameFromUrl)
  }, [showGameFromUrl, refreshGames])

  // Switch to another of the player's games, from the "Your games" list.
  function openGame(gameId) {
    if (gameId === getGameIdFromUrl()) {
      return // already showing it; don't add a duplicate entry to the browser's history
    }
    setGameIdInUrl(gameId)
    showGameFromUrl()
  }

  // While a game is in progress, keep a WebSocket open to the server. The server sends a
  // short notice on it whenever the game changes (another player guessed, or joined), and
  // the page then fetches the game, so a shared board updates without anyone refreshing.
  const gameId = game !== null ? game.id : null
  const isInProgress = game !== null && game.status === 'in_progress'
  useEffect(() => {
    if (gameId === null || !isInProgress) {
      return
    }
    let socket = null
    let reconnectTimer = null
    let checkTimer = null // set while the fallback timer is running
    let failedAttempts = 0
    let isFinished = false // set when this game is no longer on screen, or has ended

    // Fetch the game and show it if it has anything new.
    function fetchLatest() {
      getGame(gameId)
        .then((latest) => {
          if (isFinished) {
            return
          }
          setGame((current) => {
            if (current === null || current.id !== latest.id) {
              return current // the player has moved to a different game meanwhile
            }
            // only accept news: never replace the board with an older copy of itself
            const hasNews =
              latest.guesses.length > current.guesses.length ||
              latest.status !== current.status ||
              latest.players.length !== current.players.length
            return hasNews ? latest : current
          })
          if (latest.status !== 'in_progress') {
            refreshGames() // another player finished it: update its status in "Your games"
          }
        })
        .catch(() => {
          // a missed update is harmless; the next notice, or the next reconnect, catches up
        })
    }

    // The fallback for when there is no connection: ask on a timer instead of being told.
    function startCheckingOnATimer() {
      if (checkTimer === null) {
        checkTimer = setInterval(fetchLatest, NO_CONNECTION_CHECK_MS)
      }
    }

    function stopCheckingOnATimer() {
      clearInterval(checkTimer)
      checkTimer = null
    }

    function connect() {
      socket = openGameSocket(gameId)
      socket.onopen = () => {
        failedAttempts = 0
        stopCheckingOnATimer() // the server tells us about changes again
        // anything that happened while there was no connection was not announced, so look now
        fetchLatest()
      }
      socket.onmessage = () => fetchLatest()
      socket.onclose = (event) => {
        if (isFinished) {
          return // we closed it ourselves
        }
        if (REFUSED.includes(event.code)) {
          if (event.code === SOCKET_CLOSED_NOT_AUTHENTICATED) {
            // The sign-in has ended. This request gets the same answer, and api.js then
            // takes the page back to the sign-in form.
            fetchLatest()
          }
          return
        }
        // No connection from here on, so keep the board up to date the slow way.
        startCheckingOnATimer()
        if (event.code === SOCKET_CLOSED_TOO_MANY_CONNECTIONS) {
          return // too many tabs open; asking for another connection would be refused again
        }
        // dropped (the server restarted, or the network blinked): try again, a little later each time
        const delay = Math.min(FIRST_RECONNECT_DELAY_MS * 2 ** failedAttempts, LONGEST_RECONNECT_DELAY_MS)
        failedAttempts += 1
        reconnectTimer = setTimeout(connect, delay)
      }
    }

    connect()
    // close the connection when the game changes or ends, so there is never more than one
    return () => {
      isFinished = true
      clearTimeout(reconnectTimer)
      stopCheckingOnATimer()
      socket.close()
    }
  }, [gameId, isInProgress, refreshGames])

  async function startGame() {
    if (isStartingGame.current) {
      return // a new game is already being created; ignore the extra click
    }
    isStartingGame.current = true
    // Starting a game counts as a load. A game that was still loading from a link is now
    // out of date, and its answer will be ignored when it arrives.
    latestLoad.current += 1
    const thisLoad = latestLoad.current
    try {
      const newGame = await createGame(wordLength)
      if (thisLoad !== latestLoad.current) {
        // The player opened another game while this one was being created. Leave that game
        // on screen; the new one is saved and appears in "Your games".
        refreshGames()
        return
      }
      setGameIdInUrl(newGame.id)
      setGame(newGame)
      setIsLoadingGame(false)
      changeTypedWord('')
      setMessage('')
      setRowHasProblem(false)
      refreshGames()
    } catch (error) {
      if (thisLoad !== latestLoad.current) {
        return // about a game the player has already moved on from
      }
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
      // - a guess for this game is already on its way to the server
      if (game === null || game.status !== 'in_progress' || submittingForGame.current === game.id) {
        return
      }
      // read the word from the ref, so this is right even if several keys arrive before a redraw
      const typedWord = typedWordRef.current
      // if it's "Enter" on the on-screen Enter Key or the keyboard
      if (key === 'Enter') {
        // reject submission if there are not enough letters
        if (typedWord.length !== game.word_length) {
          setMessage('Not enough letters')
          // flag row
          setRowHasProblem(true)
          return
        }
        submittingForGame.current = game.id
        // Each step below waits for the server, and the player may open a different game
        // while it does. The address bar always names the game the player chose last, so
        // after each wait: if it no longer names this game, leave the screen alone.
        const isStillOpen = () => getGameIdFromUrl() === game.id
        try {
          // Step 1: send the guess.
          try {
            await submitGuess(game.id, typedWord)
          } catch (error) {
            if (!isStillOpen()) {
              return // the message would appear on a different game
            }
            setMessage(errorText(error))
            if (error.code === 'GAME_OVER') {
              // The game was finished somewhere else (another tab, or another player).
              // Reload it so this board shows the final result instead of staying stale.
              changeTypedWord('')
              setRowHasProblem(false)
              const finishedGame = await getGame(game.id)
              if (isStillOpen()) {
                setGame(finishedGame)
              }
            } else {
              // an invalid word lands here; the typed letters stay so the player can fix them
              setRowHasProblem(error.code === 'INVALID_GUESS')
            }
            return
          }

          if (!isStillOpen()) {
            refreshGames() // the guess is saved; only "Your games" needs to know
            return
          }

          // Step 2: the guess is saved. Clear the typed letters straight away, so that if the
          // reload below fails, pressing Enter again can't submit the same word a second time.
          changeTypedWord('')
          setMessage('')
          setRowHasProblem(false)

          // Step 3: the server owns the game, so reload it rather than updating our own copy.
          const reloadedGame = await getGame(game.id)
          if (isStillOpen()) {
            setGame(reloadedGame)
          }
          refreshGames() // keep the guess count and status in "Your games" up to date
        } catch (error) {
          // only a failed reload reaches here: the guess (if any) is safe on the server
          if (isStillOpen()) {
            setMessage(errorText(error))
          }
        } finally {
          if (submittingForGame.current === game.id) {
            submittingForGame.current = null
          }
        }
      } else if (key === 'Backspace') {
        changeTypedWord(typedWord.slice(0, -1))
        setMessage('')
        setRowHasProblem(false)
      } else if (/^[a-zA-Z]$/.test(key) && typedWord.length < game.word_length) {
        changeTypedWord(typedWord + key.toLowerCase())
        setMessage('')
        setRowHasProblem(false)
      }
    },
    [game, refreshGames, changeTypedWord],
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
    games,
    hasMoreGames: nextGamesCursor !== null,
    loadMoreGames,
    openGame,
  }
}
