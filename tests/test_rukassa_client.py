import httpx
import pytest

from cerber_bot.integrations.rukassa import RukassaClient, RukassaRequestError


@pytest.mark.asyncio
async def test_rukassa_create_payment_error_100_shows_credentials_hint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": 100, "message": "error shop_id or token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = RukassaClient(
            base_url="https://lk.rukassa.io/api/v1",
            http_client=http_client,
            shop_id=123,
            token="secret",
        )

        try:
            await client.create_payment(order_id="order-1", amount_rub="100.00")
        except RukassaRequestError as error:
            assert str(error) == (
                "Rukassa API ошибка 100: error shop_id or token. "
                "Проверьте корректность RUKASSA_SHOP_ID и RUKASSA_TOKEN: "
                "shop_id должен быть числом без лишних символов."
            )
        else:
            raise AssertionError("Expected RukassaRequestError for API error 100")


@pytest.mark.asyncio
async def test_rukassa_create_payment_error_300_shows_frozen_hint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "300", "message": "client is frozen"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = RukassaClient(
            base_url="https://lk.rukassa.io/api/v1",
            http_client=http_client,
            shop_id=123,
            token="secret",
        )

        try:
            await client.create_payment(order_id="order-2", amount_rub="100.00")
        except RukassaRequestError as error:
            assert str(error) == (
                "Rukassa API ошибка 300: client is frozen. "
                "Клиент Rukassa заморожен. Проверьте статус аккаунта "
                "и обратитесь в поддержку Rukassa."
            )
        else:
            raise AssertionError("Expected RukassaRequestError for API error 300")
<<<<<<< HEAD
import httpx
import pytest

from cerber_bot.integrations.rukassa import RukassaClient, RukassaRequestError


@pytest.mark.asyncio
async def test_rukassa_create_payment_error_100_shows_credentials_hint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": 100, "message": "error shop_id or token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = RukassaClient(
            base_url="https://lk.rukassa.io/api/v1",
            http_client=http_client,
            shop_id=123,
            token="secret",
        )

        try:
            await client.create_payment(order_id="order-1", amount_rub="100.00")
        except RukassaRequestError as error:
            assert str(error) == (
                "Rukassa API ошибка 100: error shop_id or token. "
                "Проверьте корректность RUKASSA_SHOP_ID и RUKASSA_TOKEN: "
                "shop_id должен быть числом без лишних символов."
            )
        else:
            raise AssertionError("Expected RukassaRequestError for API error 100")


@pytest.mark.asyncio
async def test_rukassa_create_payment_error_300_shows_frozen_hint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "300", "message": "client is frozen"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = RukassaClient(
            base_url="https://lk.rukassa.io/api/v1",
            http_client=http_client,
            shop_id=123,
            token="secret",
        )

        try:
            await client.create_payment(order_id="order-2", amount_rub="100.00")
        except RukassaRequestError as error:
            assert str(error) == (
                "Rukassa API ошибка 300: client is frozen. "
                "Клиент Rukassa заморожен. Проверьте статус аккаунта "
                "и обратитесь в поддержку Rukassa."
            )
        else:
            raise AssertionError("Expected RukassaRequestError for API error 300")
=======
>>>>>>> 900be0693be755d41112e7023befff1cdaa36ca3
