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

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from ceer_bot.games.durak import (
    DurakGame,
    SUITS,
  can_player_attack,
  can_player_defend,
  can_player_pass,
  can_player_take,
  can_transfer,
    card_display,
    check_finished,
    do_attack,
    do_defend,
    do_pass,
    do_take,
  do_transfer,
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
<title>Дурак 🃏</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{
  --bg:var(--tg-theme-bg-color,#0f172a);
  --bg2:var(--tg-theme-secondary-bg-color,#1e293b);
  --txt:var(--tg-theme-text-color,#f1f5f9);
  --hint:var(--tg-theme-hint-color,#64748b);
  --btn:var(--tg-theme-button-color,#6366f1);
  --red:#f43f5e;--blk:#1e293b;
  --trump:#f59e0b;--green:#10b981;
  --felt:#166534;--felt2:#14532d;
}
html,body{height:100%;background:var(--bg);color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  overscroll-behavior:none;overflow:hidden}
body{display:flex;flex-direction:column;height:100vh;height:100dvh}

/* Header */
.hdr{display:flex;align-items:center;justify-content:space-between;
  padding:10px 14px 6px;flex-shrink:0}
.gtitle{font-size:16px;font-weight:800;letter-spacing:-.3px}
.chips{display:flex;gap:6px}
.chip{background:var(--bg2);border-radius:20px;padding:4px 10px;
  font-size:12px;font-weight:700;display:flex;align-items:center;gap:4px}
.chip-trump{border:1.5px solid var(--trump)}

/* Status */
.sbar{text-align:center;padding:3px 14px;font-size:13px;font-weight:600;
  min-height:22px;flex-shrink:0;transition:color .2s}
.sbar.myturn{color:var(--btn)}
.sbar.wait{color:var(--hint)}

/* Players bar */
.pbar{display:flex;gap:6px;padding:4px 12px;flex-shrink:0;overflow-x:auto;
  scrollbar-width:none}
.pbar::-webkit-scrollbar{display:none}
.pchip{background:var(--bg2);border-radius:20px;padding:5px 10px;
  font-size:11px;display:flex;align-items:center;gap:4px;white-space:nowrap;
  border:2px solid transparent;transition:border-color .2s;flex-shrink:0}
.pchip.atk{border-color:var(--trump)}
.pchip.def{border-color:#38bdf8}
.pchip.out{opacity:.35}
.pchip .pn{font-weight:700;max-width:70px;overflow:hidden;text-overflow:ellipsis}
.pchip .pc{color:var(--hint)}

/* Table — green felt */
.tarea{flex:1;background:var(--felt);border-radius:18px;
  margin:5px 10px;padding:10px 10px 6px;
  display:flex;flex-wrap:wrap;gap:8px;align-content:flex-start;
  overflow:hidden;position:relative;min-height:100px}
.tempty{position:absolute;inset:0;display:flex;align-items:center;
  justify-content:center;color:rgba(255,255,255,.2);font-size:13px;
  font-weight:600;pointer-events:none}
.tpair{display:flex;flex-direction:column;align-items:center;gap:3px}

/* Card */
.card{width:46px;height:66px;border-radius:6px;background:#fff;
  border:1px solid #cbd5e1;display:flex;flex-direction:column;
  padding:3px 4px;position:relative;cursor:pointer;user-select:none;
  flex-shrink:0;transition:transform .15s,box-shadow .15s;
  box-shadow:0 2px 4px rgba(0,0,0,.35)}
.card .vt{font-size:12px;font-weight:900;line-height:1}
.card .st{font-size:9px;line-height:1;margin-top:1px}
.card .sc{position:absolute;top:50%;left:50%;
  transform:translate(-50%,-50%);font-size:24px;line-height:1;opacity:.85}
.card .vb{position:absolute;bottom:3px;right:4px;
  font-size:12px;font-weight:900;transform:rotate(180deg);line-height:1}
.card.red{color:var(--red)}
.card.blk{color:#1a1a2e}
.card.trump-c{box-shadow:0 0 0 2px var(--trump),0 3px 8px rgba(0,0,0,.4)}
.card.cov{background:#dcfce7;border-color:#86efac}
.card.cov.red{color:#dc2626}
.card.cov.blk{color:#166534}

/* Slot (куда положить карту защиты) */
.tslot{width:46px;height:66px;border-radius:6px;
  border:2px dashed rgba(255,255,255,.25);flex-shrink:0}

/* Hand */
.harea{flex-shrink:0;padding:5px 10px 4px}
.hlbl{font-size:10px;color:var(--hint);text-transform:uppercase;
  letter-spacing:.5px;margin-bottom:5px}
.hcards{display:flex;gap:5px;overflow-x:auto;padding:4px 0 10px;
  scrollbar-width:none}
.hcards::-webkit-scrollbar{display:none}
.hcards .card.act:hover{transform:translateY(-7px);
  box-shadow:0 10px 20px rgba(0,0,0,.45)}
.hcards .card.act:active{transform:translateY(-3px) scale(.97)}
.hcards .card.sel{
  transform:translateY(-12px)!important;
  box-shadow:0 0 0 3px var(--btn),0 12px 24px rgba(0,0,0,.5)!important}

/* Actions */
.acts{display:flex;gap:8px;padding:0 10px 14px;flex-shrink:0}
.abtn{flex:1;padding:12px;border-radius:12px;border:none;
  font-size:13px;font-weight:700;cursor:pointer;
  transition:opacity .15s,transform .1s;letter-spacing:.2px}
.abtn:active{transform:scale(.96)}
.abtn:disabled{opacity:.28;cursor:default;pointer-events:none}
.abtn.play{background:var(--btn);color:#fff}
.abtn.pass{background:var(--green);color:#fff}
.abtn.take{background:#dc2626;color:#fff}
.acthint{padding:0 12px 8px;color:var(--hint);font-size:12px;font-weight:600;flex-shrink:0}

/* Notice */
.notice{position:fixed;left:50%;bottom:18px;transform:translateX(-50%) translateY(20px);
  background:rgba(15,23,42,.94);color:#fff;padding:10px 14px;border-radius:14px;
  font-size:13px;font-weight:700;box-shadow:0 12px 30px rgba(0,0,0,.35);
  opacity:0;pointer-events:none;transition:opacity .2s,transform .2s;z-index:120;
  max-width:calc(100vw - 24px);text-align:center}
.notice.show{opacity:1;transform:translateX(-50%) translateY(0)}

/* Overlay result */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.82);
  display:flex;align-items:center;justify-content:center;
  animation:fi .3s;z-index:100}
@keyframes fi{from{opacity:0}to{opacity:1}}
.rbox{background:var(--bg);border-radius:24px;padding:40px 36px;
  text-align:center;max-width:280px;
  animation:pi .35s cubic-bezier(.34,1.56,.64,1)}
@keyframes pi{from{transform:scale(.65);opacity:0}to{transform:scale(1);opacity:1}}
.remi{font-size:64px;display:block;margin-bottom:14px}
.rtit{font-size:22px;font-weight:800;margin-bottom:6px}
.rsub{font-size:14px;color:var(--hint)}

/* Waiting overlay */
.woverlay{position:fixed;inset:0;background:var(--bg);
  display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:18px;z-index:80}
.wtitle{font-size:22px;font-weight:800}
.wsub{font-size:14px;color:var(--hint);text-align:center;max-width:240px}
.wplayers{background:var(--bg2);border-radius:16px;padding:14px 22px;
  min-width:200px}
.wrow{display:flex;align-items:center;gap:8px;padding:5px 0;
  font-size:14px;font-weight:600}
.spin{width:36px;height:36px;border:3px solid var(--bg2);
  border-top-color:var(--btn);border-radius:50%;
  animation:sp 1s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
</style>
</head>
<body>

<div class="hdr">
  <span class="gtitle">🃏 Дурак</span>
  <div class="chips" id="chips"></div>
</div>
<div class="sbar" id="sbar">Загрузка...</div>
<div class="pbar" id="pbar"></div>
<div class="tarea" id="tarea">
  <div class="tempty" id="tempty">Стол пуст</div>
</div>
<div class="harea" id="harea" style="display:none">
  <div class="hlbl">Ваши карты</div>
  <div class="hcards" id="hcards"></div>
</div>
<div class="acthint" id="acthint" style="display:none"></div>
<div class="acts" id="acts" style="display:none">
  <button class="abtn play" id="btn-play" onclick="onPlaySelected()">🃏 Сходить</button>
  <button class="abtn pass" id="btn-pass" onclick="onPass()">✅ Закончить атаку</button>
  <button class="abtn take" id="btn-take" onclick="onTake()">🤚 Взять карты</button>
</div>
<div class="notice" id="notice"></div>

<script>
const tg = window.Telegram?.WebApp;
if(tg){tg.ready();tg.expand();}

const gameId = location.pathname.split('/').filter(Boolean).pop();
const myId   = tg?.initDataUnsafe?.user?.id ?? null;
const initData = tg?.initData ?? '';

let state=null, poll=null, selected=null, sending=false, noticeTimer=null;

const RED = new Set(['♥','♦']);
const isRed = c => RED.has(c.slice(-1));

/* ── Рендер карты ── */
function cardEl(disp, {trump=false,covered=false,clickable=false,sel=false}={}){
  const suit = disp.slice(-1);
  const val  = disp.slice(0,-1);
  const col  = isRed(suit) ? 'red' : 'blk';
  const cls  = [
    'card',col,
    trump   ? 'trump-c' : '',
    covered ? 'cov'     : '',
    sel     ? 'sel'     : '',
    clickable ? 'act'   : '',
  ].filter(Boolean).join(' ');
  return `<div class="${cls}" onclick="onCard('${disp}')">
    <div class="vt">${val}</div><div class="st">${suit}</div>
    <div class="sc">${suit}</div>
    <div class="vb">${val}</div>
  </div>`;
}

function showNotice(text){
  const el = document.getElementById('notice');
  if(!el) return;
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => el.classList.remove('show'), 2200);
}

function selectedAction(){
  if(!state) return null;
  const actions = state.allowed_actions || {};
  if(actions.attack) return 'attack';
  if(actions.defend) return 'defend';
  return null;
}

function updateMainButton(s, selectedCard){
  if(!tg?.MainButton) return;
  const actions = s?.allowed_actions || {};
  const action = actions.attack ? 'attack' : (actions.defend ? 'defend' : null);
  if(action && selectedCard && !sending){
    tg.MainButton.setText(action==='attack' ? 'Сходить картой' : 'Отбиться картой');
    tg.MainButton.show();
    tg.MainButton.enable();
  } else {
    tg.MainButton.hide();
  }
}

if(tg?.MainButton){
  tg.MainButton.onClick(() => onPlaySelected());
}

/* ── Основной рендер ── */
function render(s){
  const actions = s.allowed_actions || {};
  const canAttack = !!actions.attack;
  const canDefend = !!actions.defend;
  const canTake = !!actions.take;
  const canPass = !!actions.pass;
  const canTransfer = !!actions.transfer;
  const isMyTurn  = canAttack || canDefend || canTake || canPass;
  const amI       = myId && s.player_ids.includes(myId);

  // Waiting overlay
  let wov = document.getElementById('woverlay');
  if(s.phase==='joining'){
    if(!wov){
      wov = document.createElement('div');
      wov.id='woverlay'; wov.className='woverlay';
      document.body.appendChild(wov);
    }
    let rows='';
    for(const pid of s.player_ids){
      rows+=`<div class="wrow"><span>👤</span><span>${s.player_names[pid]??'?'}</span></div>`;
    }
    wov.innerHTML=`<div class="spin"></div>
      <div class="wtitle">🃏 Дурак</div>
      <div class="wsub">Ожидаем игроков…</div>
      <div class="wplayers">${rows}</div>`;
    return;
  } else if(wov){ wov.remove(); }

  // Status bar
  const sb = document.getElementById('sbar');
  sb.className = 'sbar';
  if(s.finished){
    sb.textContent = s.loser_id ? `🤡 ДУРАК: ${s.player_names[s.loser_id]}!` : '🏁 Игра завершена';
  } else if(canDefend){
    sb.textContent = canTransfer
      ? '🛡 Ваш ход — отбейте карту или переведите тем же рангом'
      : '🛡 Ваш ход — отбейте карту или возьмите';
    sb.classList.add('myturn');
  } else if(canAttack && s.table.length){
    sb.textContent = canPass
      ? '⚔️ Можно подкинуть карту или завершить атаку'
      : '⚔️ Можно подкинуть карту того же ранга';
    sb.classList.add('myturn');
  } else if(canAttack){
    sb.textContent = '⚔️ Ваш ход — выберите карту для атаки';
    sb.classList.add('myturn');
  } else {
    const tid = s.phase==='attacking' ? s.attacker_id : s.defender_id;
    sb.textContent = s.phase==='attacking'
      ? `⚔️ Атакует ${s.player_names[tid]??'?'}…`
      : `🛡 Защищается ${s.player_names[tid]??'?'}…`;
    sb.classList.add('wait');
  }

  // Козырь + колода
  const ts = s.trump_sym??'?';
  const tc = isRed(ts) ? 'var(--red)' : 'var(--txt)';
  document.getElementById('chips').innerHTML=
    `<div class="chip chip-trump"><span style="color:${tc};font-size:15px">${ts}</span> Козырь</div>
     <div class="chip">🗃 ${s.deck_count}</div>`;

  // Players bar
  const pb=document.getElementById('pbar'); pb.innerHTML='';
  for(const pid of s.player_ids){
    const nm = s.player_names[pid]??'?';
    const cn = s.hand_counts[pid]??0;
    const out= s.winners.includes(pid);
    let cls='pchip', ico='👤';
    if(out){cls+=' out';ico='✅';}
    else if((s.attackers||[]).includes(pid)&&!s.finished){cls+=' atk';ico='⚔️';}
    else if(pid===s.defender_id&&!s.finished){cls+=' def';ico='🛡';}
    if(pid===myId) ico='🫵';
    pb.innerHTML+=`<div class="${cls}">
      <span>${ico}</span>
      <span class="pn">${nm}</span>
      <span class="pc">${out?'вышел':`${cn}🃏`}</span>
    </div>`;
  }

  // Стол
  const ta=document.getElementById('tarea');
  const te=document.getElementById('tempty');
  ta.querySelectorAll('.tpair').forEach(e=>e.remove());
  if(!s.table||!s.table.length){
    te.style.display='flex';
  } else {
    te.style.display='none';
    for(const [atk,dfn] of s.table){
      const atkT=atk.slice(-1)===s.trump_sym;
      const dfnT=dfn&&dfn.slice(-1)===s.trump_sym;
      const pair=document.createElement('div');
      pair.className='tpair';
      pair.innerHTML=cardEl(atk,{trump:atkT})
        +(dfn?cardEl(dfn,{trump:dfnT,covered:true}):'<div class="tslot"></div>');
      ta.appendChild(pair);
    }
  }

  // Рука
  const myHand=s.my_hand??[];
  const ha=document.getElementById('harea');
  const hc=document.getElementById('hcards');
  if(amI){
    ha.style.display='';
    hc.innerHTML='';
    for(const c of myHand){
      hc.innerHTML+=cardEl(c,{
        trump:c.slice(-1)===s.trump_sym,
        clickable:(canAttack||canDefend)&&!s.finished,
        sel:selected===c,
      });
    }
  } else { ha.style.display='none'; }

  // Кнопки
  const acts=document.getElementById('acts');
  const hint=document.getElementById('acthint');
  const bplay=document.getElementById('btn-play');
  const bp=document.getElementById('btn-pass');
  const bt=document.getElementById('btn-take');
  if(!s.finished&&amI){
    acts.style.display='flex';
    hint.style.display='block';
    bplay.style.display = (canAttack||canDefend) ? '' : 'none';
    bplay.disabled = sending || !selected || !(canAttack||canDefend);
    if(canAttack||canDefend){
      hint.textContent = selected
        ? `Выбрана карта: ${selected}`
        : 'Выберите карту и нажмите «Сходить»';
    } else if(canPass){
      hint.textContent = 'Можно завершить атаку';
    } else if(canTake){
      hint.textContent = 'Можно взять карты';
    } else {
      hint.textContent = 'Сейчас ход другого игрока';
    }
    if(canPass){
      bp.style.display='';bt.style.display='none';
      bp.disabled=sending;
    } else if(canTake) {
      bp.style.display='none';bt.style.display='';
      bt.disabled=sending;
    } else {
      bp.style.display='none';bt.style.display='none';
    }
  } else {
    acts.style.display='none';
    hint.style.display='none';
  }

  updateMainButton(s, selected);

  // Результат
  if(s.finished&&!document.querySelector('.overlay')) showResult(s);
}

function showResult(s){
  const bet=parseFloat(s.bet||0);
  let emoji,title,sub='';
  if(!s.loser_id){emoji='🏁';title='Игра завершена';}
  else if(s.loser_id===myId){
    emoji='🤡';title='Вы — ДУРАК!';
    if(bet>0) sub=`Списано: −${(bet*(s.player_ids.length-1)).toFixed(2)} ${s.currency??''}`;
  } else {
    emoji='🏆';title=`ДУРАК: ${s.player_names[s.loser_id]}`;
    if(bet>0&&myId&&s.winners.includes(myId))
      sub=`+${bet.toFixed(2)} ${s.currency??''}`;
  }
  const ov=document.createElement('div');
  ov.className='overlay';
  ov.innerHTML=`<div class="rbox">
    <span class="remi">${emoji}</span>
    <div class="rtit">${title}</div>
    <div class="rsub">${sub}</div>
  </div>`;
  ov.addEventListener('click',()=>tg?tg.close():null);
  document.body.appendChild(ov);
  setTimeout(()=>tg&&tg.close(),7000);
}

/* ── Поллинг ── */
async function fetchState(){
  try{
    const query = myId ? `?player_id=${encodeURIComponent(myId)}` : '';
    const r=await fetch(`/api/durak/${gameId}${query}`,{
      headers:initData?{'X-Telegram-Init-Data':initData}:{}
    });
    if(!r.ok){schedule(3000);return;}
    const s=await r.json();
    const changed=!state||JSON.stringify(s)!==JSON.stringify(state);
    if(changed){state=s;render(s);}
    if(!s.finished) schedule(s.phase==='joining'?2000:1300);
  }catch{schedule(3000);}
}
function schedule(ms){clearTimeout(poll);poll=setTimeout(fetchState,ms);}

/* ── Клик по карте ── */
function onCard(card){
  if(!state||state.finished||!initData||sending) return;
  const actions = state.allowed_actions || {};
  if(!actions.attack&&!actions.defend) return;
  selected = selected===card ? null : card;
  render(state);
}
function onPlaySelected(){
  const action = selectedAction();
  if(!selected||!action){
    showNotice('Сначала выберите карту');
    return;
  }
  sendMove({action, card:selected});
}
function onPass(){ if(!sending) sendMove({action:'pass'}); }
function onTake(){ if(!sending) sendMove({action:'take'}); }

/* ── Отправить ход ── */
async function sendMove(body){
  if(sending) return;
  sending = true;
  clearTimeout(poll);
  if(state) render(state);
  try{
    const r=await fetch(`/api/durak/${gameId}/move`,{
      method:'POST',
      headers:{'Content-Type':'application/json',
        ...(initData?{'X-Telegram-Init-Data':initData}:{})},
      body:JSON.stringify(body),
    });
    if(r.ok){
      state=await r.json();
      selected=null;
      render(state);
      if(!state.finished)schedule(1300);
    } else {
      let detail='Ход не выполнен';
      try{
        const err = await r.json();
        detail = err?.detail || detail;
      } catch {}
      showNotice(detail);
      if(state) render(state);
      schedule(1500);
    }
  }catch{
    showNotice('Не удалось отправить ход');
    if(state) render(state);
    schedule(2000);
  } finally {
    sending = false;
    if(state) render(state);
  }
}

fetchState();
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
    allowed_actions = {
      "attack": False,
      "defend": False,
      "take": False,
      "pass": False,
      "transfer": False,
    }
    if player_id and player_id in game.player_ids:
      hand = game.hands.get(player_id, [])
      my_hand = [card_display(c) for c in hand]
      allowed_actions = {
        "attack": any(can_player_attack(game, player_id, card) for card in hand),
        "defend": can_player_defend(game, player_id),
        "take": can_player_take(game, player_id),
        "pass": can_player_pass(game, player_id),
        "transfer": any(can_transfer(game, card) for card in hand),
      }

    attackers = [
      pid
      for pid in game.player_ids
      if pid not in game.winners and (len(game.player_ids) < 2 or pid != game.player_ids[game.defender_idx])
    ]

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
        "attackers":    attackers,
        "table":        table_view,
        "winners":      game.winners,
        "finished":     game.finished,
        "loser_id":     game.loser_id,
        "bet":          str(game.bet),
        "currency":     currency,
        "my_hand":      my_hand,
        "allowed_actions": allowed_actions,
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
      return RedirectResponse(url=f"/mini/durak/?game_id={game_id}", status_code=307)

    @router.get("/api/durak/{game_id}")
    async def get_durak_state(game_id: str, request: Request, player_id: int | None = Query(default=None)) -> dict:
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
        if pid is None and player_id in game.player_ids:
          pid = player_id
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

        action = body.action

        if action == "attack":
            # Ищем карту по отображаемому виду — переводим обратно к внутреннему коду
            card_code = _find_card_by_display(game.hands.get(player_id, []), body.card)
            if card_code is None or not do_attack(game, player_id, card_code):
                raise HTTPException(status_code=400, detail="Недопустимый ход (атака)")

        elif action == "defend":
            card_code = _find_card_by_display(game.hands.get(player_id, []), body.card)
            if card_code is None or not (do_defend(game, card_code) or do_transfer(game, card_code)):
                raise HTTPException(status_code=400, detail="Этой картой нельзя отбиться или перевести")

        elif action == "take":
            if not can_player_take(game, player_id):
                raise HTTPException(status_code=400, detail="Сейчас не ваш ход")
            do_take(game)

        elif action == "pass":
            if not do_pass(game, player_id):
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
