// The page heading, with letters alternating between the two theme colours.
function Title() {
  const letters = ['W', 'o', 'r', 'd', 'l', 'e']
  // Screen readers get the whole word once, from aria-label, instead of six separate
  // letters: each letter's span is hidden from them with aria-hidden.
  return (
    <h1 className="title" aria-label="Wordle">
      {letters.map((letter, index) => (
        <span key={index} className={index % 2 === 0 ? 'title-letter pink' : 'title-letter sage'} aria-hidden="true">
          {letter}
        </span>
      ))}
    </h1>
  )
}

export default Title
