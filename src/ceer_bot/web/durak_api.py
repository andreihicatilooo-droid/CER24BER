"""API роутер для Durak Mini App + HTML страница игры.

Эндпоинты:
  GET  /durak/{game_id}           — HTML страница Mini App
  GET  /api/durak/{game_id}       — состояние игры (JSON, без авторизации)
  POST /api/durak/{game_id}/move  — сделать ход (требует Telegram initData)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import TYPE_CHECKING
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ceer_bot.games.durak import (
    DurakGame,
    SUITS,
    card_display,
    check_finished,
    do_attack,
    do_defend,
    do_pass,
    do_take,
    get_game,
)
from ceer_bot.keyboards.game_menu import build_durak_board
from ceer_bot.games.durak import format_board
from ceer_bot.services.users import InsufficientBalanceError
from ceer_bot.texts import DURAK_TEXT

if TYPE_CHECKING:
    from ceer_bot.container import AppContainer

logger = logging.getLogger(__name__)

# ─── HTML Mini App ────────────────────────────────────────────────────────────

_DURAK_HTML = """\
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Дурак</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{
  --bg:var(--tg-theme-bg-color,#18181b);
  --bg2:var(--tg-theme-secondary-bg-color,#27272a);
  --txt:var(--tg-theme-text-color,#fafafa);
  --hint:var(--tg-theme-hint-color,#71717a);
  --btn:var(--tg-theme-button-color,#6366f1);
  --red:#f43f5e; --blk:#94a3b8;
  --trump:#fbbf24;
}
html,body{height:100%;background:var(--bg);color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  overscroll-behavior:none}
body{display:flex;flex-direction:column;align-items:center;padding:8px 8px 20px}
h1{font-size:18px;font-weight:700;margin-bottom:10px;opacity:.9}

/* Статус-строка */
.status{font-size:14px;font-weight:600;min-height:20px;margin-bottom:4px;text-align:center}
.bet-line{font-size:12px;color:var(--hint);margin-bottom:10px;min-height:14px}

/* Козырь + колода */
.info-bar{display:flex;gap:10px;margin-bottom:10px;width:100%;max-width:400px}
.info-chip{background:var(--bg2);border-radius:10px;padding:6px 12px;
  font-size:13px;font-weight:600;display:flex;align-items:center;gap:5px}
.trump-sym{font-size:18px;line-height:1}
.red{color:var(--red)}.blk{color:var(--blk)}

/* Игроки */
.players{display:flex;flex-direction:column;gap:6px;width:100%;max-width:400px;margin-bottom:10px}
.player{background:var(--bg2);border-radius:12px;padding:8px 12px;
  display:flex;align-items:center;gap:8px;
  border:2px solid transparent;transition:border-color .2s}
.player.active-atk{border-color:#f59e0b}
.player.active-def{border-color:#38bdf8}
.pname{font-size:14px;font-weight:600;flex:1}
.pcnt{font-size:12px;color:var(--hint)}
.picon{font-size:18px;line-height:1;width:24px;text-align:center}
.pout{opacity:.4}

/* Стол */
.table-wrap{width:100%;max-width:400px;margin-bottom:10px}
.table-label{font-size:11px;color:var(--hint);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}
.table-cards{display:flex;flex-wrap:wrap;gap:6px;min-height:42px;
  background:var(--bg2);border-radius:12px;padding:8px}
.tpair{display:flex;align-items:center;gap:3px}
.tcard{font-size:14px;font-weight:700;padding:4px 8px;border-radius:8px;background:#1e293b}
.tcard.red{color:var(--red)}.tcard.blk{color:var(--blk)}
.tcard.covered{background:#14532d;color:#86efac}
.tarrow{color:var(--hint);font-size:12px}
.tempty{color:var(--hint);font-size:13px;align-self:center}

/* Моя рука */
.hand-wrap{width:100%;max-width:400px;margin-bottom:10px}
.hand-label{font-size:11px;color:var(--hint);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}
.hand-cards{display:flex;flex-wrap:wrap;gap:6px}
.hcard{font-size:15px;font-weight:700;padding:8px 12px;border-radius:12px;
  background:var(--bg2);cursor:pointer;border:2px solid transparent;
  transition:transform .1s,border-color .15s,background .15s;user-select:none}
.hcard.red{color:var(--red)}.hcard.blk{color:var(--blk)}
.hcard.trump{box-shadow:0 0 0 2px var(--trump);border-color:var(--trump)!important}
.hcard.my-turn:hover{background:#1e293b;transform:translateY(-4px)}
.hcard.my-turn:active{transform:translateY(0) scale(.95)}
.hcard.selected{border-color:var(--btn)!important;background:#1e1b4b!important;transform:translateY(-6px)}

/* Кнопки действий */
.actions{display:flex;gap:8px;width:100%;max-width:400px;margin-bottom:10px}
.action-btn{flex:1;padding:10px;border-radius:12px;border:none;
  font-size:14px;font-weight:600;cursor:pointer;
  transition:opacity .15s,transform .1s}
.action-btn:active{transform:scale(.96)}
.btn-pass{background:#16a34a;color:#fff}
.btn-take{background:#dc2626;color:#fff}
.btn-beat{background:var(--btn);color:#fff}
.action-btn:disabled{opacity:.35;cursor:default}

/* Оверлей результата */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);
  display:flex;align-items:center;justify-content:center;
  animation:fadein .3s;z-index:10}
@keyframes fadein{from{opacity:0}to{opacity:1}}
.rbox{background:var(--bg);border-radius:24px;padding:36px 40px;
  text-align:center;max-width:280px;animation:scalein .3s cubic-bezier(.34,1.56,.64,1)}
@keyframes scalein{from{transform:scale(.7);opacity:0}to{transform:scale(1);opacity:1}}
.remoji{font-size:60px;margin-bottom:14px;display:block}
.rtitle{font-size:22px;font-weight:800;margin-bottom:6px}
.rsub{font-size:14px;color:var(--hint)}
</style>
</head>
<body>
<h1>🃏 Дурак</h1>
<div class="status" id="st">Загрузка...</div>
<div class="bet-line" id="bl"></div>
<div class="info-bar" id="ib"></div>
<div class="players" id="pl"></div>
<div class="table-wrap">
  <div class="table-label">Стол</div>
  <div class="table-cards" id="tbl"></div>
</div>
<div class="hand-wrap" id="hwrap" style="display:none">
  <div class="hand-label">Ваши карты</div>
  <div class="hand-cards" id="hand"></div>
</div>
<div class="actions" id="acts" style="display:none">
  <button class="action-btn btn-pass" id="btn-pass" onclick="onPass()">✅ Закончить атаку</button>
  <button class="action-btn btn-take" id="btn-take" onclick="onTake()">🤚 Взять карты</button>
</div>

<script>
const tg = window.Telegram.WebApp;
tg.ready(); tg.expand();

const gameId  = location.pathname.split('/').filter(Boolean).pop();
const myId    = tg.initDataUnsafe?.user?.id ?? null;
const initData = tg.initData;

let state = null, poll = null, selected = null;

const RED_SUITS = new Set(['♥','♦']);

function suitClass(card){ return RED_SUITS.has(card.slice(-1)) ? 'red' : 'blk'; }

/* ── Запрос состояния ── */
async function fetch_state(){
  try{
    const r = await fetch(`/api/durak/${gameId}`);
    if(!r.ok) return;
    const s = await r.json();
    if(!state || JSON.stringify(s) !== JSON.stringify(state)){ state=s; render(s); }
    if(!s.finished) poll = setTimeout(fetch_state, 1500);
  } catch(e){ poll = setTimeout(fetch_state, 3000); }
}

/* ── Рендер ── */
function render(s){
  const isMyTurn = (s.phase==='attacking' && s.attacker_id===myId) ||
                   (s.phase==='defending' && s.defender_id===myId);

  /* Статус */
  const st = document.getElementById('st');
  if(s.finished){ st.textContent = s.loser_id ? `🤡 ДУРАК: ${s.player_names[s.loser_id]}!` : 'Игра завершена'; }
  else if(s.phase==='joining'){ st.textContent = 'Ожидание игроков...'; }
  else if(isMyTurn){ st.textContent = s.phase==='attacking' ? '⚔️ Ваш ход — атакуйте!' : '🛡 Ваш ход — защищайтесь!'; }
  else {
    const tid = s.phase==='attacking' ? s.attacker_id : s.defender_id;
    const tname = s.player_names[tid] ?? '?';
    st.textContent = s.phase==='attacking' ? `⚔️ Атакует ${tname}` : `🛡 Защищается ${tname}`;
  }

  /* Ставка */
  const bet = parseFloat(s.bet||0);
  document.getElementById('bl').textContent = bet>0 ? `Ставка: ${bet.toFixed(2)} ${s.currency??''}` : '';

  /* Козырь + колода */
  const sym = s.trump_sym||'?';
  const isRed = RED_SUITS.has(sym);
  document.getElementById('ib').innerHTML = `
    <div class="info-chip">🃏 Козырь: <span class="trump-sym ${isRed?'red':'blk'}">${sym}</span></div>
    <div class="info-chip">🗃 Колода: <b>${s.deck_count}</b></div>`;

  /* Игроки */
  const pl = document.getElementById('pl');
  pl.innerHTML = '';
  for(const pid of s.player_ids){
    const name = s.player_names[pid]??'?';
    const cnt  = s.hand_counts[pid]??0;
    const out  = s.winners.includes(pid);
    let icon = '👤', cls = '';
    if(out){ icon='✅'; cls='pout'; }
    else if(pid===s.attacker_id && !s.finished){ icon='⚔️'; cls='active-atk'; }
    else if(pid===s.defender_id && !s.finished){ icon='🛡'; cls='active-def'; }
    pl.innerHTML += `<div class="player ${cls}">
      <div class="picon">${icon}</div>
      <div class="pname">${name}</div>
      <div class="pcnt">${out?'вышел':cnt+' карт'}</div>
    </div>`;
  }

  /* Стол */
  const tbl = document.getElementById('tbl');
  tbl.innerHTML = '';
  if(!s.table.length){ tbl.innerHTML='<div class="tempty">— пусто —</div>'; }
  else {
    for(const [atk,dfn] of s.table){
      const ac=suitClass(atk), dc=dfn?suitClass(dfn):'';
      tbl.innerHTML += `<div class="tpair">
        <span class="tcard ${ac}">${atk}</span>
        <span class="tarrow">→</span>
        ${dfn ? `<span class="tcard covered ${dc}">${dfn}</span>` : '<span class="tcard" style="color:var(--hint)">❓</span>'}
      </div>`;
    }
  }

  /* Моя рука */
  const myHand = s.my_hand ?? [];
  const hwrap  = document.getElementById('hwrap');
  const handEl = document.getElementById('hand');
  if(myHand.length>0 || (myId && s.player_ids.includes(myId))){
    hwrap.style.display='';
    handEl.innerHTML='';
    const trumpSym = s.trump_sym;
    for(const c of myHand){
      const sc = suitClass(c);
      const isTrump = c.slice(-1)===trumpSym;
      const isSel   = selected===c;
      const myT     = isMyTurn && !s.finished;
      handEl.innerHTML += `<div class="hcard ${sc}${isTrump?' trump':''}${myT?' my-turn':''}${isSel?' selected':''}"
        data-card="${c}" onclick="onCard('${c}')">${c}</div>`;
    }
  } else { hwrap.style.display='none'; }

  /* Кнопки действий */
  const acts = document.getElementById('acts');
  const btnPass = document.getElementById('btn-pass');
  const btnTake = document.getElementById('btn-take');
  if(!s.finished && isMyTurn){
    acts.style.display='flex';
    const tableHasCards = s.table.length>0;
    const allBeaten     = s.table.length>0 && s.table.every(([,d])=>d!==null);
    btnPass.style.display = s.phase==='attacking' ? '' : 'none';
    btnTake.style.display = s.phase==='defending' ? '' : 'none';
    btnPass.disabled = !tableHasCards || !allBeaten;
  } else { acts.style.display='none'; }

  /* Оверлей */
  if(s.finished && !document.querySelector('.overlay')){ showResult(s); }
}

function showResult(s){
  let emoji,title,sub='';
  if(!s.loser_id){ emoji='🏁'; title='Игра завершена'; }
  else if(s.loser_id===myId){ emoji='🤡'; title='Вы — ДУРАК!'; const bet=parseFloat(s.bet||0); if(bet>0) sub=`-${(bet*(s.player_ids.length-1)).toFixed(2)} ${s.currency??''}`; }
  else { emoji='🏆'; title=`ДУРАК: ${s.player_names[s.loser_id]}`; }
  const ov=document.createElement('div');
  ov.className='overlay';
  ov.innerHTML=`<div class="rbox"><span class="remoji">${emoji}</span><div class="rtitle">${title}</div><div class="rsub">${sub}</div></div>`;
  ov.addEventListener('click',()=>tg.close());
  document.body.appendChild(ov);
  setTimeout(()=>tg.close(),6000);
}

/* ── Клик по карте ── */
function onCard(card){
  if(!state || !initData) return;
  const isMyTurn = (state.phase==='attacking' && state.attacker_id===myId) ||
                   (state.phase==='defending' && state.defender_id===myId);
  if(!isMyTurn||state.finished) return;

  if(selected===card){
    /* Второй клик — отправить ход */
    sendMove({action: state.phase==='attacking'?'attack':'defend', card});
    selected=null;
  } else {
    selected=card;
    render(state);
  }
}

/* ── Кнопки ── */
function onPass(){ if(state&&initData){ sendMove({action:'pass'}); selected=null; } }
function onTake(){ if(state&&initData){ sendMove({action:'take'}); selected=null; } }

/* ── Отправка хода ── */
async function sendMove(body){
  clearTimeout(poll);
  try{
    const r=await fetch(`/api/durak/${gameId}/move`,{
      method:'POST',
      headers:{'Content-Type':'application/json','X-Telegram-Init-Data':initData},
      body:JSON.stringify(body)
    });
    if(r.ok){ state=await r.json(); render(state); if(!state.finished) poll=setTimeout(fetch_state,1500); }
    else { selected=null; render(state); poll=setTimeout(fetch_state,1500); }
  } catch(e){ selected=null; poll=setTimeout(fetch_state,1500); }
}

fetch_state();
</script>
</body>
</html>
"""


# ─── Валидация Telegram initData ──────────────────────────────────────────────

def _validate_init_data(init_data: str, bot_token: str) -> dict | None:
    try:
        params: dict[str, str] = {}
        for part in init_data.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = v
        hash_val = params.pop("hash", None)
        if not hash_val:
            return None
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key   = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed     = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, hash_val):
            return None
        user_str = unquote(params.get("user", "{}"))
        return json.loads(user_str)
    except Exception:
        return None


# ─── Сериализация состояния ────────────────────────────────────────────────────

def _game_state(game: DurakGame, currency: str, player_id: int | None = None) -> dict:
    """JSON-совместимый снимок состояния игры.

    my_hand заполняется только для запросившего игрока (если он участник).
    """
    trump_sym = SUITS.get(game.trump, "?")

    # Стол: [["карта_атк","карта_защ"|null], ...]  (красивый вид для JS)
    table_view = []
    for atk, dfn in game.table:
        table_view.append([card_display(atk), card_display(dfn) if dfn else None])

    my_hand: list[str] | None = None
    if player_id and player_id in game.player_ids:
        my_hand = [card_display(c) for c in game.hands.get(player_id, [])]

    return {
        "game_id":      game.game_id,
        "phase":        game.phase,
        "trump":        game.trump,
        "trump_sym":    trump_sym,
        "deck_count":   len(game.deck),
        "player_ids":   game.player_ids,
        "player_names": game.player_names,
        "hand_counts":  {pid: len(h) for pid, h in game.hands.items()},
        "attacker_id":  game.player_ids[game.attacker_idx] if game.player_ids else None,
        "defender_id":  game.player_ids[game.defender_idx] if len(game.player_ids) > 1 else None,
        "table":        table_view,
        "winners":      game.winners,
        "finished":     game.finished,
        "loser_id":     game.loser_id,
        "bet":          str(game.bet),
        "currency":     currency,
        "my_hand":      my_hand,
    }


class MoveBody(BaseModel):
    action: str          # "attack" | "defend" | "take" | "pass"
    card:   str = ""     # только для attack/defend


# ─── Роутер ───────────────────────────────────────────────────────────────────

def build_durak_router(container: "AppContainer") -> APIRouter:
    router   = APIRouter()
    currency = container.user_service.wallet_currency

    @router.get("/durak/{game_id}", response_class=HTMLResponse, include_in_schema=False)
    async def durak_page(game_id: str) -> HTMLResponse:
        return HTMLResponse(content=_DURAK_HTML)

    @router.get("/api/durak/{game_id}")
    async def get_durak_state(game_id: str, request: Request) -> dict:
        game = get_game(game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Игра не найдена")
        # Пытаемся определить игрока из заголовка (необязательно)
        pid: int | None = None
        raw = request.headers.get("X-Telegram-Init-Data", "")
        if raw:
            ud = _validate_init_data(raw, container.settings.ceer_bot_token)
            if ud:
                pid = int(ud.get("id", 0)) or None
        return _game_state(game, currency, pid)

    @router.post("/api/durak/{game_id}/move")
    async def post_durak_move(game_id: str, body: MoveBody, request: Request) -> dict:
        raw = request.headers.get("X-Telegram-Init-Data", "")
        user_data = _validate_init_data(raw, container.settings.ceer_bot_token)
        if user_data is None:
            raise HTTPException(status_code=403, detail="Недействительный initData")

        player_id = int(user_data.get("id", 0))
        if player_id == 0:
            raise HTTPException(status_code=403, detail="Нет данных пользователя")

        game = get_game(game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Игра не найдена или завершена")

        if game.finished:
            raise HTTPException(status_code=400, detail="Игра уже завершена")

        if player_id not in game.player_ids:
            raise HTTPException(status_code=403, detail="Вы не участник этой игры")

        attacker_id = game.player_ids[game.attacker_idx]
        defender_id = game.player_ids[game.defender_idx] if len(game.player_ids) > 1 else None

        action = body.action

        if action == "attack":
            if player_id != attacker_id:
                raise HTTPException(status_code=400, detail="Сейчас не ваш ход (атака)")
            # Ищем карту по отображаемому виду — переводим обратно к внутреннему коду
            card_code = _find_card_by_display(game.hands.get(player_id, []), body.card)
            if card_code is None or not do_attack(game, card_code):
                raise HTTPException(status_code=400, detail="Недопустимый ход (атака)")

        elif action == "defend":
            if player_id != defender_id:
                raise HTTPException(status_code=400, detail="Сейчас не ваш ход (защита)")
            card_code = _find_card_by_display(game.hands.get(player_id, []), body.card)
            if card_code is None or not do_defend(game, card_code):
                raise HTTPException(status_code=400, detail="Этой картой нельзя защититься")

        elif action == "take":
            if player_id != defender_id:
                raise HTTPException(status_code=400, detail="Сейчас не ваш ход")
            do_take(game)

        elif action == "pass":
            if player_id != attacker_id:
                raise HTTPException(status_code=400, detail="Сейчас не ваш ход")
            if not do_pass(game):
                raise HTTPException(status_code=400, detail="Нельзя закончить атаку сейчас")

        else:
            raise HTTPException(status_code=400, detail="Неизвестное действие")

        # Проверяем завершение
        if check_finished(game):
            result_text = await _settle_and_format(game, container, currency)
            if container.bot:
                try:
                    await container.bot.edit_message_text(
                        chat_id=game.chat_id,
                        message_id=game.message_id,
                        text=result_text,
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    logger.warning("Не удалось обновить чат после завершения дурака: %s", exc)
        else:
            if container.bot:
                try:
                    kb = build_durak_board(game.game_id, game.phase, bool(game.table))
                    await container.bot.edit_message_text(
                        chat_id=game.chat_id,
                        message_id=game.message_id,
                        text=format_board(game),
                        reply_markup=kb,
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    logger.warning("Не удалось обновить доску дурака: %s", exc)

        return _game_state(game, currency, player_id)

    return router


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _find_card_by_display(hand: list[str], display: str) -> str | None:
    """Находит внутренний код карты по её отображаемому виду (напр. «J♠» → «Js»)."""
    for c in hand:
        if card_display(c) == display:
            return c
    return None


async def _settle_and_format(game: DurakGame, container: "AppContainer", currency: str) -> str:
    loser_id = game.loser_id
    if loser_id and game.bet > 0:
        winners = [pid for pid in game.player_ids if pid != loser_id]
        try:
            total = game.bet * len(winners)
            await container.user_service.debit(loser_id, total, "durak_loss")
            for wid in winners:
                await container.user_service.credit(wid, game.bet, "durak_win")
        except InsufficientBalanceError:
            logger.warning("Недостаточно средств дурак miniapp game_id=%s", game.game_id)
    loser_name = game.player_names.get(loser_id) if loser_id else None
    return DURAK_TEXT.result(loser_name, game.bet, currency)
