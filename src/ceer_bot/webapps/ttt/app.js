const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const params = new URLSearchParams(window.location.search);
const gameId = params.get("game_id") || window.location.pathname.split("/").filter(Boolean).pop();
const myId = tg?.initDataUnsafe?.user?.id ?? null;
const initData = tg?.initData ?? "";
const SYM_EMPTY = "·";

let state = null;
let poll = null;

const gr = document.getElementById("gr");
for (let i = 0; i < 9; i++) {
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
  const mySymbol = s.player_x?.id === myId ? "X" : s.player_o?.id === myId ? "O" : null;

  document.getElementById("nx").textContent = s.player_x?.name ?? "—";
  document.getElementById("no").textContent = s.player_o?.name ?? "Ожидание...";

  const cx = document.getElementById("cx");
  const co = document.getElementById("co");
  cx.className = "pcard" + (s.current_turn_id === s.player_x?.id && !s.finished ? " ax" : "");
  co.className = "pcard" + (s.current_turn_id === s.player_o?.id && !s.finished ? " ao" : "");

  const bet = parseFloat(s.bet || "0");
  document.getElementById("bl").textContent = bet > 0 ? `Ставка: ${bet.toFixed(2)} ${s.currency ?? ""}` : "";

  const st = document.getElementById("st");
  if (!s.player_o) {
    st.textContent = "Ожидаем второго игрока...";
  } else if (s.finished) {
    if (s.winner_id) {
      const wn = s.winner_id === s.player_x?.id ? s.player_x?.name : s.player_o?.name;
      st.textContent = `Победил ${wn}!`;
    } else {
      st.textContent = "Ничья";
    }
  } else if (myTurn) {
    st.textContent = "Ваш ход";
  } else {
    const tn = s.current_turn_id === s.player_x?.id ? s.player_x?.name : s.player_o?.name;
    st.textContent = `Ход: ${tn}`;
  }

  cells.forEach((c, i) => {
    const v = s.board[i];
    const prev = c.dataset.sym;
    const sym = v === "✕" ? "X" : v === "◯" ? "O" : "";
    c.dataset.sym = v === SYM_EMPTY ? "" : v;
    c.className = "cell" + (sym ? ` ${sym}` : "") + (v !== SYM_EMPTY ? " taken" : "") + (myTurn && mySymbol ? " my-turn" : "");
    if (sym && prev !== c.dataset.sym) {
      c.classList.add("pop");
      setTimeout(() => c.classList.remove("pop"), 300);
    }
  });

  if (s.finished && s.winner_cells) {
    s.winner_cells.forEach((i) => cells[i]?.classList.add("winner"));
  }

  if (s.finished && !document.querySelector(".overlay")) {
    showResult(s);
  }
}

function showResult(s) {
  let emoji;
  let title;
  let sub = "";
  if (!s.winner_id) {
    emoji = "🤝";
    title = "Ничья";
  } else if (s.winner_id === myId) {
    emoji = "🏆";
    title = "Вы победили";
    const bet = parseFloat(s.bet || "0");
    if (bet > 0) sub = `+${(bet * 2).toFixed(2)} ${s.currency ?? ""}`;
  } else {
    const wn = s.winner_id === s.player_x?.id ? s.player_x?.name : s.player_o?.name;
    emoji = "😔";
    title = `Победил ${wn}`;
  }

  const ov = document.createElement("div");
  ov.className = "overlay";
  ov.innerHTML = `<div class="rbox"><span class="remoji">${emoji}</span><div class="rtitle">${title}</div><div class="rsub">${sub}</div></div>`;
  ov.addEventListener("click", () => tg?.close?.());
  document.body.appendChild(ov);
  setTimeout(() => tg?.close?.(), 5000);
}

async function fetchState() {
  if (!gameId) return;
  try {
    const r = await fetch(`/api/ttt/${gameId}`);
    if (!r.ok) return;
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

fetchState();
