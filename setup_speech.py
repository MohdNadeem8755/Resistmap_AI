"""Download the multilingual speech model once; app transcription stays local."""
from pathlib import Path
import os
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING','1')
from importlib.util import find_spec
import subprocess
import sys

root=Path(os.environ.get('RESISTMAP_ROOT',Path(__file__).resolve().parent))
target=root/'models/speech/faster-whisper-base'
requirements = Path(__file__).with_name('requirements-ui.txt').read_text().splitlines()
packages = {'ctranslate2', 'tokenizers', 'transformers', 'imageio-ffmpeg', 'numpy'}
missing = [line for line in requirements if line.partition('==')[0] in packages
           and find_spec(line.partition('==')[0].replace('-', '_')) is None]
if missing:
    subprocess.run([sys.executable, '-m', 'pip', 'install', *missing], check=True)
if not all((target / name).is_file() for name in ('model.bin','config.json','tokenizer.json')):
    from huggingface_hub import snapshot_download
    snapshot_download('Systran/faster-whisper-base',local_dir=target,
                      allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*','preprocessor_config.json'])
import ctranslate2, tokenizers, imageio_ffmpeg
from transformers import WhisperFeatureExtractor
print('Local Hindi/English speech model ready:',target)
