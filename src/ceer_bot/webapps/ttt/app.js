const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

function getGameId() {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("game_id");
  if (fromQuery) return fromQuery;
  return window.location.pathname.split("/").filter(Boolean).pop();
}

const gameId = getGameId();
const myId = tg?.initDataUnsafe?.user?.id ?? null;
const initData = tg?.initData ?? "";
const SYM_EMPTY = "·";

let state = null;
let poll = null;

const gr = document.getElementById("gr");
for (let i = 0; i < 9; i += 1) {
  const c = document.createElement("div");
  c.className = "cell";
  c.dataset.i = String(i);
  c.dataset.sym = "";
  c.addEventListener("click", () => onCell(i));
  gr.appendChild(c);
}
const cells = [...gr.children];

function render(s) {
  const myTurn = s.current_turn_id === myId && !s.finished && s.player_o;

  document.getElementById("nx").textContent = s.player_x?.name ?? "—";
  document.getElementById("no").textContent = s.player_o?.name ?? "Ожидание...";

  const cx = document.getElementById("cx");
  const co = document.getElementById("co");
  cx.className = "pcard" + (s.current_turn_id === s.player_x?.id && !s.finished ? " ax" : "");
  co.className = "pcard" + (s.current_turn_id === s.player_o?.id && !s.finished ? " ao" : "");

  const bet = parseFloat(s.bet || 0);
  document.getElementById("bl").textContent = bet > 0 ? `Ставка: ${bet.toFixed(2)} ${s.currency ?? ""}` : "";

  const st = document.getElementById("st");
  if (!s.player_o) {
    st.textContent = "Ожидаем второго игрока...";
  } else if (s.finished) {
    if (s.winner_id) {
      const winnerName = s.winner_id === s.player_x?.id ? s.player_x?.name : s.player_o?.name;
      st.textContent = `Победил ${winnerName}!`;
    } else {
      st.textContent = "Ничья!";
    }
  } else if (myTurn) {
    st.textContent = "Ваш ход";
  } else {
    const turnName = s.current_turn_id === s.player_x?.id ? s.player_x?.name : s.player_o?.name;
    st.textContent = `Ход: ${turnName}`;
  }

  cells.forEach((c, i) => {
    const v = s.board[i];
    const sym = v === "✕" ? "X" : v === "◯" ? "O" : "";
    c.dataset.sym = v === SYM_EMPTY ? "" : v;
    c.className = "cell" + (sym ? ` ${sym}` : "") + (v !== SYM_EMPTY ? " taken" : "") + (myTurn ? " my-turn" : "");
  });

  if (s.finished && s.winner_cells) {
    s.winner_cells.forEach((i) => cells[i]?.classList.add("winner"));
  }

  if (s.finished && !document.querySelector(".overlay")) {
    showResult(s);
  }
}

function showResult(s) {
  let emoji = "🤝";
  let title = "Ничья";
  let sub = "";

  if (s.winner_id) {
    if (s.winner_id === myId) {
      emoji = "🏆";
      title = "Вы победили";
      const bet = parseFloat(s.bet || 0);
      if (bet > 0) sub = `+${(bet * 2).toFixed(2)} ${s.currency ?? ""}`;
    } else {
      const winnerName = s.winner_id === s.player_x?.id ? s.player_x?.name : s.player_o?.name;
      emoji = "😔";
      title = `Победил ${winnerName}`;
    }
  }

  const ov = document.createElement("div");
  ov.className = "overlay";
  ov.innerHTML = `<div class="rbox"><span class="remoji">${emoji}</span><div class="rtitle">${title}</div><div class="rsub">${sub}</div></div>`;
  ov.addEventListener("click", () => tg?.close());
  document.body.appendChild(ov);
  setTimeout(() => tg?.close(), 5000);
}

async function fetchState() {
  try {
    const r = await fetch(`/api/ttt/${gameId}`);
    if (!r.ok) {
      poll = setTimeout(fetchState, 3000);
      return;
    }
    state = await r.json();
    render(state);
    if (!state.finished) poll = setTimeout(fetchState, 1500);
  } catch {
    poll = setTimeout(fetchState, 3000);
  }
}

async function onCell(idx) {
  if (!state || state.finished || !initData) return;
  if (state.current_turn_id !== myId || !state.player_o) return;
  if (cells[idx].classList.contains("taken")) return;

  clearTimeout(poll);
  try {
    const r = await fetch(`/api/ttt/${gameId}/move`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": initData,
      },
      body: JSON.stringify({ cell: idx }),
    });
    if (r.ok) {
      state = await r.json();
      render(state);
      if (!state.finished) poll = setTimeout(fetchState, 1500);
    } else {
      poll = setTimeout(fetchState, 1500);
    }
  } catch {
    poll = setTimeout(fetchState, 1500);
  }
}

if (!gameId) {
  document.getElementById("st").textContent = "Ошибка: не передан game_id";
} else {
  fetchState();
}
