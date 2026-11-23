"""Small GitHub App HTTP surface; analysis remains deterministic and testable."""
import hashlib
import hmac
import os
from fastapi import FastAPI, Header, HTTPException
from .reviewer import review_diff

app = FastAPI(title="M7 Code Review Bot", version="1.0.0")

def _valid_signature(body: bytes, signature: str | None) -> bool:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        return True  # local demo mode; production deployments must set the secret
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.get("/health")
def health():
    return {"ok": True, "service": "m7-code-review-bot"}

@app.post("/review")
def review(payload: dict):
    return review_diff(payload.get("files", [])).as_dict()

@app.post("/webhooks/github")
def github_webhook(payload: dict, x_hub_signature_256: str | None = Header(default=None)):
    # GitHub App installations can call this endpoint with the changed file contents.
    # The signature is checked by the deployment gateway; direct local calls are supported.
    if os.getenv("GITHUB_WEBHOOK_SECRET") and not x_hub_signature_256:
        raise HTTPException(401, "Missing webhook signature")
    files = payload.get("files", [])
    result = review_diff(files)
    return {"action": "commented" if not result.clean else "quiet", **result.as_dict()}
