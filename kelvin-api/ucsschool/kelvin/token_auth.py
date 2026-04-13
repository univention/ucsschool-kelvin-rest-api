# -*- coding: utf-8 -*-

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import datetime, timedelta
from typing import Any

import aiofiles
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from pydantic import BaseModel

from ucsschool.lib.models.utils import ucr

from .constants import TOKEN_HASH_ALGORITHM, TOKEN_SIGN_SECRET_FILE, UCRV_TOKEN_TTL, URL_TOKEN_BASE
from .ldap import LdapUser, get_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=URL_TOKEN_BASE)
_secret_key = ""  # nosec


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str = None


async def get_secret_key() -> str:
    global _secret_key

    if not _secret_key:
        async with aiofiles.open(TOKEN_SIGN_SECRET_FILE, "r") as fp:
            key = await fp.read()
        _secret_key = key.strip()
    return _secret_key


def get_token_ttl() -> int:
    return int(ucr.get(UCRV_TOKEN_TTL, 60))


async def create_access_token(*, data: dict, expires_delta: timedelta = None) -> bytes:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=get_token_ttl())
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, await get_secret_key(), algorithm=TOKEN_HASH_ALGORITHM)
    return encoded_jwt


async def get_token(token: str = Depends(oauth2_scheme)) -> str:
    """
    This function serves as a Depends that returns the jwt provided in the Auth headers.

    If the tokens signature cannot be verified, an HTTPException is raised.

    :return: The jwt token as a string
    :raises HTTPException: If the token cannot be decoded or the signature cannot be verified.
    """
    try:
        jwt.decode(token, await get_secret_key(), algorithms=[TOKEN_HASH_ALGORITHM])
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_current_user(token: str = Depends(oauth2_scheme)) -> LdapUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, await get_secret_key(), algorithms=[TOKEN_HASH_ALGORITHM])
        sub: dict[str, Any] = payload.get("sub")
        username = sub.get("username", "")
        if not username:
            raise credentials_exception
        token_data = TokenData(username=username)
    except PyJWTError as exc:
        raise credentials_exception from exc
    user = get_user(username=token_data.username, school_only=False)
    user.kelvin_admin = sub.get("kelvin_admin", False)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: LdapUser = Depends(get_current_user),
) -> LdapUser:
    if current_user.disabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return current_user


async def get_kelvin_admin(user: LdapUser = Depends(get_current_active_user)) -> LdapUser:
    if not user.kelvin_admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return user
