// errorText.js and gameUrl.js: the two small modules with no React in them.
import { describe, expect, it } from 'vitest'
import { errorText } from './errorText'
import { clearGameIdFromUrl, getGameIdFromUrl, setGameIdInUrl } from './gameUrl'
import { apiError } from './test/factories'

describe('errorText', () => {
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

  it('leaves the rest of the address alone', () => {
    window.history.replaceState({}, '', '/?theme=dark&game=abc-123')

    clearGameIdFromUrl()

    expect(window.location.search).toBe('?theme=dark')
  })
})
