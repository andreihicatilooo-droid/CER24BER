import hashlib

from cerber_bot.integrations.nicepay import NicePayClient, NicePayRequestError


def test_nicepay_signature_verification_matches_documentation() -> None:
    params = {
        "amount": "5670",
        "amount_currency": "USD",
        "merchant_id": "merchant-1",
        "method": "paypal_usd",
        "order_id": "100423",
        "payment_id": "payment-1",
        "profit": "5370",
        "profit_currency": "USDT",
        "result": "success",
    }
    secret = "secret-1"
    digest = hashlib.sha256("{np}".join([params[key] for key in sorted(params)] + [secret]).encode("utf-8")).hexdigest()

    assert NicePayClient.verify_signature(parameters=params, provided_signature=digest, secret=secret)


def test_nicepay_parse_webhook_rejects_invalid_hash() -> None:
    client = NicePayClient(
        base_url="https://nicepay.io",
        http_client=None,
        merchant_id="merchant-1",
        secret="secret-1",
    )

    try:
        client.parse_webhook(
            {
                "result": "success",
                "payment_id": "payment-1",
                "merchant_id": "merchant-1",
                "order_id": "100423",
                "amount": "5670",
                "amount_currency": "USD",
                "hash": "invalid",
            }
        )
    except NicePayRequestError as error:
        assert str(error) == "Invalid hash"
    else:
        raise AssertionError("Expected NicePayRequestError for invalid hash")