from __future__ import annotations

import pytest

from cerber_bot.config import Settings


def test_core_first_billing_requires_core_credentials() -> None:
    with pytest.raises(ValueError, match="CERBER_CORE_API_KEY"):
        Settings(
            BOT_TOKEN="test-token",
            BILLING_MODE="core_first",
            CERBER_CORE_API_KEY="",
            CERBER_CORE_SECRET_KEY="",
        ).validate_billing_configuration()


def test_local_billing_skips_core_validation() -> None:
    Settings(
        BOT_TOKEN="test-token",
        BILLING_MODE="local",
        CERBER_CORE_API_KEY="",
    ).validate_billing_configuration()


def test_is_core_first_billing_property() -> None:
    settings = Settings(BOT_TOKEN="test-token", BILLING_MODE="core_first")
    assert settings.is_core_first_billing is True

    settings_local = Settings(BOT_TOKEN="test-token", BILLING_MODE="local")
    assert settings_local.is_core_first_billing is False
