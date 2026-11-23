# M7 — Code Review Bot for Beginner Repos

This isolated service reviews changed GitHub files for hard-coded secrets, unsafe input use, missing error handling, and functions over 50 lines. Findings include the exact file and line. Clean pull requests return no findings, so the bot does not spam.

Run locally:

```powershell
uvicorn m7_code_review_bot.app:app --reload
```

Review files with `POST /review`:

```json
{"files": [{"path": "app.py", "content": "API_KEY = 'replace-me'"}]}
```

Set `GITHUB_WEBHOOK_SECRET` in production. A GitHub App can transform the returned findings into PR review comments using the installation token.
