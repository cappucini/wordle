// The current game's ID lives in the page address, for example:
//   http://localhost:5173/?game=3f2b8c1e-...
// That makes a game survive a refresh, and makes its link shareable and bookmarkable.

const GAME_PARAM = 'game'

// Returns the game ID in the address bar, or null if there isn't one.
// An address ending in "?game=" names no game, so it counts as not having one.
export function getGameIdFromUrl() {
  // URLSearchParams reads the part of the address after "?"; get() gives null if "game" is absent
  const gameId = new URLSearchParams(window.location.search).get(GAME_PARAM)
  return gameId === null || gameId === '' ? null : gameId
}

// Each history entry the app creates also records which player opened that game. The
// browser keeps this with the entry, so it is still there after Back, Forward or a refresh.
// It is how the page tells "a link someone just opened" (no record yet: opening it joins
// the game) from "an address left behind by whoever used this browser before" (their
// record: the next player must not be joined to it just by pressing Back).
const OPENED_BY = 'wordleOpenedBy'

// The ID of the player who opened the game in the address bar, or null for a fresh link.
export function getUserWhoOpenedGameInUrl() {
  const state = window.history.state
  return state !== null && typeof state === 'object' && state[OPENED_BY] ? state[OPENED_BY] : null
}

// Records the current address as opened by this player, without adding a history entry.
//
// `gameId` is the game's ID as the server wrote it. When given, the address is rewritten to
// use exactly that. The server accepts the same ID written other ways (in capitals, or
// without its hyphens), but the page compares the address with the server's ID to tell
// which game is open, so the two must be spelled the same.
export function markGameInUrlAsOpenedBy(userId, gameId) {
  const url = new URL(window.location.href)
  if (gameId !== undefined) {
    url.searchParams.set(GAME_PARAM, gameId)
  }
  // { [OPENED_BY]: userId } uses the constant's value as the key: { wordleOpenedBy: userId }.
  // The arguments are (state to keep with the entry, an unused title, the address).
  window.history.replaceState({ [OPENED_BY]: userId }, '', url)
}

// Puts a game ID in the address bar without reloading the page, recorded as opened by this player.
// pushState adds a history entry, so the browser's Back button returns to the previous game.
export function setGameIdInUrl(gameId, userId) {
  const url = new URL(window.location.href)
  url.searchParams.set(GAME_PARAM, gameId)
  window.history.pushState({ [OPENED_BY]: userId }, '', url)
}

// Removes the game ID from the address bar, for a link to a game that doesn't exist.
// replaceState swaps the current history entry, so Back doesn't return to the broken link.
export function clearGameIdFromUrl() {
  const url = new URL(window.location.href)
  url.searchParams.delete(GAME_PARAM)
  window.history.replaceState({}, '', url)
}
