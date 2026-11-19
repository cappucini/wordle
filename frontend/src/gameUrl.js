// The current game's ID lives in the page address, for example:
//   http://localhost:5173/?game=3f2b8c1e-...
// That makes a game survive a refresh, and makes its link shareable and bookmarkable.

const GAME_PARAM = 'game'

// Returns the game ID in the address bar, or null if there isn't one.
// An address ending in "?game=" names no game, so it counts as not having one.
export function getGameIdFromUrl() {
  const gameId = new URLSearchParams(window.location.search).get(GAME_PARAM)
  return gameId === null || gameId === '' ? null : gameId
}

// Puts a game ID in the address bar without reloading the page.
// pushState adds a history entry, so the browser's Back button returns to the previous game.
export function setGameIdInUrl(gameId) {
  const url = new URL(window.location.href)
  url.searchParams.set(GAME_PARAM, gameId)
  window.history.pushState({}, '', url)
}

// Removes the game ID from the address bar, for a link to a game that doesn't exist.
// replaceState swaps the current history entry, so Back doesn't return to the broken link.
export function clearGameIdFromUrl() {
  const url = new URL(window.location.href)
  url.searchParams.delete(GAME_PARAM)
  window.history.replaceState({}, '', url)
}
