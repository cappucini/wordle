"""Build the Wordle word-list files. This takes a large English dictionary
https://github.com/dolph/dictionary to form the list of valid words that someone can guess, all from ENABLE (Enhanced North American Benchmark Lexicon),
the standard for open-source word games. 

The answers are restrictd to be in ENABLE as well as a list of frequent English words pulled from Google, 
as we want to be fair to 

Usage: python build_word_lists.py <enable1.txt> <common-words.txt> <output-dir>
       [<proper-names.txt> <system-dictionary.txt>]

The two optional files are used to keep names and places out of the answers:
on macOS they are /usr/share/dict/propernames and /usr/share/dict/words.

valid_N.txt   - every N-letter word in the ENABLE dictionary (accepted as guesses)
answers_N.txt - N-letter words that are common, in the dictionary, and not plural
                (eligible to be chosen as a game's answer)
"""
import re
import sys
from pathlib import Path

MIN_LENGTH = 5
MAX_LENGTH = 8
LETTERS_ONLY = re.compile(r"^[a-z]+$")

# Dictionary words that are far better known as places, peoples, names or brands.
# They stay valid as guesses but are never chosen as answers.
NOT_ANSWERS = {
    "berlin", "boston", "china", "cisco", "collins", "cyprus", "dutch", "easter",
    "florence", "geneva", "german", "guinea", "honda", "japan", "jenny", "jersey",
    "nelson", "panama", "parker", "siemens", "soviet", "swiss", "welsh", "yahoo",
}


def read_words(path: Path) -> list[str]:
    words = []
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
    proper = {line.strip().lower() for line in names_path.read_text().splitlines() if line.strip()}
    entries = [line.strip() for line in system_dictionary_path.read_text().splitlines() if line.strip()]
    lowercase_entries = {entry for entry in entries if entry.islower()}
    for entry in entries:
        if entry[0].isupper() and entry.lower() not in lowercase_entries:
            proper.add(entry.lower())
    return proper


def main() -> None:
    dictionary_path, common_path, output_dir = (Path(arg) for arg in sys.argv[1:4])
    output_dir.mkdir(parents=True, exist_ok=True)
    proper_nouns = set()
    if len(sys.argv) >= 6:
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
        answers = sorted(set(answers))

        (output_dir / f"valid_{length}.txt").write_text("\n".join(valid) + "\n")
        (output_dir / f"answers_{length}.txt").write_text("\n".join(answers) + "\n")
        print(f"{length} letters: {len(valid):>6} valid, {len(answers):>5} answers")


if __name__ == "__main__":
    main()
