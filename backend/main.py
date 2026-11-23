"""ResistMap local research dashboard API; saved analysis outputs are read-only."""
from pathlib import Path
import csv
import io
import json
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from backend import dashboard
from backend import auth, assistant, speech, prediction
from starlette.concurrency import run_in_threadpool
import time
import threading

app=FastAPI(title='ResistMap AI',version='0.2.0')
attempts={}
attempt_lock=threading.Lock()


@app.middleware('http')
async def no_cache(request, call_next):
    path=request.url.path
    if request.method=='POST':
        origin=request.headers.get('origin')
        if origin and origin not in {'http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:8011','http://localhost:8011'}:
            return JSONResponse({'detail':'Request origin is not allowed.'},status_code=403)
    if path.startswith('/api/') and not path.startswith('/api/auth/'):
        if not auth.current(request.cookies.get(auth.COOKIE)):
            return JSONResponse({'detail':'Please sign in to your workspace.'},status_code=401)
    response=await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response


class Credentials(BaseModel):
    name:str=Field(default='',max_length=80)
    email:str=Field(max_length=254)
    password:str=Field(min_length=1,max_length=256)
    remember:bool=False


def grant(response,user,remember):
    token,seconds=auth.session(user['id'],remember)
    response.set_cookie(auth.COOKIE,token,httponly=True,samesite='strict',secure=False,
                        max_age=seconds if remember else None,path='/')
    return {'user':user}


def rate_limit(request,email):
    key=(request.client.host,email.lower())
    with attempt_lock:
        now=time.monotonic()
        recent=[t for t in attempts.get(key,[]) if now-t<300]
        if len(recent)>=10:
            raise HTTPException(429,'Too many attempts. Please wait five minutes.')
        attempts[key]=recent+[now]


@app.get('/api/auth/me')
def me(request:Request):
    return {'user':auth.current(request.cookies.get(auth.COOKIE))}


@app.post('/api/auth/register')
def register(body:Credentials,request:Request,response:Response):
    rate_limit(request,body.email)
    try:
        user=auth.register(body.name,body.email,body.password)
        return grant(response,user,body.remember)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@app.post('/api/auth/login')
def login(body:Credentials,request:Request,response:Response):
    rate_limit(request,body.email)
    try:
        return grant(response,auth.login(body.email,body.password),body.remember)
    except ValueError as exc:
        raise HTTPException(401,str(exc)) from exc


@app.post('/api/auth/logout')
def logout(request:Request,response:Response):
    auth.logout(request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE,path='/')
    return {'ok':True}


class ChatInput(BaseModel):
    message:str=Field(min_length=1,max_length=1500)
    language:str=Field(default='en',pattern='^(en|hi)$')


class ResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetPassword(BaseModel):
    token: str = Field(min_length=20, max_length=128)
    password: str = Field(min_length=8, max_length=256)


@app.post('/api/auth/forgot-password')
def forgot_password(body: ResetRequest, request: Request):
    rate_limit(request, 'reset-ip')
    try:
        auth.request_reset(body.email)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {'message': 'If this email has an account, a reset link will be sent. Check your inbox and spam folder.'}


@app.post('/api/auth/reset-password')
def reset_password(body: ResetPassword, request: Request):
    rate_limit(request, 'reset-ip')
    try:
        auth.reset_password(body.token, body.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'message': 'Password changed. Sign in with your new password.'}


@app.post('/api/chat')
def chat(body:ChatInput):
    return assistant.answer(body.message,body.language)


@app.get('/health')
def health():
    return {'status':'ok','stage':'dashboard','training_controls':False}


@app.get('/api/speech/status')
def speech_status():
    return speech.status()


@app.post('/api/speech/transcribe')
async def transcribe_audio(request:Request,language:str='en'):
    if language not in ('en','hi'):
        raise HTTPException(422,'Choose English or Hindi.')
    content=bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk)>speech.MAX_BYTES:
            raise HTTPException(413,'Audio must be smaller than 8 MB.')
        content.extend(chunk)
    try:
        return await run_in_threadpool(speech.transcribe,bytes(content),language)
    except BlockingIOError as exc:
        raise HTTPException(429,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503,str(exc)) from exc


@app.get('/api/dashboard')
def get_dashboard():
    try:
        return dashboard.snapshot()
    except (OSError,ValueError,KeyError) as exc:
        raise HTTPException(503,'Analysis files are temporarily unavailable. Please refresh.') from exc


@app.get('/api/explore')
def get_explore():
    return dashboard.explore()


@app.get('/api/reports/{report_id}')
def download_report(report_id:str):
    entry=dashboard.report_paths().get(report_id)
    if entry is None:
        raise HTTPException(404,'Unknown report')
    path=entry[2]
    if not path.is_file():
        raise HTTPException(409,'This report is still being prepared.')
    return FileResponse(path,filename=path.name,media_type='text/csv')


@app.get('/api/export/snapshot')
def export_snapshot():
    data=dashboard.snapshot()
    return Response(json.dumps(data,indent=2),media_type='application/json',
                    headers={'Content-Disposition':'attachment; filename="resistmap_workspace_snapshot.json"'})


@app.get('/api/template')
def template():
    return Response('BioSample\tAMR genotypes\nEXAMPLE_SAMPLE_01\tblaSHV-11=COMPLETE, gyrA_S83I=POINT\n',
                    media_type='text/tab-separated-values',headers={'Content-Disposition':'attachment; filename="resistmap_input_template.tsv"'})


class InputPreview(BaseModel):
    content:str=Field(max_length=5*1024*1024)


@app.post('/api/validate-input')
def validate_input(body:InputPreview):
    try:
        return dashboard.validate_input(body.content)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


class PredictionInput(InputPreview):
    species: str = Field(max_length=100)
    complete_profile: bool = False
    drug: str = None


@app.post('/api/predict')
def predict_input(body: PredictionInput):
    try:
        return prediction.predict(body.content, body.species, body.complete_profile, drug=body.drug)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (RuntimeError, ImportError, OSError) as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get('/api/unsupervised/{species}/projection.png')
def saved_projection(species: str):
    if species not in {'escherichia_coli', 'acinetobacter_baumannii', 'tuberculosis'}:
        raise HTTPException(404, 'Projection unavailable')
    path = dashboard.ROOT/'data/processed/multispecies'/species/'unsupervised_profiles/svd/svd_overview.png'
    if not path.is_file():
        raise HTTPException(404, 'Saved projection unavailable')
    return FileResponse(path, media_type='image/png')


@app.get('/api/tb/cluster_image')
def tb_cluster_image():
    path = dashboard.ROOT/'data/processed/multispecies/tuberculosis/unsupervised_profiles/clusters/cluster_overview.png'
    if not path.is_file():
        raise HTTPException(404, 'Cluster image unavailable')
    return FileResponse(path, media_type='image/png')


@app.get('/api/tb/projection_image')
def tb_projection_image():
    return saved_projection('tuberculosis')


class SampleLookupRequest(BaseModel):
    id: str = Field(min_length=1, max_length=150)
    species: str = None
    drug: str = None


@app.get('/api/sample-lookup')
def sample_lookup_get(id: str = '', species: str = None, drug: str = None):
    try:
        return dashboard.lookup_sample(id, species, drug)
    except dashboard.CohortLookupUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post('/api/sample-lookup')
def sample_lookup_post(body: SampleLookupRequest):
    return sample_lookup_get(body.id, body.species, body.drug)


dist=dashboard.ROOT/'frontend/dist'
if dist.exists():
    app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
