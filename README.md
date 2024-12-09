# Vyxal Bot 3

A custom-built chatbot for GitHub logging and other automation tools in the [Vyxal](https://chat.stackexchange.com/rooms/106764/vyxal) Stack Exchange chatroom.

## Local development instructions:
1. Download and install [PostgreSQL](https://www.postgresql.org/download/), and create a new account for the bot to use
2. Download and install [poetry](https://python-poetry.org), ideally with `pipx` (`pipx install poetry`)
3. Clone this repository
4. Run `poetry install`
5. Rename `.sample.env` to `.env` and fill in the blanks (**including** the Postgres database URL); the variables starting with `GITHUB__` can be left as-is if you don't plan on testing commands which interact with GitHub.
6. Run `poetry run prisma db push` to initialize the database and create the Prisma client
7. Start the bot with `poetry run python3 -m vyxalbot3`

Any changes to the schema must be pushed to the database with `poetry run prisma db push`.