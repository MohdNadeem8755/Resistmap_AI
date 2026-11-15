"""Download the multilingual speech model once; app transcription stays local."""
from pathlib import Path
import os
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING','1')
from huggingface_hub import snapshot_download

root=Path(os.environ.get('RESISTMAP_ROOT',Path(__file__).resolve().parent))
target=root/'models/speech/faster-whisper-base'
snapshot_download('Systran/faster-whisper-base',local_dir=target,
                  allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*','preprocessor_config.json'])
print('Local Hindi/English speech model ready:',target)
