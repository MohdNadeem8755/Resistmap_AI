"""Optional managed accounts for the public dashboard. Uses only a publishable key."""
import os
import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth")
url = os.getenv("SUPABASE_URL", "").rstrip("/")
key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
enabled = bool(url.startswith("https://") and key)
cookie = "rm_account"


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)
    name: str = Field(default="", max_length=80)


class Recovery(BaseModel):
    email: str = Field(max_length=254)


class Reset(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=8, max_length=256)


def call(method, endpoint, payload=None, token=None):
    if not enabled:
        raise HTTPException(503, "Hosted accounts are awaiting setup. Guest access is available.")
    headers = {"apikey": key}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        result = httpx.request(method, url + "/auth/v1/" + endpoint, headers=headers,
                               json=payload, timeout=10)
    except httpx.RequestError:
        raise HTTPException(503, "Account service is temporarily unavailable.")
    if result.status_code == 429:
        raise HTTPException(429, "Too many requests. Please try later.")
    if result.is_error:
        if result.status_code >= 500:
            raise HTTPException(503, "Account service unavailable. Please try later.")
        raise HTTPException(400, "Check the account details or request a fresh email link.")
    return result.json() if result.content else {}


def profile(user):
    return {"id": user["id"], "email": user["email"],
            "name": (user.get("user_metadata") or {}).get("name") or user["email"]}


def grant(result, response):
    if not result.get("access_token"):
        return {"user": None, "message": "Check your inbox to confirm your email, then sign in."}
    response.set_cookie(cookie, result["access_token"], max_age=int(result.get("expires_in", 3600)),
                        httponly=True, secure=True, samesite="strict")
    response.delete_cookie("public_guest")
    return {"user": profile(result["user"])}


@router.post("/register")
def register(body: Credentials, response: Response):
    if len(body.password) < 8:
        raise HTTPException(422, "Use at least 8 characters.")
    return grant(call("POST", "signup", {"email": body.email, "password": body.password,
                                         "data": {"name": body.name}}), response)


@router.post("/login")
def login(body: Credentials, response: Response):
    return grant(call("POST", "token?grant_type=password", {"email": body.email, "password": body.password}), response)


@router.post("/forgot-password")
def forgot(body: Recovery):
    call("POST", "recover", {"email": body.email})
    return {"message": "If this address has an account, check your inbox for a reset link."}


@router.post("/reset-password")
def reset(body: Reset):
    session = call("POST", "verify", {"type": "recovery", "token_hash": body.token})
    call("PUT", "user", {"password": body.password}, session["access_token"])
    call("POST", "logout", token=session["access_token"])
    return {"message": "Password changed. Sign in with your new password."}
