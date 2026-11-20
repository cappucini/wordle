// Everything the game screen does: loading and starting games, typing and submitting
// guesses, the games list, and live updates from other players over a WebSocket.
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
import {
  clearGameIdFromUrl,
  getGameIdFromUrl,
  getUserWhoOpenedGameInUrl,
  markGameInUrlAsOpenedBy,
  setGameIdInUrl,
} from '../gameUrl'

// If the connection that reports other players' guesses drops, the page reconnects:
// after 1 second, then 2, 4, 8, and at most every 10 seconds after that.
const FIRST_RECONNECT_DELAY_MS = 1000
const LONGEST_RECONNECT_DELAY_MS = 10000

// While there is no connection (it dropped, or the network doesn't allow WebSockets at all),
// the page falls back to asking the server this often, so a shared board still updates.
const NO_CONNECTION_CHECK_MS = 5000

// close codes after which reconnecting is pointless: the backend refused on purpose
const REFUSED = [SOCKET_CLOSED_NOT_A_PLAYER, SOCKET_CLOSED_GAME_NOT_FOUND]

// Two answers about the same game can arrive out of order: a slow reply may describe the game
// as it was before a faster one. This picks which copy to show, so the board never steps back.
// `current` is the game on screen; `incoming` is the copy that has just arrived.
function newestCopy(current, incoming) {
  if (current === null || current.id !== incoming.id) {
    return incoming // nothing to compare with: a different game, or none on screen yet
  }
  const isOlder =
    incoming.guesses.length < current.guesses.length ||
    incoming.players.length < current.players.length ||
    // a finished game never goes back to being in progress
    (incoming.status === 'in_progress' && current.status !== 'in_progress')
  return isOlder ? current : incoming
}

// True if `incoming` shows something the copy on screen does not: another guess, another
// player, or the game having finished. False for an identical copy and for an older one.
function hasNewsFor(current, incoming) {
  if (newestCopy(current, incoming) !== incoming) {
    return false // it is the older of the two
  }
  return (
    incoming.guesses.length !== current.guesses.length ||
    incoming.players.length !== current.players.length ||
    incoming.status !== current.status
  )
}

// Holds everything the game screen needs to know, and the actions that change it.
// Components only display what this returns; they never call the API themselves.
// This is called from GameScreen.jsx, which is only shown once a player has signed in.
// `user` is the signed-in player ({ id, username }).
// `isTypingPaused` is true while something is open over the game (the "How to play" panel),
// so key presses meant for it are not typed onto the board.
// `{ isTypingPaused = false } = {}` makes the second argument optional: leaving it out,
// or leaving that one option out, both mean "not paused".
export function useGame(user, { isTypingPaused = false } = {}) {
  const userId = user.id
  // Every call useState() dedicates a piece of state with a given starting value.
  // They belong to the page's working memory, and will be wiped on refresh.
  const [config, setConfig] = useState(null) // the rules, from the backend
  const [wordLength, setWordLength] = useState(5) // the length picked for the next game
  const [game, setGame] = useState(null) // the game being played, from the backend
  const [typedWord, setTypedWord] = useState('') // the guess being typed
  const [message, setMessage] = useState('')
  // Why the rules could not be loaded, or '' if they were (or are still on their way).
  // Kept apart from `message`, which is cleared whenever a game loads: without the rules
  // the screen cannot be drawn, so this must stay until they arrive.
  const [configError, setConfigError] = useState('')
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
  // [] means this function is made once and never replaced
  }, [])
  // true when the message is about the word being typed, so only then does the row shake
  const [rowHasProblem, setRowHasProblem] = useState(false)
  // true while a game named in the address bar is being fetched, so the page can wait
  // instead of briefly showing the "start a game" hint
  // (passing a function makes React work the starting value out once, not on every redraw)
  const [isLoadingGame, setIsLoadingGame] = useState(() => getGameIdFromUrl() !== null)
  // a ref, not state: it must change immediately so a double-click can't start two games
  const isStartingGame = useRef(false)
  // "Your games": the signed-in player's games, newest first, loaded a page at a time
  const [games, setGames] = useState([])
  const [nextGamesCursor, setNextGamesCursor] = useState(null) // null when there are no more pages
  // Counts the game loads started. If Back and Forward are pressed quickly, an older request
  // can finish after a newer one; its answer is ignored so the wrong game never shows.
  const latestLoad = useRef(0)

  // Loads the game settings from the backend. Called once when the game screen first
  // appears, and again if the player clicks "Try again" after it failed.
  const loadConfig = useCallback(() => {
    // sends request and returns a promise
    getConfig()
    // ...when the result arrives, run the function inside
      .then((rules) => {
        // store the rules from config including min_word_length, max_word_length, default_word_length, extra_guesses
        setConfig(rules)
        // set the word length from rules
        setWordLength(rules.default_word_length)
        setConfigError('')
      })
      .catch((error) => {
        setMessage(errorText(error))
        setConfigError(errorText(error))
      })
  }, [])

  // Runs once, when the game screen first appears.
  useEffect(() => {
    loadConfig()
  // loadConfig never changes, so this runs once, after the page is first drawn
  }, [loadConfig])

  // "Try again" on the screen shown when the rules could not be loaded.
  function retryConfig() {
    setConfigError('')
    loadConfig()
  }

  // How many games "Your games" is showing, and whether a "Show more" request is under way.
  // Refs, because the functions below need the current values the moment they run.
  const shownGamesCount = useRef(0)
  const isLoadingMoreGames = useRef(false)
  // Counts the list refreshes sent, so an older one that answers late can be ignored.
  const latestListRefresh = useRef(0)
  // refreshGames itself, for the one place it needs to call itself (set just below it)
  const refreshGamesAgain = useRef(() => {})

  // Fetch the player's games again from the top. Called on load and whenever the list may
  // have changed (a game was started, joined or finished).
  // It asks for as many games as are already showing, in whole pages, so a player who has
  // clicked "Show more" keeps those extra games instead of dropping back to the first page.
  const refreshGames = useCallback(() => {
    // for example: 14 games showing is 2 pages, so ask for 20, but never more than the
    // backend allows in one request
    const limitForShownGames = () => {
      const pagesShown = Math.max(1, Math.ceil(shownGamesCount.current / GAMES_PAGE_SIZE))
      return Math.min(pagesShown * GAMES_PAGE_SIZE, MAX_GAMES_PAGE_SIZE)
    }
    const limit = limitForShownGames()
    // number this refresh: its answer only counts if no later refresh has started by then
    latestListRefresh.current += 1
    const thisRefresh = latestListRefresh.current
    listGames(null, limit)
      .then((page) => {
        if (thisRefresh !== latestListRefresh.current) {
          return // a newer refresh has been sent since; its answer is the one to show
        }
        if (limitForShownGames() > limit) {
          // "Show more" added a page while this was on its way. This answer is too short
          // to replace the list without losing that page, so ask again for all of it.
          refreshGamesAgain.current()
          return
        }
        shownGamesCount.current = page.items.length
        setGames(page.items)
        setNextGamesCursor(page.next_cursor)
      })
      .catch(() => {
        // the list is a convenience; a failure here shouldn't interrupt the game on screen
      })
  }, [])
  useEffect(() => {
    refreshGamesAgain.current = refreshGames
  }, [refreshGames])

  // Fetch the next page and add it to the end of the list.
  function loadMoreGames() {
    if (nextGamesCursor === null || isLoadingMoreGames.current) {
      return // nothing more to fetch, or the next page is already on its way (a double-click)
    }
    isLoadingMoreGames.current = true
    listGames(nextGamesCursor)
      .then((page) => {
        // the function form is given the list as it is now, not as it was when the request began
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
  //
  // Normally it joins the game first: opening a link someone shared is how a player joins
  // their game, and joining a game you are already in changes nothing, so this is also how
  // your own games load.
  //
  // The exception is an address that a *different* player opened on this browser (reached
  // with Back, or left in the address bar when their sign-in ended). That is not an
  // invitation, so the game is only read: it shows if this player happens to be in it too,
  // and otherwise they are told they are not a player. Nobody is joined by pressing Back.
  //
  // `keepMessage` is true when the message on screen explains something that has just gone
  // wrong (a failed "New game") and should still be there once the game has loaded.
  const loadGameFromUrl = useCallback((keepMessage) => {
    const gameId = getGameIdFromUrl()
    // number this load: its answer only counts if no later load has started by then
    latestLoad.current += 1
    const thisLoad = latestLoad.current
    changeTypedWord('')
    setRowHasProblem(false)

    if (gameId === null) {
      setGame(null)
      if (!keepMessage) {
        setMessage('') // don't leave a message from the previous game on screen
      }
      setIsLoadingGame(false)
      return
    }
    const openedBy = getUserWhoOpenedGameInUrl()
    const wasOpenedByAnotherPlayer = openedBy !== null && openedBy !== userId
    setIsLoadingGame(true)
    const load = wasOpenedByAnotherPlayer ? getGame(gameId) : joinGame(gameId)
    load
      .then((loadedGame) => {
        if (thisLoad !== latestLoad.current) {
          return // a newer load has started since; ignore this stale answer
        }
        // This player is in the game: the address is theirs now. It is also rewritten to
        // the ID as the server spells it, in case the link had it in capitals or without
        // hyphens; the checks below ("is this game still the one open?") compare the two.
        markGameInUrlAsOpenedBy(userId, loadedGame.id)
        setGame(loadedGame)
        if (!keepMessage) {
          setMessage('')
        }
        setIsLoadingGame(false)
        refreshGames() // a game joined through a link now belongs in "Your games"
      })
      .catch((error) => {
        if (thisLoad !== latestLoad.current) {
          return
        }
        if (error.code === 'NOT_AUTHENTICATED') {
          // The sign-in has ended, and api.js is taking the page back to the sign-in form.
          // Leave the game in the address, so signing in again returns to it.
          setIsLoadingGame(false)
          return
        }
        // the link points to a game that doesn't exist, isn't a valid ID, or is already full
        clearGameIdFromUrl()
        setGame(null)
        setMessage(errorText(error))
        setIsLoadingGame(false)
      })
  }, [refreshGames, changeTypedWord, userId])

  // The usual way in: any message left on screen belongs to the game being left.
  const showGameFromUrl = useCallback(() => loadGameFromUrl(false), [loadGameFromUrl])

  // Stop caring about any game that is still loading or being created. Called when the
  // player signs out: an answer that arrives after that must not put a game back in the
  // address, where the next person to sign in on this browser would find it.
  function cancelLoading() {
    latestLoad.current += 1
  }

  // Run it on first load, and again whenever the player uses the browser's Back or Forward
  // buttons to move between games.
  useEffect(() => {
    showGameFromUrl()
    refreshGames()
    // the browser fires "popstate" when Back or Forward changes the address without a reload
    window.addEventListener('popstate', showGameFromUrl)
    // clean-up: stop listening when this screen goes away, or before the effect runs again
    return () => window.removeEventListener('popstate', showGameFromUrl)
  }, [showGameFromUrl, refreshGames])

  // Switch to another of the player's games, from the "Your games" list.
  function openGame(gameId) {
    if (gameId === getGameIdFromUrl()) {
      return // already showing it; don't add a duplicate entry to the browser's history
    }
    setGameIdInUrl(gameId, userId)
    showGameFromUrl()
  }

  // While a game is in progress, keep a WebSocket open to the server. The server sends a
  // short notice on it whenever the game changes (another player guessed, or joined), and
  // the page then fetches the game, so a shared board updates without anyone refreshing.
  const gameId = game !== null ? game.id : null
  const isInProgress = game !== null && game.status === 'in_progress'
  // The game on screen, readable from inside the connection's callbacks below, which are
  // set up once per game and would otherwise only see the game as it was at that moment.
  const gameOnScreen = useRef(game)
  useEffect(() => {
    gameOnScreen.current = game
  }, [game])
  useEffect(() => {
    // no game, or a finished one: nothing more can change, so no connection is needed
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
          // the function form compares against the game on screen now, not the one from when
          // the request was sent
          setGame((current) => {
            if (current === null || current.id !== latest.id) {
              return current // the player has moved to a different game meanwhile
            }
            // answers can arrive out of order: never replace the board with an older copy
            return hasNewsFor(current, latest) ? latest : current
          })
          // Another player guessed, joined or finished the game: its entry in "Your games"
          // (guess count, small board, status) needs to follow.
          const shown = gameOnScreen.current
          if (shown !== null && shown.id === latest.id && hasNewsFor(shown, latest)) {
            refreshGames()
          }
        })
        .catch(() => {
          // a missed update is harmless; the next notice, or the next reconnect, catches up
        })
    }

    // The fallback for when there is no connection: ask on a timer instead of being told.
    function startCheckingOnATimer() {
      if (checkTimer === null) {
        checkTimer = setInterval(() => {
          if (!document.hidden) {
            fetchLatest() // not from a tab nobody is looking at
          }
        }, NO_CONNECTION_CHECK_MS)
      }
    }

    // Stops the fallback timer: there is a connection again, or this game is done with.
    function stopCheckingOnATimer() {
      clearInterval(checkTimer)
      checkTimer = null
    }

    // Opens the WebSocket and says what to do when it opens, sends a notice, or closes.
    // When the connection drops, this is called again after a delay.
    function connect() {
      try {
        socket = openGameSocket(gameId)
      } catch {
        // The browser refused to even try (for example an insecure ws:// address on an
        // https page). Trying again would be refused the same way, so check on a timer.
        socket = null
        startCheckingOnATimer()
        return
      }
      socket.onopen = () => {
        failedAttempts = 0
        stopCheckingOnATimer() // the server tells us about changes again
        // anything that happened while there was no connection was not announced, so look now
        fetchLatest()
      }
      // any message means "the game changed"; what it says is not needed
      socket.onmessage = () => fetchLatest()
      socket.onclose = (event) => {
        if (isFinished) {
          return // we closed it ourselves
        }
        // refused on purpose (not a player, or no such game): no retry, and no timer either
        if (REFUSED.includes(event.code)) {
          return
        }
        if (event.code === SOCKET_CLOSED_NOT_AUTHENTICATED) {
          // The server believes the sign-in has ended. Ask straight away: if it has, this
          // request gets a 401 and api.js takes the page back to the sign-in form (which
          // removes this screen and its timers). If the sign-in was extended since the
          // connection opened, the request succeeds and we simply reconnect below.
          fetchLatest()
        }
        // No connection from here on, so keep the board up to date the slow way.
        startCheckingOnATimer()
        if (event.code === SOCKET_CLOSED_TOO_MANY_CONNECTIONS) {
          return // too many tabs open; asking for another connection would be refused again
        }
        // dropped (the server restarted, or the network blinked): try again, a little later each time
        // 2 ** failedAttempts doubles the wait each time (1s, 2s, 4s, 8s); Math.min caps it at 10s
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
      if (socket !== null) {
        socket.close()
      }
    }
  // when the game on screen changes or ends, React runs the clean-up above and then the
  // whole effect again for the new values
  }, [gameId, isInProgress, refreshGames])

  // Creates a new game with the chosen word length and puts it on screen.
  // Called when "New game" is clicked.
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
      setGameIdInUrl(newGame.id, userId)
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
      // Clicking "New game" abandoned any game that was still loading (see above). No new
      // game came of it, so if the address names a game that is not the one on screen,
      // load that after all. Otherwise the board and the address would disagree and the
      // page would wait for ever for an answer it has already thrown away.
      const shownGameId = game !== null ? game.id : null
      if (getGameIdFromUrl() !== shownGameId) {
        loadGameFromUrl(true) // true: keep the message that says why "New game" failed
      } else {
        setIsLoadingGame(false)
      }
    } finally {
      isStartingGame.current = false
    }
  }

  // Handles one key press.
  // Every key press ends up here, including on-screen keyboard and physical keyboard.
  const pressKey = useCallback(
    async (key) => {
      // Ignore key when:
      // - no game has been started yet
      // - game is already won or lost
      // - a guess for this game is already on its way to the server
      // - another game is loading: the board still shows the game being left, and a word
      //   typed now would be guessed in that one
      // - the rules have not loaded: the screen shows no board, so nothing typed can be seen
      if (
        game === null ||
        game.status !== 'in_progress' ||
        submittingForGame.current === game.id ||
        isLoadingGame ||
        config === null
      ) {
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
                setGame((current) => newestCopy(current, finishedGame))
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
          // Another player's guess may have reached the board while this reload was on its
          // way, so keep whichever copy is newer rather than always taking this one.
          const reloadedGame = await getGame(game.id)
          if (isStillOpen()) {
            setGame((current) => newestCopy(current, reloadedGame))
          }
          refreshGames() // keep the guess count and status in "Your games" up to date
        } catch (error) {
          // only a failed reload reaches here: the guess (if any) is safe on the server
          if (isStillOpen()) {
            setMessage(errorText(error))
          }
        } finally {
          // unlock the keyboard, unless the lock now belongs to a guess for another game
          if (submittingForGame.current === game.id) {
            submittingForGame.current = null
          }
        }
      } else if (key === 'Backspace') {
        // slice(0, -1) is the word without its last letter
        changeTypedWord(typedWord.slice(0, -1))
        setMessage('')
        setRowHasProblem(false)
      // a single letter (not a key such as "Shift" or "Tab"), and the row still has room
      } else if (/^[a-zA-Z]$/.test(key) && typedWord.length < game.word_length) {
        changeTypedWord(typedWord + key.toLowerCase())
        setMessage('')
        setRowHasProblem(false)
      }
    },
    // pressKey is rebuilt when any of these change, so it never works from an old game
    [game, isLoadingGame, config, refreshGames, changeTypedWord],
  )

  // Listen to the physical keyboard.
  useEffect(() => {
    // Passes a physical key press on to pressKey, unless it is one to leave alone.
    function handleKeyDown(event) {
      if (isTypingPaused) {
        return // the board is not listening right now; what was typed so far is kept
      }
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
  }, [pressKey, isTypingPaused])

  return {
    config,
    // why the rules could not be loaded ('' if they were), and a function to try again
    configError,
    retryConfig,
    // called when the player signs out: forgets any game still loading
    cancelLoading,
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
    // the backend sends a cursor only while another page exists
    hasMoreGames: nextGamesCursor !== null,
    loadMoreGames,
    openGame,
  }
}
