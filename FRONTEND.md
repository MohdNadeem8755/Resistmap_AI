# ResistMap AI research dashboard

The frontend reads the project's saved analysis outputs. It does not start, stop, alter or retrain the genomic processing job.

## Open the dashboard

Double-click `D:\ResistMap-AI\start_dashboard.cmd`, or run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\ResistMap-AI\start_dashboard.ps1
```

Visit **http://127.0.0.1:8011** and choose **Create an account** on the animated login page. No default password or shared account is installed. Accounts are local to this computer. The server runs hidden and listens only on loopback; logs are under `reports/dashboard/`.

To use an existing Python environment with the dashboard dependencies installed, pass `-PythonPath D:\AncondaAPP\python.exe` to `start_dashboard.ps1`. The overview reads the saved TB feature report; feature construction and model training are separate statuses.

The production build and API use one local server. Port 8000 is left available to the user's other application. This is a local research application; internet deployment would require a separate deployment and authentication review.

## Included

- Animated molecular DNA/protein identity, animated login, responsive navigation and reduced-motion support.
- Light and dark themes, English and Hindi interface, saved browser preferences.
- Live processing overview, searchable/filterable 445-sample genome collection and details.
- Real gene-count/anomaly scatterplot, cluster pie chart, fold recall bars, location bars, gene-prevalence heatmap and historical confusion matrix.
- Interactive six-stage dataflow diagram and an original 60-second animated explainer, downloadable as MP4 and WebM, with English/Hindi captions. The video has no recorded narration.
- Bilingual project chatbot grounded in saved project data and a local guide. It answers progress, accuracy, quality and workflow questions. It can navigate pages and change theme/language. It is a bounded project guide, not a general-purpose LLM.
- Voice recording through MediaRecorder, with local multilingual Whisper transcription via CTranslate2. Choose English or Hindi, record up to 30 seconds, stop, review the editable transcript, then send. Audio-file upload (8 MB maximum) works when the embedded browser blocks microphone capture. Audio is decoded in memory with FFmpeg and is not persisted or sent to a cloud speech service. Spoken replies still use browser speech synthesis and installed voices.
- Add input opens manual sample entry, pasted CSV/TSV tables, and file upload. Enter your own sample IDs and gene/mutation calls, add multiple samples, check the input and download it. Inputs are not saved on the server. - Saved V2 model inference is available for confirmed complete **Klebsiella pneumoniae**, **Escherichia coli**, and **Acinetobacter baumannii** profiles; **Mycobacterium tuberculosis** only shows unsupervised results and the supervised endpoint remains closed (HTTP 503).

## Research scope

The 3,000-isolate exploratory cohort is separate from the 445-sample supervised development cohort. Scatter points are actual gene-count/anomaly pairs, not invented PCA coordinates. Heatmap cells show within-cluster gene prevalence; eight genes are selected by overall presence/absence variance.

V2 accuracy (90.37%) and balanced accuracy (83.66%) are development-CV selection scores. The historical V1 test contains 114 samples and is no longer an untouched test for future versions. Sequence expansion and fresh independent evaluation remain separate stages. No verified 99% accuracy is claimed. Anomaly flags are review signals; the dashboard does not recommend treatment.

## Development

```powershell
cd D:\ResistMap-AI
python -m venv .venv-ui
.\.venv-ui\Scripts\python.exe -m pip install -r requirements-ui.txt
cd frontend
pnpm install
pnpm build
cd ..
.\.venv-ui\Scripts\python.exe setup_speech.py
```

For hot reload, run the API with `.venv-ui\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8011` from the project root, then `pnpm dev` from `frontend`. Vite runs at http://127.0.0.1:5173 and proxies `/api` to port 8011.

`RESISTMAP_ROOT` overrides the analysis root. `RESISTMAP_AUTH_DB` overrides the local account database; default `data/app/accounts.sqlite3`. Passwords use salted PBKDF2 hashes. Sessions are opaque, stored hashed, expire after 12 hours or seven days when remembered, and are revoked on logout. Cookies are HttpOnly and SameSite=Strict for local HTTP use.

## Verification and source assets

API tests live in `tests/test_dashboard.py`. Install `pytest httpx` in `.venv-ui`, then run `.venv-ui\Scripts\python.exe -m pytest tests/test_dashboard.py -q` from the root. These tests use an isolated temporary account database.

Browser verification screenshots and results are under `reports/ui_qa/`. Desktop and 390px mobile layouts, authentication, filters, exports, input validation, chat, preferences and captioned video playback were checked. The revised voice flow was tested through a real Chromium MediaRecorder with a synthetic microphone WAV, the local transcription endpoint, and an editable transcript. Audio upload, permission-denied recovery, cancellation, malformed/silent/overlong audio and input byte limits were checked. English synthetic speech was recognized correctly; Hindi language routing was tested separately. Physical microphone acoustics and OS spoken-voice quality require testing on the user's device.

The original logo and video exports are under `frontend/public/media/`. Editable video source and generation scripts are under `tools/dashboard_media/`. The renderer uses the local bundled Playwright runtime and installed Chrome; adjust runtime paths on another machine. `render_video.cjs` creates WebM; `export_video.py` creates seekable MP4/WebM using imageio-ffmpeg.


## Voice and manual input update

1. Refresh the dashboard. Open **Ask ResistMap**.
2. Choose EN or हिन्दी in the top bar, then **Record voice**. Allow microphone access.
3. Press **Stop**, wait for the local transcript, correct any recognition errors and press **Send**.
4. If the embedded browser blocks the microphone, use **Upload audio** with a WAV/MP3/M4A/OGG/WebM clip, or open the same localhost address in Chrome/Edge.
5. Choose **Add input** in the page header for **Manual entry**, **Paste data**, or **Upload file**. Download your input before navigating away; drafts are not persisted.

The model files are downloaded once by `setup_speech.py` into `models/speech/faster-whisper-base/`. `RESISTMAP_SPEECH_MODEL` can override that directory. Inference loads these local files only. The decoder caps duration at 30 seconds and has a timeout; the model runs with two CPU threads and one transcription at a time. The Windows-blocked PyAV decoder is not used. No Windows security policy was changed.

Tests: `.venv-ui\Scripts\python.exe -m pytest tests/test_dashboard.py tests/test_input_speech.py -q` from the project root. The real-clip regression fixture is `reports/ui_revision/speech-test.wav`, generated using Windows TTS, not a user recording. Screenshots and browser checks are under `reports/ui_revision/`.

Implementation references: [CTranslate2 Whisper API](https://opennmt.net/CTranslate2/python/ctranslate2.models.Whisper.html), [Whisper feature extraction](https://huggingface.co/docs/transformers/model_doc/whisper), [browser microphone permissions](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).
