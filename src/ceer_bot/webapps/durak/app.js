const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const params = new URLSearchParams(window.location.search);
const gameId = params.get("game_id") || window.location.pathname.split("/").filter(Boolean).pop();
const myId = tg?.initDataUnsafe?.user?.id ?? null;
const initData = tg?.initData ?? "";

let state = null;
let poll = null;
let selected = null;
let sending = false;
let noticeTimer = null;

const RED = new Set(["♥", "♦"]);
const isRed = (c) => RED.has(c.slice(-1));

function cardEl(disp, { trump = false, covered = false, clickable = false, sel = false } = {}) {
  const suit = disp.slice(-1);
  const val = disp.slice(0, -1);
  const col = isRed(suit) ? "red" : "blk";
  const cls = ["card", col, trump ? "trump-c" : "", covered ? "cov" : "", sel ? "sel" : "", clickable ? "act" : ""]
    .filter(Boolean)
    .join(" ");
  return `<div class="${cls}" onclick="onCard('${disp}')"><div class="vt">${val}</div><div class="st">${suit}</div><div class="sc">${suit}</div><div class="vb">${val}</div></div>`;
}

function showNotice(text) {
  const el = document.getElementById("notice");
  if (!el) return;
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => el.classList.remove("show"), 2200);
}

function selectedAction() {
  if (!state) return null;
  const actions = state.allowed_actions || {};
  if (actions.attack) return "attack";
  if (actions.defend) return "defend";
  return null;
}

function updateMainButton(s, selectedCard) {
  if (!tg?.MainButton) return;
  const actions = s?.allowed_actions || {};
  const action = actions.attack ? "attack" : actions.defend ? "defend" : null;
  if (action && selectedCard && !sending) {
    tg.MainButton.setText(action === "attack" ? "Сходить картой" : "Отбиться картой");
    tg.MainButton.show();
    tg.MainButton.enable();
  } else {
    tg.MainButton.hide();
  }
}

if (tg?.MainButton) {
  tg.MainButton.onClick(() => onPlaySelected());
}

function render(s) {
  const actions = s.allowed_actions || {};
  const canAttack = !!actions.attack;
  const canDefend = !!actions.defend;
  const canTake = !!actions.take;
  const canPass = !!actions.pass;
  const canTransfer = !!actions.transfer;
  const amI = !!(myId && s.player_ids.includes(myId));

  let wov = document.getElementById("woverlay");
  if (s.phase === "joining") {
    if (!wov) {
      wov = document.createElement("div");
      wov.id = "woverlay";
      wov.className = "woverlay";
      document.body.appendChild(wov);
    }
    let rows = "";
    for (const pid of s.player_ids) {
      rows += `<div class="wrow"><span>👤</span><span>${s.player_names[pid] ?? "?"}</span></div>`;
    }
    wov.innerHTML = `<div class="spin"></div><div class="wtitle">🃏 Дурак</div><div class="wsub">Ожидаем игроков…</div><div class="wplayers">${rows}</div>`;
    return;
  } else if (wov) {
    wov.remove();
  }

  const sb = document.getElementById("sbar");
  sb.className = "sbar";
  if (s.finished) {
    sb.textContent = s.loser_id ? `ДУРАК: ${s.player_names[s.loser_id]}!` : "Игра завершена";
  } else if (canDefend) {
    sb.textContent = canTransfer ? "Ваш ход: отбить или перевести" : "Ваш ход: отбить или взять";
    sb.classList.add("myturn");
  } else if (canAttack && s.table.length) {
    sb.textContent = canPass ? "Можно подкинуть или завершить" : "Можно подкинуть карту";
    sb.classList.add("myturn");
  } else if (canAttack) {
    sb.textContent = "Ваш ход: выберите карту для атаки";
    sb.classList.add("myturn");
  } else {
    const tid = s.phase === "attacking" ? s.attacker_id : s.defender_id;
    sb.textContent = s.phase === "attacking" ? `Атакует ${s.player_names[tid] ?? "?"}` : `Защищается ${s.player_names[tid] ?? "?"}`;
    sb.classList.add("wait");
  }

  const ts = s.trump_sym ?? "?";
  const tc = isRed(ts) ? "var(--red)" : "var(--txt)";
  document.getElementById("chips").innerHTML = `<div class="chip chip-trump"><span style="color:${tc};font-size:15px">${ts}</span> Козырь</div><div class="chip">🗃 ${s.deck_count}</div>`;

  const pb = document.getElementById("pbar");
  pb.innerHTML = "";
  for (const pid of s.player_ids) {
    const nm = s.player_names[pid] ?? "?";
    const cn = s.hand_counts[pid] ?? 0;
    const out = s.winners.includes(pid);
    let cls = "pchip";
    let ico = "👤";
    if (out) {
      cls += " out";
      ico = "✅";
    } else if ((s.attackers || []).includes(pid) && !s.finished) {
      cls += " atk";
      ico = "⚔️";
    } else if (pid === s.defender_id && !s.finished) {
      cls += " def";
      ico = "🛡";
    }
    if (pid === myId) ico = "🫵";
    pb.innerHTML += `<div class="${cls}"><span>${ico}</span><span class="pn">${nm}</span><span class="pc">${out ? "вышел" : `${cn}🃏`}</span></div>`;
  }

  const ta = document.getElementById("tarea");
  const te = document.getElementById("tempty");
  ta.querySelectorAll(".tpair").forEach((e) => e.remove());
  if (!s.table?.length) {
    te.style.display = "flex";
  } else {
    te.style.display = "none";
    for (const [atk, dfn] of s.table) {
      const atkT = atk.slice(-1) === s.trump_sym;
      const dfnT = dfn && dfn.slice(-1) === s.trump_sym;
      const pair = document.createElement("div");
      pair.className = "tpair";
      pair.innerHTML = cardEl(atk, { trump: atkT }) + (dfn ? cardEl(dfn, { trump: dfnT, covered: true }) : '<div class="tslot"></div>');
      ta.appendChild(pair);
    }
  }

  const myHand = s.my_hand ?? [];
  const ha = document.getElementById("harea");
  const hc = document.getElementById("hcards");
  if (amI) {
    ha.style.display = "";
    hc.innerHTML = "";
    for (const c of myHand) {
      hc.innerHTML += cardEl(c, { trump: c.slice(-1) === s.trump_sym, clickable: (canAttack || canDefend) && !s.finished, sel: selected === c });
    }
  } else {
    ha.style.display = "none";
  }

  const acts = document.getElementById("acts");
  const hint = document.getElementById("acthint");
  const bplay = document.getElementById("btn-play");
  const bp = document.getElementById("btn-pass");
  const bt = document.getElementById("btn-take");
  if (!s.finished && amI) {
    acts.style.display = "flex";
    hint.style.display = "block";
    bplay.style.display = canAttack || canDefend ? "" : "none";
    bplay.disabled = sending || !selected || !(canAttack || canDefend);

    if (canAttack || canDefend) {
      hint.textContent = selected ? `Выбрана карта: ${selected}` : "Выберите карту и нажмите «Сходить»";
    } else if (canPass) {
      hint.textContent = "Можно завершить атаку";
    } else if (canTake) {
      hint.textContent = "Можно взять карты";
    } else {
      hint.textContent = "Сейчас ход другого игрока";
    }

    if (canPass) {
      bp.style.display = "";
      bt.style.display = "none";
      bp.disabled = sending;
    } else if (canTake) {
      bp.style.display = "none";
      bt.style.display = "";
      bt.disabled = sending;
    } else {
      bp.style.display = "none";
      bt.style.display = "none";
    }
  } else {
    acts.style.display = "none";
    hint.style.display = "none";
  }

  updateMainButton(s, selected);

  if (s.finished && !document.querySelector(".overlay")) {
    showResult(s);
  }
}

function showResult(s) {
  const bet = parseFloat(s.bet || "0");
  let emoji;
  let title;
  let sub = "";
  if (!s.loser_id) {
    emoji = "🏁";
    title = "Игра завершена";
  } else if (s.loser_id === myId) {
    emoji = "🤡";
    title = "Вы — дурак";
    if (bet > 0) sub = `Списано: -${(bet * (s.player_ids.length - 1)).toFixed(2)} ${s.currency ?? ""}`;
  } else {
    emoji = "🏆";
    title = `Дурак: ${s.player_names[s.loser_id]}`;
    if (bet > 0 && myId && s.winners.includes(myId)) sub = `+${bet.toFixed(2)} ${s.currency ?? ""}`;
  }

  const ov = document.createElement("div");
  ov.className = "overlay";
  ov.innerHTML = `<div class="rbox"><span class="remi">${emoji}</span><div class="rtit">${title}</div><div class="rsub">${sub}</div></div>`;
  ov.addEventListener("click", () => tg?.close?.());
  document.body.appendChild(ov);
  setTimeout(() => tg?.close?.(), 7000);
}

function schedule(ms) {
  clearTimeout(poll);
  poll = setTimeout(fetchState, ms);
}

async function fetchState() {
  if (!gameId) return;
  try {
    const query = myId ? `?player_id=${encodeURIComponent(myId)}` : "";
    const r = await fetch(`/api/durak/${gameId}${query}`, {
      headers: initData ? { "X-Telegram-Init-Data": initData } : {},
    });
    if (!r.ok) {
      schedule(3000);
      return;
    }
    const s = await r.json();
    const changed = !state || JSON.stringify(s) !== JSON.stringify(state);
    if (changed) {
      state = s;
      render(s);
    }
    if (!s.finished) schedule(s.phase === "joining" ? 2000 : 1300);
  } catch {
    schedule(3000);
  }
}

function onCard(card) {
  if (!state || state.finished || !initData || sending) return;
  const actions = state.allowed_actions || {};
  if (!actions.attack && !actions.defend) return;
  selected = selected === card ? null : card;
  render(state);
}

function onPlaySelected() {
  const action = selectedAction();
  if (!selected || !action) {
    showNotice("Сначала выберите карту");
    return;
  }
  sendMove({ action, card: selected });
}

function onPass() {
  if (!sending) sendMove({ action: "pass" });
}

function onTake() {
  if (!sending) sendMove({ action: "take" });
}

async function sendMove(body) {
  if (sending) return;
  sending = true;
  clearTimeout(poll);
  if (state) render(state);

  try {
    const r = await fetch(`/api/durak/${gameId}/move`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(initData ? { "X-Telegram-Init-Data": initData } : {}),
      },
      body: JSON.stringify(body),
    });

    if (r.ok) {
      state = await r.json();
      selected = null;
      render(state);
      if (!state.finished) schedule(1300);
    } else {
      let detail = "Ход не выполнен";
      try {
        const err = await r.json();
        detail = err?.detail || detail;
      } catch {
      }
      showNotice(detail);
      if (state) render(state);
      schedule(1500);
    }
  } catch {
    showNotice("Не удалось отправить ход");
    if (state) render(state);
    schedule(2000);
  } finally {
    sending = false;
    if (state) render(state);
  }
}

fetchState();
