// The rules of the game, written once and shown in two places:
//   - beside the sign-in form (HowToPlay, the default export)
//   - in the "How to play" panel a player can open from the bar while playing (Rules)
// The sample tiles are decoration (hidden from screen readers); the sentence beside each
// one carries the meaning.
const RESULTS = [
  { letter: 'a', result: 'correct', meaning: 'Green: the right letter in the right place.' },
  { letter: 'r', result: 'present', meaning: 'Yellow: in the word, but somewhere else.' },
  { letter: 't', result: 'absent', meaning: 'Grey: not in the word.' },
]

// The rules themselves: how long words are, how many guesses, and what each colour means.
// The numbers are the game's settings. The in-game panel passes the real ones from the
// backend; the sign-in page has not loaded them yet, so it uses these defaults, which
// match the backend's own (backend/app/domain/rules.py).
export function Rules({ minLength = 5, maxLength = 8, extraGuesses = 1 }) {
  // the sentence reads differently when only one word length is allowed
  const lengths =
    minLength === maxLength
      ? `Words have ${minLength} letters`
      : `Words run from ${minLength} to ${maxLength} letters`
  const guesses = extraGuesses === 1 ? 'one more guess' : `${extraGuesses} more guesses`
  return (
    <>
      <p className="lead">
        {lengths}, and you get {guesses} than the word has letters.
      </p>
      {/* <dl> is a description list: each <dt> (a sample tile) is explained by its <dd> */}
      <dl className="legend">
        {RESULTS.map(({ letter, result, meaning }) => (
          <div key={result}>
            <dt>
              <span className={'tile ' + result} aria-hidden="true">
                {letter}
              </span>
            </dt>
            <dd>{meaning}</dd>
          </div>
        ))}
      </dl>
    </>
  )
}

// The sign-in page's version: a headline, then the rules.
function HowToPlay() {
  return (
    <section className="pitch" aria-label="How to play">
      <h2 className="pitch-heading">Guess the word, alone or together.</h2>
      <Rules />
    </section>
  )
}

export default HowToPlay
