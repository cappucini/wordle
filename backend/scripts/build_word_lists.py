"""Build the word-list files for 6, 7 and 8-letter games.

The 5-letter files are NOT built here. They are the original Wordle lists (its answers, and
its other accepted guesses), copied in as published with nothing added or removed. See
"Word Lists" in the README. This script leaves them alone, and none of the filtering below
(plurals, names) is applied to them.

For the longer lengths, where no official list exists:

valid_N.txt   - every N-letter word in the ENABLE dictionary (accepted as guesses).
                ENABLE (Enhanced North American Benchmark Lexicon) is the usual
                public-domain dictionary for word games: https://github.com/dolph/dictionary
answers_N.txt - N-letter words that are in ENABLE, are also in a list of common English
                words, and are not plural (eligible to be chosen as a game's answer).
                Restricting answers to common words keeps the game fair: any dictionary
                word can be guessed, but the answer is one a player is likely to know.

Usage: python build_word_lists.py <enable1.txt> <common-words.txt> <output-dir>
       [<proper-names.txt> <system-dictionary.txt>]

The two optional files are used to keep names and places out of the answers:
on macOS they are /usr/share/dict/propernames and /usr/share/dict/words.
"""
import re
import sys
from pathlib import Path

# 5-letter games use the original Wordle lists, which are not generated (see above)
MIN_LENGTH = 6
MAX_LENGTH = 8
# ^ and $ are the start and end of the text, so the whole word must be a to z letters
LETTERS_ONLY = re.compile(r"^[a-z]+$")

# Dictionary words that are far better known as places, peoples, names or brands.
# They stay valid as guesses but are never chosen as answers.
NOT_ANSWERS = {
    "berlin", "boston", "china", "cisco", "collins", "cyprus", "dutch", "easter",
    "florence", "geneva", "german", "guinea", "honda", "japan", "jenny", "jersey",
    "nelson", "panama", "parker", "siemens", "soviet", "swiss", "welsh", "yahoo",
}


def read_words(path: Path) -> list[str]:
    """Reads a file with one word per line. Returns the words, lowercased and in file
    order, leaving out any line that is not made only of the letters a to z."""
    words = []
    # errors="ignore" skips bytes that are not valid UTF-8 instead of stopping
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        word = line.strip().lower()
        if LETTERS_ONLY.match(word):
            words.append(word)
    return words


def looks_plural(word: str, dictionary: set[str]) -> bool:
    """True if the word is an -s form of another dictionary word (plural or verb form)."""
    if not word.endswith("s") or word.endswith("ss"):
        return False
    if word[:-1] in dictionary:                               # cranes -> crane
        return True
    if word.endswith("es") and word[:-2] in dictionary:       # boxes -> box
        return True
    if word.endswith("ies") and word[:-3] + "y" in dictionary:  # cities -> city
        return True
    if word.endswith("ves") and (word[:-3] + "f" in dictionary or word[:-3] + "fe" in dictionary):
        return True                                           # knives -> knife
    if word.endswith("ices") and (word[:-4] + "ex" in dictionary or word[:-4] + "ix" in dictionary):
        return True                                           # indices -> index
    if word.endswith("es") and len(word) > 4 and word[-3] == word[-4] and word[:-3] in dictionary:
        return True                                           # quizzes -> quiz
    return False


def read_proper_nouns(names_path: Path, system_dictionary_path: Path) -> set[str]:
    """Names, plus words the system dictionary only lists with a capital letter."""
    # the `if line.strip()` at the end of each of these leaves out blank lines
    proper = {line.strip().lower() for line in names_path.read_text().splitlines() if line.strip()}
    entries = [line.strip() for line in system_dictionary_path.read_text().splitlines() if line.strip()]
    lowercase_entries = {entry for entry in entries if entry.islower()}
    for entry in entries:
        if entry[0].isupper() and entry.lower() not in lowercase_entries:
            proper.add(entry.lower())
    return proper


def main() -> None:
    """Reads the files named on the command line, and writes valid_N.txt and
    answers_N.txt into the output folder for each word length."""
    # the first three arguments, each made into a Path (sys.argv[0] is the script itself)
    dictionary_path, common_path, output_dir = (Path(arg) for arg in sys.argv[1:4])
    output_dir.mkdir(parents=True, exist_ok=True)
    proper_nouns = set()
    if len(sys.argv) >= 6:  # both optional files were given
        proper_nouns = read_proper_nouns(Path(sys.argv[4]), Path(sys.argv[5]))

    dictionary = set(read_words(dictionary_path))
    common_in_frequency_order = read_words(common_path)

    for length in range(MIN_LENGTH, MAX_LENGTH + 1):
        valid = sorted(word for word in dictionary if len(word) == length)

        answers = []
        for word in common_in_frequency_order:
            if len(word) != length:
                continue
            if word not in dictionary:          # drops names, brands, abbreviations
                continue
            if looks_plural(word, dictionary):
                continue
            if word in proper_nouns or word in NOT_ANSWERS:   # drops jesse, paris, florence...
                continue
            answers.append(word)
        answers = sorted(set(answers))  # set() drops repeats; then alphabetical order

        (output_dir / f"valid_{length}.txt").write_text("\n".join(valid) + "\n")
        (output_dir / f"answers_{length}.txt").write_text("\n".join(answers) + "\n")
        # :>6 and :>5 right-align the numbers, so the printed lines form neat columns
        print(f"{length} letters: {len(valid):>6} valid, {len(answers):>5} answers")


if __name__ == "__main__":
    main()
