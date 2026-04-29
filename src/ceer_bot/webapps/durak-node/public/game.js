import { CanvasEngine, drawCard, drawDeck } from "./engine.js";

const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const canvas = document.getElementById("durak-canvas");
const engine = new CanvasEngine(canvas);

const statusEl = document.getElementById("status");
const btnPlay = document.getElementById("btn-play");
const btnPass = document.getElementById("btn-pass");
const btnTake = document.getElementById("btn-take");

const gameId = new URLSearchParams(location.search).get("game_id");
const myId = tg?.initDataUnsafe?.user?.id || null;
const initData = tg?.initData || "";

let state = null;
let selectedCard = null;
let busy = false;

if (!gameId) {
  statusEl.textContent = "Не передан game_id";
}

btnPlay.addEventListener("click", async () => {
  if (!state || !selectedCard) return;
  const actions = state.allowed_actions || {};
  if (actions.attack) {
    await sendMove({ action: "attack", card: selectedCard });
  } else if (actions.defend) {
    await sendMove({ action: "defend", card: selectedCard });
  }
});

btnPass.addEventListener("click", async () => {
  await sendMove({ action: "pass", card: "" });
});

btnTake.addEventListener("click", async () => {
  await sendMove({ action: "take", card: "" });
});

async function fetchState() {
  if (!gameId) return;
  const query = myId ? `?player_id=${myId}` : "";
  const response = await fetch(`/api/state/${gameId}${query}`, {
    headers: {
      "X-Telegram-Init-Data": initData,
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  state = await response.json();
  if (selectedCard && !(state.my_hand || []).includes(selectedCard)) {
    selectedCard = null;
  }
  render();
}

async function sendMove(body) {
  if (!gameId || busy) return;
  busy = true;
  try {
    const response = await fetch(`/api/move/${gameId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": initData,
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    state = await response.json();
    selectedCard = null;
    render();
  } catch (error) {
    statusEl.textContent = `Ошибка хода: ${String(error.message || error)}`;
  } finally {
    busy = false;
  }
}

function render() {
  if (!state) return;

  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  engine.clear("#0b1324");

  engine.roundedRect(16, 16, width - 32, 58, 12, "#111b31", "#1f2a44", 1);
  engine.text(`Игра: ${state.game_id}`, 28, 40, { size: 14, weight: "700" });
  engine.text(`Козырь: ${state.trump_sym}   Колода: ${state.deck_count}`, 28, 60, { size: 13, color: "#93c5fd" });

  const players = state.player_ids || [];
  const names = state.player_names || {};
  const handCounts = state.hand_counts || {};
  let py = 90;
  for (const pid of players) {
    const tag = pid === state.attacker_id ? "⚔" : pid === state.defender_id ? "🛡" : "•";
    const mine = pid === myId ? " (вы)" : "";
    engine.text(`${tag} ${names[String(pid)] || pid}${mine} — ${handCounts[String(pid)] ?? 0} карт`, 24, py, {
      size: 13,
      color: pid === myId ? "#f8fafc" : "#94a3b8",
    });
    py += 18;
  }

  const tableTop = 170;
  engine.roundedRect(16, tableTop, width - 32, 150, 14, "#14532d", "#166534");
  engine.text("Стол", 28, tableTop + 24, { size: 13, color: "#bbf7d0" });

  const table = state.table || [];
  let tx = 26;
  let ty = tableTop + 38;
  for (const [attack, defend] of table) {
    drawCard(engine, { x: tx, y: ty, label: attack, trump: attack.endsWith(state.trump_sym) });
    if (defend) {
      drawCard(engine, { x: tx + 26, y: ty + 12, label: defend, trump: defend.endsWith(state.trump_sym) });
    }
    tx += 90;
    if (tx + 90 > width - 24) {
      tx = 26;
      ty += 96;
    }
  }

  const hand = state.my_hand || [];
  const handTop = Math.max(height - 140, 334);
  engine.text("Ваши карты", 24, handTop - 10, { size: 12, color: "#93c5fd" });

  // Рисуем колоду слева
  const deckCount = state.deck_count || 0;
  drawDeck(engine, { x: 24, y: handTop, count: deckCount });

  let hx = 96;
  for (const card of hand) {
    const isSelected = selectedCard === card;
    drawCard(engine, {
      x: hx,
      y: handTop,
      label: card,
      selected: isSelected,
      trump: card.endsWith(state.trump_sym),
    });
    engine.registerClick(hx, handTop, 56, 82, () => {
      selectedCard = selectedCard === card ? null : card;
      render();
    });
    hx += 62;
    if (hx + 56 > width - 24) {
      break;
    }
  }

  const actions = state.allowed_actions || {};
  btnPlay.disabled = !selectedCard || !(actions.attack || actions.defend);
  btnPass.disabled = !actions.pass;
  btnTake.disabled = !actions.take;

  if (state.finished) {
    if (state.loser_id === myId) {
      statusEl.textContent = "Игра завершена: вы проиграли";
    } else if ((state.winners || []).includes(myId)) {
      statusEl.textContent = "Игра завершена: вы победили";
    } else {
      statusEl.textContent = "Игра завершена";
    }
  } else {
    statusEl.textContent = selectedCard
      ? `Выбрана карта ${selectedCard}`
      : "Выберите карту и сделайте ход";
  }
}

async function tick() {
  try {
    await fetchState();
  } catch (error) {
    statusEl.textContent = `Ошибка загрузки: ${String(error.message || error)}`;
  }
}

setInterval(tick, 1500);
tick();
