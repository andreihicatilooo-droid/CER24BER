"""API роутер для TTT Mini App + HTML страница игры.

Эндпоинты:
  GET  /ttt/{game_id}           — HTML страница Mini App
  GET  /api/ttt/{game_id}       — состояние игры (JSON, без авторизации)
  POST /api/ttt/{game_id}/move  — сделать ход (требует Telegram initData)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ceer_bot.games.tictactoe import (
    TicTacToeGame,
    check_winner,
    finish_game,
    get_game,
    get_winning_cells,
    is_draw,
    make_move,
    next_turn,
)
from ceer_bot.keyboards.game_menu import build_ttt_board
from ceer_bot.services.users import InsufficientBalanceError
from ceer_bot.texts import TTT_TEXT

if TYPE_CHECKING:
    from ceer_bot.container import AppContainer

logger = logging.getLogger(__name__)

# ─── HTML Mini App ────────────────────────────────────────────────────────────

_TTT_HTML = """\
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Крестики-нолики</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{
  --bg:var(--tg-theme-bg-color,#18181b);
  --bg2:var(--tg-theme-secondary-bg-color,#27272a);
  --txt:var(--tg-theme-text-color,#fafafa);
  --hint:var(--tg-theme-hint-color,#71717a);
  --btn:var(--tg-theme-button-color,#6366f1);
  --X:#f43f5e; --O:#38bdf8;
}
html,body{height:100%;background:var(--bg);color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  overscroll-behavior:none}
body{display:flex;flex-direction:column;align-items:center;padding:16px 12px 24px}
h1{font-size:20px;font-weight:700;letter-spacing:.5px;margin-bottom:18px;opacity:.9}

/* Карточки игроков */
.players{display:grid;grid-template-columns:1fr 1fr;gap:10px;width:100%;max-width:340px;margin-bottom:16px}
.pcard{background:var(--bg2);border-radius:16px;padding:12px 10px;
  display:flex;flex-direction:column;align-items:center;gap:5px;
  border:2px solid transparent;transition:border-color .2s,box-shadow .2s}
.pcard.ax{border-color:var(--X);box-shadow:0 0 12px color-mix(in srgb,var(--X) 30%,transparent)}
.pcard.ao{border-color:var(--O);box-shadow:0 0 12px color-mix(in srgb,var(--O) 30%,transparent)}
.psym{font-size:26px;font-weight:800;line-height:1}
.psym.sx{color:var(--X)}.psym.so{color:var(--O)}
.pname{font-size:12px;color:var(--hint);text-align:center;max-width:100%;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pbadge{font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px}
.pbadge.bx{background:var(--X);color:#fff}.pbadge.bo{background:var(--O);color:#000}

/* Статус */
.status{font-size:15px;font-weight:600;min-height:22px;margin-bottom:6px;text-align:center;transition:all .2s}
.bet-line{font-size:12px;color:var(--hint);margin-bottom:18px;min-height:16px}

/* Поле */
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;width:100%;max-width:320px}
.cell{aspect-ratio:1;border-radius:18px;background:var(--bg2);
  display:flex;align-items:center;justify-content:center;
  font-size:0;font-weight:800;cursor:pointer;
  border:2px solid rgba(255,255,255,.07);
  transition:transform .12s,background .15s,border-color .15s,box-shadow .15s;
  user-select:none;position:relative;overflow:hidden}
.cell::after{content:attr(data-sym);font-size:clamp(24px,8vw,42px);
  transition:transform .2s cubic-bezier(.34,1.56,.64,1),opacity .15s}
.cell.X{background:color-mix(in srgb,var(--X) 12%,var(--bg2));border-color:color-mix(in srgb,var(--X) 45%,transparent)}
.cell.O{background:color-mix(in srgb,var(--O) 12%,var(--bg2));border-color:color-mix(in srgb,var(--O) 45%,transparent)}
.cell.X::after{color:var(--X)}.cell.O::after{color:var(--O)}
.cell.my-turn:not(.taken):hover{background:rgba(255,255,255,.1);transform:scale(1.03)}
.cell.my-turn:not(.taken):active{transform:scale(.94)}
.cell.winner{animation:glow .65s ease-in-out infinite alternate}
@keyframes glow{to{box-shadow:0 0 20px 4px currentColor}}
.cell.X.winner{box-shadow:none;color:var(--X)}.cell.O.winner{color:var(--O)}
.cell.pop::after{animation:pop .25s cubic-bezier(.34,1.56,.64,1)}
@keyframes pop{0%{transform:scale(0);opacity:0}100%{transform:scale(1);opacity:1}}

/* Оверлей результата */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.72);
  display:flex;align-items:center;justify-content:center;
  animation:fadein .3s;z-index:10}
@keyframes fadein{from{opacity:0}to{opacity:1}}
.rbox{background:var(--bg);border-radius:24px;padding:36px 40px;
  text-align:center;max-width:280px;animation:scalein .3s cubic-bezier(.34,1.56,.64,1)}
@keyframes scalein{from{transform:scale(.7);opacity:0}to{transform:scale(1);opacity:1}}
.remoji{font-size:64px;margin-bottom:14px;display:block}
.rtitle{font-size:22px;font-weight:800;margin-bottom:6px}
.rsub{font-size:14px;color:var(--hint)}
</style>
</head>
<body>
<h1>❌⭕ Крестики-нолики</h1>
<div class="players">
  <div class="pcard" id="cx">
    <div class="psym sx">✕</div>
    <div class="pname" id="nx">—</div>
    <div class="pbadge bx">X</div>
  </div>
  <div class="pcard" id="co">
    <div class="psym so">◯</div>
    <div class="pname" id="no">Ожидание...</div>
    <div class="pbadge bo">O</div>
  </div>
</div>
<div class="status" id="st">Загрузка...</div>
<div class="bet-line" id="bl"></div>
<div class="grid" id="gr"></div>

<script>
const tg = window.Telegram.WebApp;
tg.ready(); tg.expand();

const gameId = location.pathname.split('/').filter(Boolean).pop();
const myId   = tg.initDataUnsafe?.user?.id ?? null;
const initData = tg.initData;
const SYM_EMPTY = '·';

let state = null, poll = null;

/* ── Построение сетки ── */
const gr = document.getElementById('gr');
for (let i=0;i<9;i++){
  const c=document.createElement('div');
  c.className='cell';c.dataset.i=i;c.dataset.sym='';
  c.addEventListener('click',()=>onCell(i));
  gr.appendChild(c);
}
const cells=[...gr.children];

/* ── Рендер ── */
function render(s){
  const myTurn=s.current_turn_id===myId&&!s.finished&&s.player_o;
  const mySymbol=s.player_x?.id===myId?'X':s.player_o?.id===myId?'O':null;

  /* Игроки */
  document.getElementById('nx').textContent=s.player_x?.name??'—';
  document.getElementById('no').textContent=s.player_o?.name??'Ожидание...';
  const cx=document.getElementById('cx'),co=document.getElementById('co');
  cx.className='pcard'+(s.current_turn_id===s.player_x?.id&&!s.finished?' ax':'');
  co.className='pcard'+(s.current_turn_id===s.player_o?.id&&!s.finished?' ao':'');

  /* Ставка */
  const bet=parseFloat(s.bet||0);
  document.getElementById('bl').textContent=bet>0?`Ставка: ${bet.toFixed(2)} ${s.currency??''}`:'';

  /* Статус */
  const st=document.getElementById('st');
  if(!s.player_o){st.textContent='Ожидаем второго игрока...';}
  else if(s.finished){
    if(s.winner_id){
      const wn=s.winner_id===s.player_x?.id?s.player_x?.name:s.player_o?.name;
      st.textContent=`🏆 Победил ${wn}!`;
    } else {st.textContent='🤝 Ничья!';}
  } else if(myTurn){st.textContent='Ваш ход!';}
  else {
    const tn=s.current_turn_id===s.player_x?.id?s.player_x?.name:s.player_o?.name;
    st.textContent=`Ход: ${tn}`;
  }

  /* Ячейки */
  cells.forEach((c,i)=>{
    const v=s.board[i];
    const prev=c.dataset.sym;
    const sym=v==='✕'?'X':v==='◯'?'O':'';
    c.dataset.sym=v===SYM_EMPTY?'':v;
    c.className='cell'+(sym?' '+sym:'')+(v!==SYM_EMPTY?' taken':'')+(myTurn&&mySymbol?' my-turn':'');
    /* pop-анимация при новом ходе */
    if(sym&&prev!==c.dataset.sym){c.classList.add('pop');setTimeout(()=>c.classList.remove('pop'),300);}
  });

  /* Победная комбинация */
  if(s.finished&&s.winner_cells){
    s.winner_cells.forEach(i=>cells[i].classList.add('winner'));
  }

  /* Оверлей результата */
  if(s.finished&&!document.querySelector('.overlay')){showResult(s);}
}

function showResult(s){
  let emoji,title,sub='';
  if(!s.winner_id){emoji='🤝';title='Ничья!';}
  else if(s.winner_id===myId){
    emoji='🏆';title='Вы победили!';
    const bet=parseFloat(s.bet||0);
    if(bet>0) sub=`+${(bet*2).toFixed(2)} ${s.currency??''}`;
  } else {
    const wn=s.winner_id===s.player_x?.id?s.player_x?.name:s.player_o?.name;
    emoji='😔';title=`Победил ${wn}`;
  }
  const ov=document.createElement('div');
  ov.className='overlay';
  ov.innerHTML=`<div class="rbox"><span class="remoji">${emoji}</span><div class="rtitle">${title}</div><div class="rsub">${sub}</div></div>`;
  ov.addEventListener('click',()=>tg.close());
  document.body.appendChild(ov);
  setTimeout(()=>tg.close(),5000);
}

/* ── Загрузка состояния ── */
async function fetch_state(){
  try{
    const r=await fetch(`/api/ttt/${gameId}`);
    if(!r.ok) return;
    state=await r.json();
    render(state);
    if(!state.finished) poll=setTimeout(fetch_state,1500);
  } catch(e){ poll=setTimeout(fetch_state,3000); }
}

/* ── Ход ── */
async function onCell(idx){
  if(!state||state.finished||!initData) return;
  if(state.current_turn_id!==myId||!state.player_o) return;
  if(cells[idx].classList.contains('taken')) return;
  clearTimeout(poll);
  try{
    const r=await fetch(`/api/ttt/${gameId}/move`,{
      method:'POST',
      headers:{'Content-Type':'application/json','X-Telegram-Init-Data':initData},
      body:JSON.stringify({cell:idx})
    });
    if(r.ok){ state=await r.json(); render(state); if(!state.finished) poll=setTimeout(fetch_state,1500); }
    else poll=setTimeout(fetch_state,1500);
  } catch(e){ poll=setTimeout(fetch_state,1500); }
}

fetch_state();
</script>
</body>
</html>
"""


# ─── Валидация Telegram initData ──────────────────────────────────────────────

def _validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Проверяет подпись Telegram WebApp initData.

    Возвращает dict с данными пользователя ({id, first_name, username, ...}) или None.
    """
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


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _game_state(game: TicTacToeGame, currency: str) -> dict:
    """Сериализует состояние игры в JSON-совместимый dict."""
    winning_cells = get_winning_cells(game.board) if game.finished and game.winner_id else None
    return {
        "game_id":       game.game_id,
        "board":         game.board,
        "player_x":      {"id": game.player_x_id, "name": game.player_x_name},
        "player_o":      {"id": game.player_o_id, "name": game.player_o_name} if game.player_o_id else None,
        "current_turn_id": game.current_turn_id,
        "finished":      game.finished,
        "winner_id":     game.winner_id,
        "winner_cells":  winning_cells,
        "bet":           str(game.bet),
        "currency":      currency,
    }


class MoveBody(BaseModel):
    cell: int


# ─── Роутер ───────────────────────────────────────────────────────────────────

def build_ttt_router(container: "AppContainer") -> APIRouter:
    router   = APIRouter()
    currency = container.user_service.wallet_currency

    # ── HTML страница Mini App ─────────────────────────────────────────────

    @router.get("/ttt/{game_id}", include_in_schema=False)
    async def ttt_page(game_id: str) -> RedirectResponse:
      return RedirectResponse(url=f"/mini/ttt/?game_id={game_id}", status_code=307)

    # ── Состояние игры ────────────────────────────────────────────────────

    @router.get("/api/ttt/{game_id}")
    async def get_ttt_state(game_id: str) -> dict:
        game = get_game(game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Игра не найдена")
        return _game_state(game, currency)

    # ── Ход через Mini App ────────────────────────────────────────────────

    @router.post("/api/ttt/{game_id}/move")
    async def post_ttt_move(game_id: str, body: MoveBody, request: Request) -> dict:
        # Валидируем Telegram initData
        raw_init = request.headers.get("X-Telegram-Init-Data", "")
        user_data = _validate_init_data(raw_init, container.settings.ceer_bot_token)
        if user_data is None:
            raise HTTPException(status_code=403, detail="Недействительный initData")

        player_id = int(user_data.get("id", 0))
        if player_id == 0:
            raise HTTPException(status_code=403, detail="Нет данных пользователя")

        game = get_game(game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Игра не найдена")

        if body.cell < 0 or body.cell > 8:
            raise HTTPException(status_code=400, detail="Недопустимый номер клетки")

        if not make_move(game, body.cell, player_id):
            raise HTTPException(status_code=400, detail="Недопустимый ход")

        winner_symbol = check_winner(game.board)
        draw          = is_draw(game.board)

        if winner_symbol or draw:
            finish_game(game, winner_symbol)
            new_balance = Decimal("0")

            if winner_symbol and game.bet > 0:
                winner_id = game.winner_id
                loser_id  = game.player_o_id if winner_id == game.player_x_id else game.player_x_id
                try:
                    await container.user_service.debit(loser_id, game.bet, "ttt_loss")
                    await container.user_service.credit(winner_id, game.bet * 2, "ttt_win")
                    winner_profile = await container.user_service.get_profile(winner_id)
                    new_balance = winner_profile.balance if winner_profile else Decimal("0")
                except InsufficientBalanceError:
                    logger.warning("Нет средств для расчёта TTT via Mini App, game_id=%s", game_id)

            # Обновляем сообщение в чате
            if container.bot:
                winner_name = None
                if game.winner_id:
                    winner_name = (
                        game.player_x_name if game.winner_id == game.player_x_id
                        else game.player_o_name
                    )
                result_text = (
                    TTT_TEXT.win(winner_name, game.bet, currency, new_balance)
                    if winner_name else TTT_TEXT.DRAW
                )
                try:
                    await container.bot.edit_message_text(
                        chat_id=game.chat_id,
                        message_id=game.message_id,
                        text=result_text,
                        reply_markup=build_ttt_board(game.board, game.game_id, finished=True),
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    logger.warning("Не удалось обновить сообщение чата после хода Mini App: %s", exc)
        else:
            next_turn(game)
            # Обновляем сообщение в чате (ход игрока)
            if container.bot:
                turn_name = (
                    game.player_x_name if game.current_turn_id == game.player_x_id
                    else game.player_o_name
                )
                board_text = TTT_TEXT.board(
                    game_x=game.player_x_name,
                    game_o=game.player_o_name or "",
                    turn_name=turn_name,
                    bet=game.bet,
                    currency=currency,
                )
                try:
                    await container.bot.edit_message_text(
                        chat_id=game.chat_id,
                        message_id=game.message_id,
                        text=board_text,
                        reply_markup=build_ttt_board(game.board, game.game_id, finished=False),
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    logger.warning("Не удалось обновить сообщение чата: %s", exc)

        return _game_state(game, currency)

    return router
