// Builds the objects the backend sends, so each test only spells out what it cares about.

// the one-letter codes makeGuess accepts, and the result each stands for
const RESULTS = { C: 'correct', P: 'present', A: 'absent' }

// two players for tests to sign in as
export const ERICA = { id: 'user-erica', username: 'erica' }
export const SAM = { id: 'user-sam', username: 'sam' }

// the rules, as the backend's /config sends them
export const CONFIG = {
  min_word_length: 5,
  max_word_length: 8,
  default_word_length: 5,
  extra_guesses: 1,
  max_players_per_game: 3,
}

// makeGuess('react', 'PPCPA') is the guess "react" against the answer "crane":
// C = correct, P = present, A = absent, one letter per tile.
export function makeGuess(word, pattern, guessedBy = ERICA.username, number = 1) {
  return {
    number: number,
    word: word,
    results: pattern.split('').map((letter) => RESULTS[letter]),
    guessed_by: guessedBy,
  }
}

// A game as the backend sends it. With no arguments: five letters, in progress, erica
// playing alone, no guesses. Pass `overrides` to change any of its fields.
export function makeGame(overrides = {}) {
  // ?? means "use the right-hand side when the left is null or undefined"
  const wordLength = overrides.word_length ?? 5
  // copy each guess and number it by its position, whatever number it came with
  const guesses = (overrides.guesses ?? []).map((guess, index) => ({ ...guess, number: index + 1 }))
  const maxGuesses = wordLength + 1
  return {
    id: 'game-1',
    word_length: wordLength,
    max_guesses: maxGuesses,
    guesses_remaining: maxGuesses - guesses.length,
    status: 'in_progress',
    answer: null,
    created_at: '2026-01-01T00:00:00Z',
    owner_id: ERICA.id,
    players: [ERICA],
    max_players: 3,
    // spread last, so anything the test passed replaces the defaults above...
    ...overrides,
    // ...except the guesses, which are always the renumbered list
    guesses: guesses,
  }
}

// An error shaped like the ones api.js throws.
export function apiError(code, message = code) {
  const error = new Error(message)
  error.code = code
  return error
}
