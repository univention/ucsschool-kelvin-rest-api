import datetime
import logging
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Dict

import jwt
import requests

AUTH_TOKEN_URL = "/ucsschool/kelvin/token"  # nosec

logger = logging.getLogger(__name__)


@dataclass
class AuthToken:
    token: str
    expiration_time: datetime.datetime

    @property
    def expired(self) -> bool:
        """Whether the token has expired."""
        return self.expiration_time - datetime.datetime.now() < datetime.timedelta(seconds=10)

    @classmethod
    def from_kelvin_response(cls, response_json: Dict[str, str]):
        return cls(
            token=f"{response_json['token_type']} {response_json['access_token']}",
            expiration_time=cls.extract_expiry(response_json["access_token"]),
        )

    @classmethod
    def extract_expiry(cls, access_token: str) -> datetime.datetime:
        """Get the time at which `token` expires."""
        actual_token = access_token.rsplit(" ", 1)[-1]
        payload = jwt.decode(actual_token, algorithm="HS256", options={"verify_signature": False})
        exp: str = payload.get("exp")
        ts = int(exp)
        return datetime.datetime.fromtimestamp(ts)


class TokenError(Exception):
    ...


def retrieve_token(host: str, username: str, password: str) -> AuthToken:
    url = f"https://{host}{AUTH_TOKEN_URL}"
    logger.info("Fetching access token for %r from %r...", username, url)
    headers = {"accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"username": username, "password": password}
    response = requests.post(url, data=data, headers=headers)
    try:
        response_json = response.json()
    except JSONDecodeError as exc:
        raise TokenError(
            f"Fetching token for {username!r}: response could not be decoded as JSON: "
            f"{exc!s}\nresponse.text: {response.text!r}"
        ) from exc
    try:
        return AuthToken.from_kelvin_response(response_json)
    except KeyError as exc:
        raise TokenError(
            f"Fetching token for {username!r}: response did not have expected content: "
            f"{response_json!r}"
        ) from exc
