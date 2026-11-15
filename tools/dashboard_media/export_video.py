from pathlib import Path
import subprocess
import imageio_ffmpeg

media=Path(r'D:\ResistMap-AI\frontend\public\media')
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(media/'resistmap-explainer.webm'),
                '-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-threads','2','-movflags','+faststart',
                str(media/'resistmap-explainer.mp4')],check=True)
subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(media/'resistmap-explainer.webm'),'-c','copy',
                str(media/'resistmap-explainer-indexed.webm')],check=True)
print('Exported seekable MP4 and WebM:',[(p.name,p.stat().st_size) for p in media.glob('resistmap-explainer*')])
