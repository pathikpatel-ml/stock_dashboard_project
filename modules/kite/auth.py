import os

from kiteconnect import KiteConnect


def get_kite_client(api_key: str) -> KiteConnect:
    return KiteConnect(api_key=api_key)


def generate_login_url(api_key: str) -> str:
    kite = get_kite_client(api_key)
    return kite.login_url()


def exchange_request_token(api_key: str, request_token: str, api_secret: str) -> str:
    kite = get_kite_client(api_key)
    session = kite.generate_session(request_token, api_secret=api_secret)
    return session["access_token"]


def build_authenticated_client(api_key_enc: str, access_token_enc: str) -> KiteConnect:
    from modules.auth.crypto import decrypt
    kite = get_kite_client(decrypt(api_key_enc))
    kite.set_access_token(decrypt(access_token_enc))
    return kite
