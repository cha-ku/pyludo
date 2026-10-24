// The browser side of a room. The page (room.html) already contains every element; this script
// fills them in from the server's snapshots, shows or hides them, and sends what the player does.

// ---------------------------------------------------------------------------
// Find things on the page (once, at the top)
// ---------------------------------------------------------------------------
const code = document.querySelector("[data-code]").dataset.code;
const joinForm = document.getElementById("join");
const membersList = document.getElementById("members");
const statusLine = document.getElementById("status");
const errorLine = document.getElementById("error");
const startButton = document.getElementById("start");
const rollButton = document.getElementById("roll");
const tokensGroup = document.getElementById("tokens");
const timerText = document.getElementById("timer");
let turnEndsAt = null;

// SVG elements must be created in the SVG namespace, or they never draw.
const SVG = "http://www.w3.org/2000/svg";

// Both live in localStorage, so they outlive the tab: closing the room and opening it again later
// still takes back the seat. Tabs of one browser share them, so a second player needs a second
// browser (or a private window).
const sessionKey = `pyludo:session:${code}`;
const nicknameKey = "pyludo:nickname";

const FIRST_RETRY_DELAY = 1000; // milliseconds
const MAX_RETRY_DELAY = 10000;

// Nudges for tokens sharing a square, in board units. The first token sits in the middle.
const STACK_OFFSETS = [[0, 0], [-0.2, -0.2], [0.2, 0.2], [-0.2, 0.2], [0.2, -0.2]];

// ---------------------------------------------------------------------------
// State that must survive from one message to the next
// ---------------------------------------------------------------------------
let socket = null;
let mySeat = null; // from welcome. Seat 0 is falsy, so always compare with === null
let nickname = null; // kept so a reconnect can say hello again
let retryDelay = FIRST_RETRY_DELAY;

// ---------------------------------------------------------------------------
// Remembering. Storage can throw (some private modes), so the game must work without it.
// ---------------------------------------------------------------------------
function load(storage, key) {
    try {
        return storage.getItem(key);
    } catch {
        return null;
    }
}

function save(storage, key, value) {
    try {
        storage.setItem(key, value);
    } catch {
        // Not remembered; nothing else to do.
    }
}

function forget(storage, key) {
    try {
        storage.removeItem(key);
    } catch {
        // Nothing was remembered.
    }
}

// ---------------------------------------------------------------------------
// Connecting
// ---------------------------------------------------------------------------
function connect() {
    socket = new WebSocket(`ws://${location.host}/ws/${code}`);
    // Per connection, not per tab: after a server restart this tab still has a seat, but the room
    // is gone, and that refusal must stop the retries.
    let welcomed = false;
    let refused = false;

    socket.addEventListener("open", () => {
        const hello = { type: "hello", nickname: nickname };
        const session = load(localStorage, sessionKey);
        if (session !== null) {
            hello.session = session;
        }
        socket.send(JSON.stringify(hello));
    });

    socket.addEventListener("message", (event) => {
        const message = JSON.parse(event.data);
        switch (message.type) {
            case "welcome":
                welcomed = true;
                mySeat = message.seat;
                retryDelay = FIRST_RETRY_DELAY;
                save(localStorage, sessionKey, message.session);
                joinForm.hidden = true;
                errorLine.textContent = "";
                break;
            case "snapshot":
                render(message);
                break;
            case "error":
                errorLine.textContent = message.message;
                if (!welcomed) {
                    refused = true;
                }
                break;
        }
    });

    socket.addEventListener("close", () => {
        turnEndsAt = null;
        startButton.hidden = true;
        rollButton.hidden = true;
        tokensGroup.querySelectorAll(".movable").forEach((token) => token.classList.remove("movable"));
        if (refused) {
            // Asking again gets the same answer: let the player decide what to do.
            forget(localStorage, sessionKey);
            mySeat = null;
            joinForm.hidden = false;
            statusLine.textContent = "";
            return;
        }
        statusLine.textContent = "Connection lost, reconnecting…";
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY);
    });
}

function send(message) {
    if (socket !== null && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message));
    }
}

// ---------------------------------------------------------------------------
// Drawing. Everything is redrawn from each snapshot, so nothing can drift out of step.
// ---------------------------------------------------------------------------
function render(snapshot) {
    renderMembers(snapshot);
    renderStart(snapshot);
    renderRoll(snapshot.game);
    statusLine.textContent = describe(snapshot);
    drawTokens(snapshot.game);
    const secondsLeft = snapshot.game ?. seconds_left ?? null;
    turnEndsAt = secondsLeft === null ? null : performance.now() + secondsLeft * 1000;
}

function renderMembers(snapshot) {
    const items = snapshot.members.map((member) => {
        const item = document.createElement("li");
        let text = member.nickname; // textContent, never innerHTML: nicknames come from players
        if (member.seat === mySeat) {
            text += " (you)";
        }
        if (member.seat === snapshot.host_seat) {
            text += " (host)";
        }
        if (!member.connected) {
            text += " (away)";
        }
        item.textContent = text;
        // No colour in the lobby, nor for someone who joined after the last game ended: they have no
        // player in it yet.
        const player = snapshot.game?.players[member.seat];
        if (player !== undefined) {
            item.dataset.colour = player.colour;
        }
        return item;
    });
    membersList.replaceChildren(...items);
}

function renderStart(snapshot) {
    const game = snapshot.game;
    const isHost = mySeat === snapshot.host_seat;
    const isOver = game !== null && game.phase === "GAME_OVER";
    startButton.hidden = !(isHost && (game === null || isOver));
    startButton.disabled = snapshot.members.length < 2;
    startButton.textContent = isOver ? "Play again" : "Start game";
}

function renderRoll(game) {
    rollButton.hidden = !(game !== null && game.current_seat === mySeat && game.phase === "AWAITING_ROLL");
    rollButton.disabled = false;
}

function nameOf(snapshot, seat) {
    if (seat === mySeat) {
        return "You";
    }
    const member = snapshot.members.find((m) => m.seat === seat);
    return member === undefined ? "?" : member.nickname;
}

function describe(snapshot) {
    const game = snapshot.game;
    if (game === null) {
        return "Waiting for the host to start the game.";
    }
    const parts = [];
    if (game.last_roll !== null) {
        parts.push(`${nameOf(snapshot, game.last_roll.seat)} rolled ${game.last_roll.die}.`);
    }
    if (game.phase === "GAME_OVER") {
        const winnerSeat = game.players.findIndex((player) => player.colour === game.winner);
        parts.push(`${nameOf(snapshot, winnerSeat)} won!`);
    } else {
        const next = game.phase === "AWAITING_MOVE" ? "move" : "roll";
        parts.push(`${nameOf(snapshot, game.current_seat)} to ${next}.`);
    }
    return parts.join(" ");
}

function drawTokens(game) {
    if (game === null) {
        tokensGroup.replaceChildren();
        return;
    }
    const canMove = game.phase === "AWAITING_MOVE" && game.current_seat === mySeat;
    const drawnOn = new Map(); // "row,col" -> how many tokens are already drawn there
    const circles = [];
    game.players.forEach((player, seat) => {
        player.tokens.forEach((token, index) => {
            const square = `${token.cell.row},${token.cell.col}`;
            const already = drawnOn.get(square) ?? 0;
            drawnOn.set(square, already + 1);
            const [dx, dy] = STACK_OFFSETS[already % STACK_OFFSETS.length];

            const circle = document.createElementNS(SVG, "circle");
            circle.setAttribute("cx", token.cell.col + 0.5 + dx);
            circle.setAttribute("cy", token.cell.row + 0.5 + dy);
            circle.setAttribute("r", already === 0 ? 0.35 : 0.3);
            circle.classList.add("token");
            circle.dataset.colour = player.colour;
            if (canMove && seat === mySeat && game.movable_tokens.includes(index)) {
                circle.classList.add("movable");
                circle.dataset.token = index;
            }
            circles.push(circle);
        });
    });
    tokensGroup.replaceChildren(...circles);
}

// ---------------------------------------------------------------------------
// What the player does
// ---------------------------------------------------------------------------
joinForm.addEventListener("submit", (event) => {
    event.preventDefault(); // otherwise the browser reloads the page with ?nickname=...
    nickname = new FormData(joinForm).get("nickname").trim();
    save(localStorage, nicknameKey, nickname);
    errorLine.textContent = "";
    connect();
});

startButton.addEventListener("click", () => send({ type: "start" }));

rollButton.addEventListener("click", () => {
    rollButton.disabled = true; // one click, one roll; the next snapshot decides what's shown
    send({ type: "roll" });
});

// One listener for every token, because the circles are replaced on every snapshot.
tokensGroup.addEventListener("click", (event) => {
    const token = event.target.closest(".movable");
    if (token !== null) {
        send({ type: "move", token: Number(token.dataset.token) }); // data-* values are strings
    }
});

// ---------------------------------------------------------------------------
// On page load
// ---------------------------------------------------------------------------
const rememberedNickname = load(localStorage, nicknameKey);
if (rememberedNickname !== null) {
    joinForm.elements.nickname.value = rememberedNickname;
    if (load(localStorage, sessionKey) !== null) {
        // A refresh: this tab already has a seat in this room, so take it back without the form.
        nickname = rememberedNickname;
        joinForm.hidden = true;
        connect();
    }
}

function showTimeLeft() {
    if (turnEndsAt === null) {
        timerText.textContent = "";
        return;
    }
    // performance.now() - browser clock
    const seconds = Math.max(0, Math.ceil((turnEndsAt - performance.now()) / 1000));
    timerText.textContent = `${seconds} s`;
}
setInterval(showTimeLeft, 250);
