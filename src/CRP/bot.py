"""Чат-бот CRP для управления репутацией в группах."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import ChatMemberUpdatedFilter, Command, IS_MEMBER, IS_NOT_MEMBER
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberUpdated, Message

from cerber_bot.container import AppContainer
from CRP.texts import CRP_TEXT


def build_crp_router(container: AppContainer) -> Router:
    router = Router(name="crp")

    @router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
    async def handle_added_to_chat(event: ChatMemberUpdated) -> None:
        try:
            chat_member = await event.bot.get_chat_member(event.chat.id, event.bot.id)  # type: ignore[union-attr]
            is_admin = chat_member.status in ("administrator", "creator")
            text = CRP_TEXT.WELCOME if is_admin else f"{CRP_TEXT.WELCOME}\n\n{CRP_TEXT.NO_RIGHTS}"
            await event.answer(text, parse_mode="HTML")
        except Exception:
            return

    @router.message(Command("crp"))
    async def handle_crp_command(message: Message, state: FSMContext) -> None:
        del state
        if message.chat.type not in {"group", "supergroup"}:
            await message.answer(CRP_TEXT.INVALID)
            return

        subcommand, args = _parse_crp_args(message)
        if not subcommand or subcommand in {"help", "?"}:
            await message.answer(CRP_TEXT.HELP)
            return

        if subcommand == "me":
            if message.from_user is None:
                await message.answer(CRP_TEXT.INVALID)
                return
            await container.user_service.register_or_update(message.from_user)
            await message.answer(await _format_profile_line(container, message.from_user.id))
            return

        if subcommand in {"+1", "-1"}:
            if message.from_user is None or not await _is_chat_admin(message, message.from_user.id):
                await message.answer(CRP_TEXT.ONLY_ADMIN)
                return
            if message.reply_to_message is None or message.reply_to_message.from_user is None:
                await message.answer(CRP_TEXT.NEED_REPLY)
                return
            target = message.reply_to_message.from_user
            if target.id == message.from_user.id:
                await message.answer(CRP_TEXT.SELF)
                return
            await container.user_service.register_or_update(target)
            updated = await container.reputation_service.adjust_reputation(target.id, 1 if subcommand == "+1" else -1)
            display = _display_name(target)
            await message.answer(CRP_TEXT.UPDATED.format(name=display, score=updated.score))
            return

        if subcommand == "отзыв":
            await _handle_review_command(container, message, args)
            return

        if subcommand == "отзывы":
            await _handle_reviews_command(container, message)
            return

        if subcommand == "ник":
            await _handle_nickname_command(container, message, args)
            return

        await message.answer(CRP_TEXT.INVALID)

    return router


def _parse_crp_args(message: Message) -> tuple[str, str]:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) == 1:
        return ("", "")
    subcommand = parts[1].strip().lower()
    rest = parts[2].strip() if len(parts) > 2 else ""
    return (subcommand, rest)


async def _handle_review_command(container: AppContainer, message: Message, args: str) -> None:
    if message.from_user is None:
        await message.answer(CRP_TEXT.INVALID)
        return
    if message.reply_to_message is None or message.reply_to_message.from_user is None:
        await message.answer(CRP_TEXT.NEED_REPLY_REVIEW)
        return

    target = message.reply_to_message.from_user
    if target.id == message.from_user.id:
        await message.answer(CRP_TEXT.REVIEW_SELF)
        return

    score_str = args.split(maxsplit=1)[0] if args else ""
    try:
        score = int(score_str)
    except ValueError:
        await message.answer(CRP_TEXT.REVIEW_INVALID_SCORE)
        return

    comment = args.split(maxsplit=1)[1] if len(args.split(maxsplit=1)) > 1 else None

    await container.user_service.register_or_update(target)
    try:
        await container.reputation_service.add_review(
            rater_telegram_id=message.from_user.id,
            rated_telegram_id=target.id,
            score=score,
            comment=comment,
        )
    except Exception as error:
        await message.answer(str(error))
        return

    display = _display_name(target)
    await message.answer(CRP_TEXT.REVIEW_ADDED.format(name=display, score=score))


async def _handle_reviews_command(container: AppContainer, message: Message) -> None:
    if message.reply_to_message is None or message.reply_to_message.from_user is None:
        await message.answer(CRP_TEXT.NEED_REPLY_REVIEW)
        return

    target = message.reply_to_message.from_user
    await container.user_service.register_or_update(target)
    reviews = await container.reputation_service.get_reviews_for_user(target.id, limit=20)
    display = _display_name(target)
    if not reviews:
        await message.answer(CRP_TEXT.REVIEWS_EMPTY.format(name=display))
        return

    lines = [CRP_TEXT.REVIEWS_HEADER.format(name=display)]
    for review in reviews:
        rater_name = await container.reputation_service.get_display_name(review.rater_telegram_id)
        if review.comment:
            lines.append(CRP_TEXT.REVIEW_LINE.format(score=review.score, rater=rater_name, comment=review.comment))
        else:
            lines.append(CRP_TEXT.REVIEW_LINE_NO_COMMENT.format(score=review.score, rater=rater_name))
    await message.answer("".join(lines).strip())


async def _handle_nickname_command(container: AppContainer, message: Message, args: str) -> None:
    if message.from_user is None:
        await message.answer(CRP_TEXT.INVALID)
        return
    if not args:
        await message.answer(CRP_TEXT.NICKNAME_EMPTY)
        return

    await container.user_service.register_or_update(message.from_user)
    try:
        await container.reputation_service.set_nickname(message.from_user.id, args)
    except Exception as error:
        await message.answer(str(error))
        return

    display = await container.reputation_service.get_display_name(message.from_user.id)
    await message.answer(CRP_TEXT.NICKNAME_SET.format(name=display))


async def _is_chat_admin(message: Message, user_id: int) -> bool:
    if message.bot is None:
        return False
    member = await message.bot.get_chat_member(message.chat.id, user_id)
    return member.status in {"administrator", "creator"}


async def _format_profile_line(container: AppContainer, telegram_id: int) -> str:
    profile = await container.user_service.get_profile(telegram_id)
    reputation = await container.reputation_service.get_user_reputation(telegram_id)
    if profile is None:
        return CRP_TEXT.USER_NOT_FOUND
    name = _display_name(profile)
    return CRP_TEXT.PROFILE_LINE.format(name=name, score=reputation.score, disputes=reputation.dispute_losses)


def _display_name(user) -> str:
    nickname = getattr(user, "nickname", None)
    if nickname:
        return nickname
    username = getattr(user, "username", None)
    if username:
        return f"@{username}"
    first_name = getattr(user, "first_name", None)
    if first_name:
        return str(first_name)
    return str(getattr(user, "telegram_id", getattr(user, "id", "unknown")))
