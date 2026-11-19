// Shown beside the sign-in form: what the game is, and what the three colours mean.
// The sample tiles are decoration (hidden from screen readers); the sentence beside each
// one carries the meaning.
const RESULTS = [
  { letter: 'a', result: 'correct', meaning: 'Green: the right letter in the right place.' },
  { letter: 'r', result: 'present', meaning: 'Yellow: in the word, but somewhere else.' },
  { letter: 't', result: 'absent', meaning: 'Grey: not in the word.' },
]

function HowToPlay() {
  return (
    <section className="pitch" aria-label="How to play">
      <h2 className="pitch-heading">Guess the word, alone or together.</h2>
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
    </section>
  )
}

export default HowToPlay
