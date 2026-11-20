// errorText.js and gameUrl.js: the two small modules with no React in them.
import { describe, expect, it } from 'vitest'
import { errorText } from './errorText'
import {
  clearGameIdFromUrl,
  getGameIdFromUrl,
  getUserWhoOpenedGameInUrl,
  markGameInUrlAsOpenedBy,
  setGameIdInUrl,
} from './gameUrl'
import { apiError } from './test/factories'

describe('errorText', () => {
  // it.each runs the same test once per row; %s in its name is replaced by the row's code
  it.each([
    ['GAME_NOT_FOUND', "That game doesn't exist. Start a new one?"],
    ['GAME_OVER', 'This game has already finished.'],
    ['INVALID_REQUEST', "That link or request isn't valid. Start a new game?"],
    ['NETWORK_ERROR', "Can't reach the game server. Is it running?"],
    ['NOT_AUTHENTICATED', 'Please sign in to continue.'],
    ['INVALID_CREDENTIALS', 'Wrong username or password.'],
    ['USERNAME_TAKEN', 'That username is taken. Try another, or sign in.'],
    ['NOT_A_PLAYER', "You're not a player in that game."],
    ['GAME_FULL', 'That game already has the maximum number of players.'],
    ['CSRF_CHECK_FAILED', 'This page is out of date. Refresh it and try again.'],
    ['NO_WORDS_AVAILABLE', "The word lists aren't loaded yet. Try again in a moment."],
    ['TOO_MANY_ATTEMPTS', 'Too many attempts. Wait a few minutes and try again.'],
  ])('has a plain sentence for %s', (code, sentence) => {
    expect(errorText(apiError(code, 'technical detail from the backend'))).toBe(sentence)
  })

  it("keeps the backend's wording for a rejected word, which names the word", () => {
    const error = apiError('INVALID_GUESS', "'zzzzz' is not in the word list")

    expect(errorText(error)).toBe("'zzzzz' is not in the word list")
  })

  it('never shows technical detail for a code it does not know', () => {
    const error = apiError('BRAND_NEW_CODE', 'game_id: Input should be a valid UUID')

    expect(errorText(error)).toBe('Something went wrong. Please try again.')
  })

  it('copes with an error that has no code at all', () => {
    expect(errorText(new Error('boom'))).toBe('Something went wrong. Please try again.')
  })
})

describe('gameUrl', () => {
  it('finds no game in a plain address', () => {
    expect(getGameIdFromUrl()).toBeNull()
  })

  it('reads the game from the address', () => {
    window.history.replaceState({}, '', '/?game=abc-123')

    expect(getGameIdFromUrl()).toBe('abc-123')
  })

  it('treats an empty game in the address as no game', () => {
    window.history.replaceState({}, '', '/?game=')

    expect(getGameIdFromUrl()).toBeNull()
  })

  it('puts a game in the address', () => {
    setGameIdInUrl('abc-123')

    expect(window.location.search).toBe('?game=abc-123')
    expect(getGameIdFromUrl()).toBe('abc-123')
  })

  it('replaces the game already in the address', () => {
    setGameIdInUrl('first')
    setGameIdInUrl('second')

    expect(window.location.search).toBe('?game=second')
  })

  it('adds a history entry for each game, so Back returns to the previous one', () => {
    const before = window.history.length

    setGameIdInUrl('first')
    setGameIdInUrl('second')

    expect(window.history.length).toBe(before + 2)
  })

  it('removes the game from the address without adding a history entry', () => {
    window.history.replaceState({}, '', '/?game=abc-123')
    const before = window.history.length

    clearGameIdFromUrl()

    expect(getGameIdFromUrl()).toBeNull()
    expect(window.location.search).toBe('')
    expect(window.history.length).toBe(before)
  })

  it('records which player opened a game', () => {
    setGameIdInUrl('abc-123', 'user-erica')

    expect(getUserWhoOpenedGameInUrl()).toBe('user-erica')
  })

  it('knows a freshly opened link was opened by nobody yet', () => {
    window.history.replaceState(null, '', '/?game=abc-123')

    expect(getUserWhoOpenedGameInUrl()).toBeNull()
  })

  it('rewrites the game in the address to the spelling it is given', () => {
    window.history.replaceState(null, '', '/?game=ABC-123')
    const before = window.history.length

    markGameInUrlAsOpenedBy('user-erica', 'abc-123')

    expect(getGameIdFromUrl()).toBe('abc-123')
    expect(getUserWhoOpenedGameInUrl()).toBe('user-erica')
    expect(window.history.length).toBe(before)
  })

  it('can mark the game already in the address without adding a history entry', () => {
    window.history.replaceState(null, '', '/?game=abc-123')
    const before = window.history.length

    markGameInUrlAsOpenedBy('user-erica')

    expect(getUserWhoOpenedGameInUrl()).toBe('user-erica')
    expect(window.location.search).toBe('?game=abc-123')
    expect(window.history.length).toBe(before)
  })

  it('forgets who opened the game when the game is removed from the address', () => {
    setGameIdInUrl('abc-123', 'user-erica')

    clearGameIdFromUrl()

    expect(getUserWhoOpenedGameInUrl()).toBeNull()
  })

  it('leaves the rest of the address alone', () => {
    window.history.replaceState({}, '', '/?theme=dark&game=abc-123')

    clearGameIdFromUrl()

    expect(window.location.search).toBe('?theme=dark')
  })
})
