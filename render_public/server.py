"""Public, read-only presentation service. Serves precomputed results only."""
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from hosted_auth import router, enabled, cookie, call, profile

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "saved"
app = FastAPI(docs_url=None, redoc_url=None)
app.include_router(router)
dashboard = json.loads((DATA / "dashboard.json").read_text(encoding="utf-8"))
guest = {"name": "Research guest", "email": "guest", "id": 0}


@app.get("/health")
def health():
    return {"status": "ok", "mode": "saved-results"}


@app.get("/")
def home(request: Request):
    if enabled or request.cookies.get("public_guest") == "1":
        return FileResponse(ROOT / "web/index.html")
    return HTMLResponse("""<!doctype html><meta name="viewport" content="width=device-width">
    <title>ResistMap AI</title><main style="max-width:38rem;margin:15vh auto;padding:2rem;font:18px system-ui">
    <h1>ResistMap AI</h1><p>Explore the research dashboard, saved sample results and quality reports.
    Password sign-in and email recovery are awaiting account-service setup. Guest access is available now.</p>
    <form method="post" action="/guest"><button style="padding:.8rem 1rem">Open dashboard as guest</button></form></main>""")


@app.post("/guest")
def enter():
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("public_guest", "1", httponly=True, samesite="lax")
    return response


@app.get("/api/auth/me")
def me(request: Request):
    token = request.cookies.get(cookie)
    if enabled and token:
        try:
            return {"user": profile(call("GET", "user", token=token)), "accounts": True}
        except HTTPException as exc:
            if exc.status_code != 400:
                raise
    return {"user": guest if request.cookies.get("public_guest") == "1" else None}


@app.post("/api/auth/logout")
def logout(request: Request):
    from fastapi.responses import JSONResponse
    response = JSONResponse({"ok": True})
    response.delete_cookie("public_guest")
    if enabled and request.cookies.get(cookie):
        try:
            call("POST", "logout", token=request.cookies[cookie])
        except HTTPException:
            pass
    response.delete_cookie(cookie)
    return response


@app.get("/api/dashboard")
@app.get("/api/export/snapshot")
def overview():
    return dashboard


@app.get("/api/explore")
def explore():
    return FileResponse(DATA / "explore.json", media_type="application/json")


@app.get("/api/reports/{key}")
def report(key: str):
    if key not in {r["id"] for r in dashboard["reports"] if r["available"]}:
        raise HTTPException(404, "Report unavailable")
    return FileResponse(DATA / (key + ".csv"), filename=key + ".csv")


@app.get("/api/sample-lookup")
def lookup(id: str, drug: str = ""):
    for species, rows in dashboard["species_examples"].items():
        for row in rows:
            if row["sample"].casefold() == id.strip().casefold() and (not drug or row["drug"].casefold() == drug.casefold()):
                return {**row, "found": True, "species": species, "status": row["observed"],
                        "drugs": [], "explanation": "Saved research example. Independent validation pending."}
    return {"found": False, "sample": id, "status": "Unavailable", "explanation": "No matching saved example."}


class Question(BaseModel):
    message: str = Field(min_length=1, max_length=1500)
    language: str = "en"


@app.post("/api/chat")
def chat(question: Question):
    q = question.message.casefold()
    hi = question.language == "hi"
    cohort = dashboard["cohort"]
    if any(k in q for k in ("accuracy", "score", "सटीक", "स्कोर")):
        metrics = dashboard["model"]["metrics"]
        value = f"{metrics['accuracy']:.1%}"
        answer = (f"K. pneumoniae V2 की development accuracy {value} है। स्वतंत्र मूल्यांकन बाकी है।" if hi else
                  f"K. pneumoniae V2 development accuracy was {value}. Independent validation is pending.")
    elif any(k in q for k in ("progress", "sample", "cohort", "status", "data", "kitna", "कितना", "पूरा", "नमूने", "डेटा")):
        total, projects = cohort["total"], cohort["projects"]
        answer = (f"सहेजे गए development cohort में {projects} प्रोजेक्ट के {total} नमूने हैं।" if hi else
                  f"The saved development cohort contains {total} samples from {projects} projects.")
    else:
        answer = ("आप cohort, progress या accuracy के बारे में पूछ सकते हैं। उदाहरण देखने के लिए Overview खोलें।" if hi else
                  "Ask about the cohort, progress or accuracy. Open Overview to inspect saved sample results.")
    return {"answer": answer, "source": "ResistMap · saved dashboard"}


@app.api_route("/api/{path:path}", methods=["GET", "POST"])
def unsupported(path: str):
    raise HTTPException(404, "Available only in the local research application.")


app.mount("/", StaticFiles(directory=ROOT / "web"), name="assets")
