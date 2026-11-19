# Wordle Full Stack Assessment

## Background

Wordle is a simple game in which you have to guess a five-letter word. You get six guesses, learning a little more information with each guess, and eventually narrow your guesses down to find the answer.

You can play an online version of Wordle [here](https://www.nytimes.com/games/wordle/index.html).

## Rules

1. Letters that are in the answer and in the right place turn green.
2. Letters that are in the answer but in the wrong place turn yellow.
3. Letters that are not in the answer turn gray.
4. Answers are never plural.
5. Letters can appear more than once. So if your guess includes two of one letter, they may both turn yellow, both turn green, or one could be yellow and the other green.
6. Each guess must be a valid word in Wordle's dictionary. You can't guess ABCDE, for instance.
7. You do not have to include correct letters in subsequent guesses.
8. You have six guesses to solve the Wordle.

## Goal

Your goal is to design and build a full stack Wordle application with both a REST API backend and a React frontend.

In our version of Wordle, there are 2 key differences from the original:

1. **Multiple Games**: The user can create and play as many games as they want.
2. **Configurable Word Length**: The user can configure the number of letters in the target word to be anywhere between 5 to 8 letters, but they will always only have N+1 turns to guess the word. For instance, traditional Wordle involves guessing a five-letter word over six turns, but in our version, the user can pick 7 as the number of letters and get 8 turns to guess the word.

### Backend Requirements

- Build a REST API that supports:
  - Creating a new game (with configurable word length 5-8)
  - Submitting guesses and receiving feedback (green/yellow/gray for each letter)
  - Retrieving game state
  - Validating that guesses are real words
- Use appropriate data storage for game state

### Frontend Requirements

- Build a React UI that allows users to:
  - Start a new game with a selected word length (5-8 letters)
  - Enter guesses via an on-screen keyboard or physical keyboard
  - See feedback for each guess (green/yellow/gray letters)
  - View their guess history for the current game
  - See when they've won or lost

**Use of AI is allowed and encouraged for this assessment.**

---

## Getting Started

This repository includes boilerplate code to help you get started quickly.

### Project Structure

```
wordle-starter/
├── frontend/           # React application (Vite)
├── backend/            # FastAPI application
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── e2e/                # End-to-end browser tests
├── docker-compose.yml
├── docker-compose.test.yml   # The test stack (see Testing)
├── Makefile            # Test commands
└── README.md
```

### Frontend

The frontend is a React application built with Vite. It is pre-configured with CORS support to communicate with the backend.

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173`.

**How it looks**

The interface is styled as a screen-printed label: cream paper, a fat slab typeface, thick ink rules and one red for the main button. Played letters are green (right place), yellow (wrong place) and grey (not in the word).

- Every colour, font and size is a named value in `frontend/src/index.css`; `frontend/src/App.css` only uses those names, so the look can be changed in one place.
- The two fonts (Ultra and Chivo) are bundled with the app, so the page loads nothing from other sites.
- "How to play" in the top bar (or the `?` key) opens the rules in a small panel without leaving the game. Escape or a click outside closes it, and typing is paused while it is open.
- The game screen is three panels across the top (new game, players, your games) and one boxed panel below with the board and the keyboard side by side. On a phone the board comes first and the panels stack under it.

**Key files to modify:**
- `frontend/src/App.jsx` - Main application component, start building your UI here
- `frontend/src/App.css` - Application styles
- Add new components in `frontend/src/components/` as needed

### Backend

The backend is a FastAPI application with CORS already configured for the frontend. Run it using Docker Compose:

```bash
docker compose up --build
```

This will build and start the backend container with hot-reloading enabled. The API will be available at `http://localhost:8000`.

To run in detached mode (background):

```bash
docker compose up -d --build
```

To stop the container:

```bash
docker compose down
```

API documentation is automatically available at `http://localhost:8000/docs`.

**Key files to modify:**
- `backend/main.py` - Add your API endpoints here
- `backend/requirements.txt` - Add any additional Python dependencies

### Live updates in shared games

When several players share a game, each player's page shows the others' guesses as they
happen. While a game in progress is on screen, the page keeps a WebSocket open to the backend:

```
ws://localhost:8000/api/v1/games/{game_id}/ws
```

- When a guess is saved or a new player joins, the backend sends every page watching that
  game one small message, `{"type": "game_updated"}`. The page then fetches the game through
  the normal `GET /api/v1/games/{game_id}` route. No game data, and so no answer, ever
  travels over the WebSocket.
- Only a signed-in player of the game may connect, and only from the frontend's own address
  (the addresses in `CORS_ORIGINS`). A refused connection is closed with code `4401` (not
  signed in), `4403` (not a player) or `4404` (no such game).
- If the connection drops, the page reconnects after 1 second, then 2, 4, 8 and at most
  every 10 seconds, and checks for anything it missed as soon as it is back. While there is
  no connection (including on networks that block WebSockets) it asks the backend every
  5 seconds instead (while the tab is visible), so a shared board still updates.
- A connection ends with its sign-in: it is closed with `4401` when the player logs out or
  the session expires.
- One player may hold 10 connections at once (about ten tabs). An eleventh is closed with
  `4429`, and that tab uses the 5-second check.
- The list of connected pages is kept in the backend's memory, which is right for the single
  backend process this project runs. Running several backend processes would need a shared
  channel (for example Postgres `LISTEN`/`NOTIFY`) so a guess handled by one reaches pages
  connected to another.

### Staying signed in

A sign-in lasts 7 days and is extended while it is being used: once a day, a request from a
signed-in player pushes the expiry back out to 7 days from then. A player who keeps playing
stays signed in; one who stops is signed out 7 days after their last visit. Logging in again
in a browser that is already signed in ends the session it replaces.

Each game address the page puts in the browser's history records which player opened it. A
link nobody has opened yet joins you to the game. An address left behind by a different
player on the same browser (reached with Back, or still in the address bar when their
sign-in ended) does not: the game is only shown if you are already one of its players.

### Limits on log-in and sign-up

To slow down password guessing, the backend counts attempts over the last five minutes and
answers `429 TOO_MANY_ATTEMPTS` (with a `Retry-After` header) once a limit is reached.

**Always on**

| Limit | Allowed in 5 minutes |
|---|---|
| Wrong passwords for one username | 10 |

A successful log-in clears that username's count. Someone who knows a username can keep it
at its limit and so stop that player logging in for a while; they cannot end a session the
player already has.

**Off unless `RATE_LIMIT_BY_ADDRESS=true` is set on the backend**

| Limit | Allowed in 5 minutes |
|---|---|
| Wrong passwords from one network address, across all usernames | 30 |
| Accounts created from one network address | 20 |
| Sign-ups refused because the username was taken, from one network address | 30 |

These three count by the address a request comes from, so they only work where the backend
can tell visitors apart. Run with Docker as described above, it cannot: every browser
reaches the backend from Docker's own address, and the same is true behind a reverse proxy.
Counted that way, one visitor's wrong passwords would lock out everyone. Turn the setting on
only in a deployment where each visitor's own address reaches the backend.

Each attempt is counted before it is carried out, so the limits also hold when many requests
arrive at the same instant. The counts are kept in the backend's memory and reset when it
restarts.

The numbers are in `backend/app/domain/rules.py`. Each can be changed without editing code
by setting an environment variable on the backend: `MAX_FAILED_LOGINS_PER_USERNAME`,
`MAX_FAILED_LOGINS_PER_ADDRESS`, `MAX_SIGNUPS_PER_ADDRESS` or
`MAX_REFUSED_SIGNUPS_PER_ADDRESS`.

### Changing the database schema

The backend creates any missing tables when it starts, but it does not alter tables that
already exist; there are no migrations. After a change to the models in `backend/app/db.py`
(a new column or index), recreate the development database:

```bash
docker compose down -v      # deletes the dev database, including its users and games
docker compose up --build
```

The word lists are loaded again automatically. To keep existing data instead, apply the
change by hand. For the index added on `game_players.user_id`:

```bash
docker compose exec db psql -U wordle -d wordle -c "CREATE INDEX IF NOT EXISTS ix_game_players_user_id ON game_players (user_id);"
```

### Development Workflow

1. Start the backend with `docker compose up --build`
2. Start the frontend with `cd frontend && npm install && npm run dev`
3. Build your API endpoints in `backend/main.py`
4. Build your UI in the `frontend/src/` directory
5. The frontend is configured to make requests to `http://localhost:8000`

### Word Lists

The game uses two word lists for each word length (5 to 8 letters), stored in `backend/app/words/data/`:

- `valid_N.txt` - every N-letter word accepted as a guess (this includes the answers)
- `answers_N.txt` - the smaller set of familiar words that can be chosen as a game's answer

A guess is accepted only if it is in `valid_N.txt`; anything else is refused with "not in the word list". A game's answer is always picked from `answers_N.txt`.

These files are committed to the repository and loaded into the database automatically when the backend starts. **You do not need to rebuild them to run the app.**

| Length | Answers | Accepted guesses | Where they come from |
|---|---|---|---|
| 5 | 2,315 | 12,972 | The original Wordle lists, copied in unchanged |
| 6 | 981 | 15,232 | Built by `backend/scripts/build_word_lists.py` |
| 7 | 945 | 23,109 | Built by `backend/scripts/build_word_lists.py` |
| 8 | 766 | 28,420 | Built by `backend/scripts/build_word_lists.py` |

**5 letters: the original Wordle lists**

The 5-letter files are the two lists from the original Wordle game: its 2,315 answers, and the 10,657 further words it accepted as guesses. They were taken from these published copies:

- Answers: <https://gist.github.com/cfreshman/a03ef2cba789d8cf00c08f767e0fad7b>
- Other accepted guesses: <https://gist.github.com/cfreshman/cdcdf777450c5b5301e439061d29694c>

`answers_5.txt` is the first list; `valid_5.txt` is both lists together. Both are sorted alphabetically and otherwise unchanged.

Things to know about these lists:

- **Nothing has been added or removed.** The decision was to use the official lists as they are rather than a cleaned-up copy, and a unit test fails if they are edited.
- **Plurals:** no answer is a plural made by adding "s" or "es"; those words (`cakes`, `boxes`) are accepted as guesses only. Seven irregular plurals are answers, as they were in the original game: `geese`, `teeth`, `women`, `fungi`, `cacti`, `radii` and `algae`. Read strictly, that is the one place the game departs from rule 4 above ("Answers are never plural").
- They are the lists as the original game shipped them. The New York Times, which now owns Wordle, has since removed some words (for example `slave`, `lynch` and `wench`) and no longer picks answers from a fixed list. Those words are still answers here.
- Wordle and its word lists belong to The New York Times. They are used here for a coursework assessment; check the position before using them in anything public or commercial.
- There is no official list for 6, 7 or 8 letters, which is why those lengths are built differently.

**6 to 8 letters: built from open sources**

- Valid guesses come from the [ENABLE word list](https://github.com/dolph/dictionary) (public domain).
- Answers are the words that also appear in a [list of the 10,000 most common English words](https://github.com/first20hours/google-10000-english), which is derived from the Google Web Trillion Word Corpus and permitted for educational use. Plurals and proper nouns are filtered out, so answers are familiar words and never plural.

**Rebuilding the 6 to 8 letter lists (optional)**

Run these commands from the repository root. They need Python 3.9 or later and an internet connection. The script writes the 6, 7 and 8-letter files only; it does not touch the 5-letter ones.

1. Download the two source lists into `backend/scripts/sources/` (this folder is not committed):

```bash
mkdir -p backend/scripts/sources

curl -sSL -o backend/scripts/sources/enable_dictionary_words.txt https://raw.githubusercontent.com/dolph/dictionary/master/enable1.txt

curl -sSL -o backend/scripts/sources/common_words.txt https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-usa-no-swears.txt
```

2. Build the six files:

```bash
python3 backend/scripts/build_word_lists.py \
    backend/scripts/sources/enable_dictionary_words.txt \
    backend/scripts/sources/common_words.txt \
    backend/app/words/data \
    /usr/share/dict/propernames \
    /usr/share/dict/words
```

The script prints the number of valid words and answers for each length. The last two arguments are macOS system files used to keep names and places out of the answers. They are optional: without them the script still runs and applies only its built-in exclusion list.

**Reloading the words into the database**

The words are only loaded when the `words` table is empty. After changing any of the files, empty the table and restart the backend:

```bash
docker compose exec db psql -U wordle -d wordle -c "TRUNCATE words;"
docker compose restart backend
```

This does not affect existing users or games.

**Known limits (6 to 8 letters)**

- Plural detection is a spelling heuristic: a word ending in "s" is excluded from the answers when undoing a common plural ending gives another dictionary word. It errs towards excluding too much (for example, `news` is dropped).
- Verb forms such as `showed` are allowed as answers.
- The dictionary dates from around 2000, so newer words such as `online` and `podcast` are not accepted as guesses.
- The common-words list was built from web pages, so some answers are web jargon (`warranty`, `shipping`).

## Testing

The tests are split into layers, so a failure points at the part that broke. Run the layer
for the code you are changing while you work, and everything before you merge.

**You need:** Docker running (for every layer except the frontend one), and Node.js with npm
(for the frontend one). The tests use their own containers and database and publish no
ports, so the development stack can stay up while they run.

### Commands

Run these from the repository root.

| Command | What it runs | Tests | Takes about |
|---|---|---|---|
| `make test-unit` | Backend unit tests: scoring, rules, request limits, password hashing, cursors, live-update notices. No database, no network. | 261 | 2 s |
| `make test-frontend` | Frontend component tests: the components, the game hook and the API client, with a fake backend. Same as `cd frontend && npm test`. | 287 | 4 s |
| `make test-api` | Backend API tests: real HTTP requests (and the live-update WebSocket) through FastAPI into a throwaway Postgres. | 175 | 9 s |
| `make test-security` | Security tests: sign-in and CSRF on every route, who may open the WebSocket, log-in and sign-up limits, hashed secrets, game access, the hidden answer, hostile input. | 221 | 19 s |
| `make test-concurrency` | Race tests: joins, guesses and sign-ups sent at the same instant. | 8 | 5 s |
| `make test-e2e` | End-to-end tests: headless Chromium driving the real frontend and backend through seven user journeys, plus 14 layout checks at desktop, small-laptop and phone sizes. | 21 | 45 s |
| `make test` | All of the above, fastest first, stopping at the first layer that fails. | 973 | 85 s |

The first run of a layer is slower, because Docker builds its image.

### Which layer failed, and what that means

| Failing layer | Look at |
|---|---|
| Unit | The logic of one function in `backend/app/domain/`, `security.py`, `pagination.py` or `schemas.py`. |
| Frontend | One component, `useGame.js` or `api.js`. |
| API, with unit passing | A route, a service function or a database query in `backend/app/`. |
| Security | A missing sign-in or CSRF check, a response that reveals too much, or a cookie setting. |
| Concurrency | A row lock in `backend/app/game_service.py`, or the unique-username handling in `user_service.py`. |
| End-to-end only | The frontend and backend disagreeing with each other, or a journey broken in the browser. |

### Running part of a layer

Extra options go in `ARGS`:

```bash
make test-api ARGS="-k pagination"       # only tests with "pagination" in their name
make test-api ARGS="--random-order"      # shuffle the order, to prove no test depends on another
make test-unit ARGS="-x -vv"             # stop at the first failure, with more detail
make test-frontend ARGS="Keyboard"       # only test files with "Keyboard" in their name
make test-e2e ARGS="-k refresh"          # one end-to-end journey
```

### How a test knows the answer

A game's answer is picked at random, so the tests load their own small word lists from
`backend/tests/words/`, which have exactly one answer for each length:

| Length | Answer |
|---|---|
| 5 | `crane` |
| 6 | `planet` |
| 7 | `kitchen` |
| 8 | `absolute` |

The application still picks at random; there is only one word to pick. No application code
changes for this, and there is no test-only switch or endpoint that could reveal an answer
in production. The API tests point the normal seeding code at that folder, and the
end-to-end stack mounts it in place of `backend/app/words/data/`. The real word lists are
checked by the unit tests instead.

### The test database

- It is a separate Postgres container that keeps its data in memory, with a database named
  `wordle_test`. It is created when a layer starts and removed when it finishes.
- The tests refuse to run against any database whose name does not end in `_test`.
- Before every API, security and concurrency test, the user and game tables are emptied,
  so tests do not depend on each other or on their order.
- End-to-end tests do not clean up. Each one creates users with unique names and its own games.

### Layout checks

`e2e/test_layout.py` holds the checks for things that only go wrong on a real screen, where the cause is in CSS and no other layer can see it: nothing sticking out sideways, the board staying on screen for a player with many games, the small boards in "Your games" being drawn in true squares, the rules panel opening where the player is looking, and keys staying wide enough to press. They measure the page at four window sizes (1280, 1100, 390 and 320 pixels wide).

Each one guards a bug that was found by looking at the page. If you change the stylesheet and one fails, its message says what moved and by how much.

### When an end-to-end test fails

For each browser the failed test had open, three files are saved in `e2e/artifacts/`
(which git ignores), named after the test:

- `.png`: a screenshot of the page at the moment of failure
- `.console.log`: the page address and everything the browser console logged
- `.html`: the page source

### Where the tests live

```
backend/tests/
├── unit/           # layer 1
├── api/            # layer 2
├── security/       # layer 3
├── concurrency/    # layer 4
├── words/          # the test word lists
├── conftest.py     # database set-up and clean-up, signed-in players
└── support.py      # the known answers and a helper for acting as a player
frontend/src/**/*.test.{js,jsx}   # beside the file each one tests
e2e/
├── pages/          # page objects: every selector lives here
├── conftest.py     # browsers, unique users, saving screenshots on failure
├── test_journeys.py   # one test per user journey
└── test_layout.py     # the page fits at desktop, laptop and phone sizes
```

Test-only dependencies are in `backend/requirements-test.txt`, `e2e/requirements.txt` and
the `devDependencies` of `frontend/package.json`. None are installed in the production image.

### Adding a test

| You changed | Add |
|---|---|
| A pure function or a rule | A unit test in `backend/tests/unit/` |
| A route, a query or an error code | An API test in `backend/tests/api/` |
| A component or the game hook | A `*.test.jsx` beside it |
| A new HTTP route | Nothing for sign-in and CSRF: `test_route_protection.py` reads the route list and covers it. If the route is meant to be public, add it to `PUBLIC_ROUTES` there. |
| A whole new thing a user can do | One end-to-end journey in `e2e/test_journeys.py`, using the page objects |
