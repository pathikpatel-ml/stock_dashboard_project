import logging
import os
import time

logger = logging.getLogger(__name__)

# Defaults to real API in production (no env var needed on Render).
# For local testing without a subscription set GROWW_MOCK_MODE=true in .env
MOCK_MODE = os.environ.get("GROWW_MOCK_MODE", "false").lower() == "true"


def is_mock_mode() -> bool:
    return MOCK_MODE


def get_access_token_totp(app_id: str, totp_secret: str) -> str:
    """Generate a fresh Groww access token using TOTP (fully automated, no user login)."""
    if MOCK_MODE:
        mock_token = f"MOCK_GROWW_TOKEN_{app_id[:6]}_{int(time.time())}"
        logger.info("[GROWW MOCK] Generated mock token: %s...", mock_token[:25])
        return mock_token
    import pyotp
    from growwapi import GrowwAPI
    totp_code = pyotp.TOTP(totp_secret).now()
    access_token = GrowwAPI.get_access_token(api_key=app_id, totp=totp_code)
    logger.info("Groww TOTP token refreshed for app_id=%s***", app_id[:6])
    return access_token


def build_authenticated_client(app_id_enc: str, access_token_enc: str):
    """Build an authenticated Groww client from encrypted credentials."""
    from modules.auth.crypto import decrypt
    app_id = decrypt(app_id_enc)
    access_token = decrypt(access_token_enc)
    if MOCK_MODE:
        return _MockGrowwClient(app_id)
    from growwapi import GrowwAPI
    return GrowwAPI(access_token=access_token)


def auto_refresh_token(app_id_enc: str, totp_secret_enc: str) -> str:
    """Decrypt credentials and auto-refresh the Groww access token via TOTP."""
    from modules.auth.crypto import decrypt
    return get_access_token_totp(decrypt(app_id_enc), decrypt(totp_secret_enc))


class _MockGrowwClient:
    """Mock Groww client — returns realistic fake data for UI testing."""

    def __init__(self, app_id: str):
        self._app_id = app_id
        logger.info("[GROWW MOCK] Client created for app_id=%s***", app_id[:6])

    def get_holdings(self) -> list:
        logger.info("[GROWW MOCK] get_holdings")
        return [
            {"tradingsymbol": "RELIANCE", "quantity": 10, "last_price": 2450.0},
            {"tradingsymbol": "TCS",      "quantity": 5,  "last_price": 3800.0},
            {"tradingsymbol": "INFY",     "quantity": 20, "last_price": 1550.0},
        ]

    def get_smart_orders(self) -> list:
        logger.info("[GROWW MOCK] get_smart_orders")
        return []

    def create_smart_order(self, **kwargs) -> dict:
        import random
        order_id = f"MOCK_SO_{random.randint(10000, 99999)}"
        logger.info("[GROWW MOCK] create_smart_order symbol=%s → id=%s",
                    kwargs.get("tradingsymbol"), order_id)
        return {"order_id": order_id, "status": "PLACED"}

    def cancel_smart_order(self, order_id: str) -> dict:
        logger.info("[GROWW MOCK] cancel_smart_order id=%s", order_id)
        return {"status": "CANCELLED"}
