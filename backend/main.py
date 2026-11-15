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


@app.post('/api/predict')
def predict_input(body: PredictionInput):
    try:
        return prediction.predict(body.content, body.species, body.complete_profile)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (RuntimeError, ImportError, OSError) as exc:
        raise HTTPException(503, str(exc)) from exc


dist=dashboard.ROOT/'frontend/dist'
if dist.exists():
    app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
