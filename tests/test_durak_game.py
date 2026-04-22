from decimal import Decimal

from ceer_bot.games.durak import DurakGame, can_transfer, do_attack, do_transfer


def _build_game() -> DurakGame:
    return DurakGame(
        game_id="game-1",
        chat_id=1,
        message_id=1,
        creator_id=1,
        bet=Decimal("0"),
        player_ids=[1, 2, 3],
        player_names={1: "A", 2: "B", 3: "C"},
        trump="c",
        attacker_idx=0,
        defender_idx=1,
        phase="attacking",
        round_limit=6,
    )


def test_second_attacker_can_throw_same_rank_card() -> None:
    game = _build_game()
    game.hands = {
        1: ["6s", "9c"],
        2: ["7s", "8d"],
        3: ["6h", "Qc"],
    }

    assert do_attack(game, 1, "6s") is True
    assert game.phase == "defending"

    assert do_attack(game, 3, "6h") is True
    assert game.table == [("6s", None), ("6h", None)]
    assert "6h" not in game.hands[3]


def test_defender_can_transfer_attack_to_next_player() -> None:
    game = _build_game()
    game.hands = {
        1: ["6s", "9c"],
        2: ["6h", "8d"],
        3: ["7c", "9d", "Qs"],
    }

    assert do_attack(game, 1, "6s") is True
    assert can_transfer(game, "6h") is True

    assert do_transfer(game, "6h") is True
    assert game.attacker_idx == 1
    assert game.defender_idx == 2
    assert game.phase == "defending"
    assert game.round_limit == 3
    assert game.table == [("6s", None), ("6h", None)]
    assert "6h" not in game.hands[2]