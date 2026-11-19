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
export function Rules() {
  return (
    <>
      <p className="lead">
        Words run from 5 to 8 letters, and you get one more guess than the word has letters.
      </p>
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
