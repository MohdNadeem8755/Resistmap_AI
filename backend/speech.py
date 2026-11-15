"""Local Hindi/English Whisper inference with bounded FFmpeg audio decoding."""
from importlib.util import find_spec
import os
from pathlib import Path
import subprocess
import threading
from backend.dashboard import ROOT

MODEL_DIR=Path(os.environ.get('RESISTMAP_SPEECH_MODEL',ROOT/'models/speech/faster-whisper-base'))
MAX_BYTES=8*1024*1024
MAX_SECONDS=30
_model=None
_tokenizer=None
_extractor=None
_lock=threading.Lock()

def status():
    dependencies=('ctranslate2','tokenizers','transformers','imageio_ffmpeg','numpy')
    ready=all((MODEL_DIR/name).is_file() for name in ('model.bin','config.json','tokenizer.json')) and all(find_spec(name) is not None for name in dependencies)
    return {'available':ready,'engine':'local-whisper-base','languages':['en','hi'],
            'max_seconds':MAX_SECONDS,'max_bytes':MAX_BYTES,'audio_saved':False}

def decode_bounded(content):
    import imageio_ffmpeg
    import numpy as np
    command=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-nostdin',
             '-protocol_whitelist','pipe','-i','pipe:0','-t',str(MAX_SECONDS+.1),'-vn','-threads','1',
             '-ac','1','-ar','16000','-f','f32le','pipe:1']
    try:
        result=subprocess.run(command,input=content,capture_output=True,timeout=20,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except (subprocess.TimeoutExpired,OSError) as exc:
        raise ValueError('Audio could not be decoded. Try a shorter WAV, MP3 or WebM clip.') from exc
    if result.returncode or not result.stdout:
        raise ValueError('Cannot read this audio. Try a WAV, MP3, M4A, OGG or WebM clip.')
    audio=np.frombuffer(result.stdout,dtype='<f4').copy()
    if len(audio)>16000*MAX_SECONDS:
        raise ValueError('Keep audio clips under 30 seconds.')
    if len(audio)<4800:
        raise ValueError('The recording is too short. Speak for at least one second.')
    if not np.isfinite(audio).all() or float(np.sqrt(np.mean(audio**2)))<.00001:
        raise ValueError('No audible speech was detected. Check your microphone and try again.')
    return audio

def transcribe(content,language):
    global _model,_tokenizer,_extractor
    if language not in ('en','hi'):
        raise ValueError('Choose English or Hindi.')
    if not content or len(content)>MAX_BYTES:
        raise ValueError('Choose a non-empty audio clip smaller than 8 MB.')
    if not status()['available']:
        raise RuntimeError('The local speech model is not installed. Run setup_speech.py.')
    if not _lock.acquire(blocking=False):
        raise BlockingIOError('Another recording is being transcribed. Try again shortly.')
    try:
        import ctranslate2
        import numpy as np
        audio=decode_bounded(content)
        if _model is None:
            from tokenizers import Tokenizer
            from transformers import WhisperFeatureExtractor
            _tokenizer=Tokenizer.from_file(str(MODEL_DIR/'tokenizer.json'))
            _extractor=WhisperFeatureExtractor(feature_size=80,sampling_rate=16000,hop_length=160,n_fft=400,chunk_length=30)
            _model=ctranslate2.models.Whisper(str(MODEL_DIR),device='cpu',compute_type='int8',intra_threads=2,inter_threads=1)
        features=_extractor(audio,sampling_rate=16000,return_tensors='np').input_features
        mel=ctranslate2.StorageView.from_array(np.ascontiguousarray(features,dtype=np.float32))
        prompts=[_tokenizer.token_to_id(token) for token in ('<|startoftranscript|>',f'<|{language}|>','<|transcribe|>','<|notimestamps|>')]
        output=_model.generate(mel,[prompts],beam_size=3,max_length=160,return_no_speech_prob=True)[0]
        text=_tokenizer.decode(output.sequences_ids[0],skip_special_tokens=True).strip()
        if not text or output.no_speech_prob>.8:
            raise ValueError('No clear speech was detected. Speak closer to the microphone and try again.')
        return {'text':text[:1500],'language':language,'duration_seconds':round(len(audio)/16000,2),
                'engine':'local-whisper-base','audio_saved':False}
    finally:
        _lock.release()
