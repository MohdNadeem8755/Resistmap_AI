import io
import wave
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend import auth,speech
from backend.main import app,attempts

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(auth,'DB',tmp_path/'speech-test.sqlite3')
    attempts.clear()
    with TestClient(app) as c:
        assert c.get('/api/speech/status').status_code==401
        assert c.post('/api/speech/transcribe',content=b'audio').status_code==401
        c.post('/api/auth/register',json={'name':'Test','email':'input-test@example.invalid','password':'temporary-test-password'})
        yield c

def wav(seconds,silent=False):
    buffer=io.BytesIO()
    values=np.zeros(int(seconds*16000),dtype=np.int16) if silent else (np.sin(np.arange(int(seconds*16000))*.1)*1000).astype(np.int16)
    with wave.open(buffer,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(values.tobytes())
    return buffer.getvalue()

def test_speech_limits_and_errors(client):
    assert client.get('/api/speech/status').json()['available']
    assert client.post('/api/speech/transcribe?language=fr',content=b'a').status_code==422
    assert client.post('/api/speech/transcribe',content=b'x'*(speech.MAX_BYTES+1)).status_code==413
    for content in (b'invalid file',wav(.1),wav(1,True),wav(31)):
        response=client.post('/api/speech/transcribe?language=en',content=content)
        assert response.status_code==422,response.text

def test_real_speech_clip(client):
    clip=Path(__file__).resolve().parents[1]/'reports/ui_revision/speech-test.wav'
    r=client.post('/api/speech/transcribe?language=en',content=clip.read_bytes(),headers={'content-type':'audio/wav'})
    assert r.status_code==200,r.text
    body=r.json()
    assert 'current progress' in body['text'].lower()
    assert body['language']=='en' and body['audio_saved'] is False

def test_hindi_request_routes_to_model(client,monkeypatch):
    received=[]
    def fake_transcription(content,language):
        received.append((content,language))
        return {'text':'अभी कितना काम पूरा हुआ?','language':language,'audio_saved':False}
    monkeypatch.setattr(speech,'transcribe',fake_transcription)
    r=client.post('/api/speech/transcribe?language=hi',content=b'test-audio')
    assert r.json()['text']=='अभी कितना काम पूरा हुआ?'
    assert received==[(b'test-audio','hi')]

def test_own_input_and_csv_safety(client):
    good='BioSample\tAMR genotypes\n"MY_SAMPLE_01"\t"blaSHV-11=COMPLETE, gyrA_S83I=POINT"\n'
    r=client.post('/api/validate-input',json={'content':good})
    assert r.status_code==200 and r.json()['preview'][0]['features']==2
    assert r.json()['prediction_run'] is False
    malformed='BioSample,AMR genotypes\nMY_SAMPLE,blaSHV-11=COMPLETE,gyrA_S83I=POINT\n'
    assert client.post('/api/validate-input',json={'content':malformed}).status_code==422
    duplicate='BioSample,AMR genotypes,AMR genotypes\na,bla=COMPLETE,bla=COMPLETE\n'
    assert client.post('/api/validate-input',json={'content':duplicate}).status_code==422
