# pyludo

Ludo in the browser, for two to four players. Create a room, share its link, and play together on
your own network or over the internet. Built with FastAPI, WebSockets and plain JavaScript with SVG.
The engine maintains the game state which is a state machine. The server broadcasts this state to all players in a room after every game action, and the browser
then renders it. One could potentially write an alternative renderer for this and thus play "cross-platform" games.

## Development

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.14 and everything else.

```bash
uv sync                                         # create .venv with all dependencies
uv run uvicorn pyludo.server:app --reload       # serve on http://127.0.0.1:8000, reload on changes
uv run pytest                                   # run the tests
uv run ruff check && uv run ruff format --check # lint and check formatting
```

## Running with Docker

To run it on your own machine:

```bash
docker build -t pyludo .
docker run --rm -p 8000:8000 pyludo
```

Then open <http://127.0.0.1:8000>. Ctrl+C stops it.

## Settings

pyludo reads its settings from environment variables. Pass them with `docker run -e NAME=value`,
or under `environment:` in `compose.yaml`.

| Variable | Default | Meaning |
|---|---|---|
| `PYLUDO_TURN_SECONDS` | `30` | Time for each roll or move. When it runs out, the server plays the turn. |
| `PYLUDO_MAX_ROOMS` | `100` | Most rooms at once. When full, Create room shows a "try again later" page. |
| `PYLUDO_EMPTY_ROOM_SECONDS` | `600` | A room with nobody connected for this long is deleted. |
| `PYLUDO_SWEEP_SECONDS` | `60` | How often to look for empty rooms. Keep it well below the setting above. |

## Playing on your network

Other devices on the same network can join while the container runs:

1. On a phone or another computer, open `http://192.168.x.y:8000`.
2. Create a room and send its link to the other players.

## Hosting with HTTPS (Caddy)

To play over the internet, `compose.yaml` runs pyludo behind [Caddy](https://caddyserver.com/),
which gets and renews an HTTPS certificate from Let's Encrypt automatically.

Put your domain name in the `Caddyfile`:

```
ludo.example.com {
    reverse_proxy pyludo:8000
}
```

Then, on the server:

```bash
docker compose up --build -d   # start pyludo and Caddy in the background
docker compose ps              # pyludo should show (healthy) after a few seconds
docker compose logs -f         # follow the logs
```

