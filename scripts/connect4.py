#!/usr/bin/env python3
"""Community Connect Four, played through GitHub issues.

A visitor opens an issue titled `connect4|drop|<1-7>` (or `connect4|new`).
The workflow runs this script, which updates game/state.json, re-renders the
board between the C4 markers in README.md and writes the reply for the issue
to game/reply.md.

Usage:
    ISSUE_TITLE='connect4|drop|4' ISSUE_USER=octocat python3 scripts/connect4.py
    python3 scripts/connect4.py --test
"""

import json
import os
import re
import sys
from urllib.parse import quote

REPO = os.environ.get("GITHUB_REPOSITORY", "jitheender-ops/jitheender-ops")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "game", "state.json")
REPLY = os.path.join(ROOT, "game", "reply.md")
README = os.path.join(ROOT, "README.md")
ROWS, COLS = 6, 7
DISC = {"": "⚪", "R": "🔴", "Y": "🟡"}
NAME = {"R": "Red", "Y": "Yellow"}
START, END = "<!-- C4:START -->", "<!-- C4:END -->"


def new_game(stats=None):
    return {"board": [[""] * COLS for _ in range(ROWS)], "turn": "R",
            "moves": [], "winner": None, "stats": stats or {"games": 0, "players": {}}}


def winner(board):
    for r in range(ROWS):
        for c in range(COLS):
            p = board[r][c]
            if not p:
                continue
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = [(r + dr * i, c + dc * i) for i in range(4)]
                if all(0 <= y < ROWS and 0 <= x < COLS and board[y][x] == p for y, x in cells):
                    return p
    if all(board[0]):
        return "draw"
    return None


def drop(state, col, user):
    """Apply a move. Returns an error string, or None on success."""
    if state["winner"]:
        return "This game is over. Start a new one from the README."
    board = state["board"]
    if board[0][col]:
        return f"Column {col + 1} is full. Pick another one."
    row = max(r for r in range(ROWS) if not board[r][col])
    board[row][col] = state["turn"]
    state["moves"].append({"user": user, "col": col + 1, "disc": state["turn"]})
    players = state["stats"]["players"]
    players[user] = players.get(user, 0) + 1
    state["winner"] = winner(board)
    if state["winner"]:
        state["stats"]["games"] += 1
    else:
        state["turn"] = "Y" if state["turn"] == "R" else "R"
    return None


def issue_link(title, label):
    body = quote("Just press **Submit new issue**. No need to change anything, the bot moves for you.")
    return f"[{label}](https://github.com/{REPO}/issues/new?title={quote(title)}&body={body})"


def render(state):
    out = []
    if state["winner"] == "draw":
        out.append("**It's a draw!** " + issue_link("connect4|new", "Start a new game"))
    elif state["winner"]:
        w = state["winner"]
        out.append(f"**{DISC[w]} {NAME[w]} wins!** Last move by @{state['moves'][-1]['user']}. "
                   + issue_link("connect4|new", "Start a new game"))
    else:
        t = state["turn"]
        out.append(f"It's **{DISC[t]} {NAME[t]}**'s turn. Click a column to drop a disc:")
    out.append("")
    head = [issue_link(f"connect4|drop|{c + 1}", f"⬇️{c + 1}") if not state["winner"] and not state["board"][0][c]
            else str(c + 1) for c in range(COLS)]
    out.append("<div align=\"center\">\n")
    out.append("| " + " | ".join(head) + " |")
    out.append("|" + ":-:|" * COLS)
    for row in state["board"]:
        out.append("| " + " | ".join(DISC[x] for x in row) + " |")
    out.append("\n</div>\n")
    recent = state["moves"][-5:][::-1]
    if recent:
        out.append("**Last moves:** " + " · ".join(
            f"{DISC[m['disc']]} @{m['user']} → col {m['col']}" for m in recent))
        out.append("")
    top = sorted(state["stats"]["players"].items(), key=lambda kv: -kv[1])[:5]
    if top:
        out.append("**Top players:** " + " · ".join(f"@{u} ({n})" for u, n in top)
                   + f" · games finished: {state['stats']['games']}")
    return "\n".join(out)


def write_readme(state):
    with open(README, encoding="utf-8") as f:
        text = f.read()
    block = f"{START}\n{render(state)}\n{END}"
    text = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    with open(README, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    title = os.environ.get("ISSUE_TITLE", "").strip().lower()
    user = os.environ.get("ISSUE_USER", "someone")
    try:
        with open(STATE, encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        state = new_game()

    m = re.fullmatch(r"connect4\|drop\|([1-7])", title)
    if title == "connect4|new":
        if state["winner"] or not state["moves"]:
            state = new_game(state["stats"])
            reply = f"New game started by @{user}! [Back to the board](https://github.com/{REPO}#-play-connect-four)"
        else:
            reply = "A game is still in progress. Jump in and finish it first!"
    elif m:
        err = drop(state, int(m.group(1)) - 1, user)
        if err:
            reply = err
        else:
            last = state["moves"][-1]
            reply = f"{DISC[last['disc']]} @{user} dropped a disc in column {last['col']}."
            if state["winner"] == "draw":
                reply += " The board is full: **draw!**"
            elif state["winner"]:
                reply += f" **{NAME[state['winner']]} wins!** 🎉"
            reply += f"\n\n[Back to the board](https://github.com/{REPO}#-play-connect-four)"
    else:
        reply = "I didn't understand that move. Use the links in the README to play."

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    with open(REPLY, "w", encoding="utf-8") as f:
        f.write(reply + "\n")
    write_readme(state)


def test():
    s = new_game()
    for col in (0, 1, 0, 1, 0, 1):
        assert drop(s, col, "t") is None and not s["winner"]
    assert drop(s, 0, "t") is None and s["winner"] == "R"          # vertical
    assert drop(s, 2, "t").startswith("This game is over")
    s = new_game()
    for col in (0, 0, 1, 1, 2, 2):
        drop(s, col, "t")
    drop(s, 3, "t")
    assert s["winner"] == "R"                                        # horizontal
    s = new_game()
    for col in (0, 1, 1, 2, 2, 3, 2, 3, 3, 6):
        drop(s, col, "t")
    drop(s, 3, "t")
    assert s["winner"] == "R"                                        # diagonal
    s = new_game()
    for _ in range(ROWS):
        drop(s, 4, "t")
    assert drop(s, 4, "t").startswith("Column 5 is full")
    assert "⬇️5" not in render(s) and "⬇️4" in render(s)
    print("connect4 ok")


if __name__ == "__main__":
    test() if "--test" in sys.argv else main()
