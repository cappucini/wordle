# Test word lists

The API, security, concurrency and end-to-end tests load these files instead of the real
lists in `backend/app/words/data/`.

Each length has **exactly one answer**, so a test always knows the answer to a new game:

| Length | Answer     | Other accepted guesses                              |
|--------|------------|-----------------------------------------------------|
| 5      | `crane`    | slate, react, nacre, eerie, elect, moist, trace     |
| 6      | `planet`   | plates, garden                                      |
| 7      | `kitchen`  | thicken, chicken                                    |
| 8      | `absolute` | notebook, textbook                                  |

The application code is unchanged: it still picks a random answer, there is just only one
to pick. If you edit these files, update `backend/tests/support.py` to match.
