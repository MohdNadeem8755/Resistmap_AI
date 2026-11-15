import React, { useEffect, useRef, useState } from 'react';
import { Mic, Square, Upload, X, LoaderCircle } from 'lucide-react';
import { api, useUI } from './context';

export default function VoiceInput({ onTranscript, onBusy, disabled }) {
  const { t, lang } = useUI();
  const [phase, setPhase] = useState('idle'), [seconds, setSeconds] = useState(0), [notice, setNotice] = useState('');
  const recorder = useRef(null), stream = useRef(null), timer = useRef(null), request = useRef(null);
  const alive = useRef(true), version = useRef(0), fileInput = useRef(null), levelNode = useRef(null), audioContext = useRef(null), animation = useRef(null);
  const state = useRef('idle');
  function transition(next) { state.current = next; if (alive.current) setPhase(next); onBusy?.(next !== 'idle'); }
  function releaseMic() {
    clearInterval(timer.current); cancelAnimationFrame(animation.current);
    stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
    audioContext.current?.close().catch(() => {}); audioContext.current = null;
  }
  function cancel() {
    version.current++; request.current?.abort();
    if (recorder.current?.state === 'recording') { recorder.current.onstop = null; recorder.current.stop(); }
    releaseMic(); transition('idle'); setNotice(t('Recording cancelled.', 'Recording रद्द कर दी।'));
  }
  useEffect(() => { alive.current = true; return () => { alive.current = false; version.current++; request.current?.abort(); if (recorder.current?.state === 'recording') { recorder.current.onstop = null; recorder.current.stop(); } releaseMic(); onBusy?.(false); }; }, []);
  async function transcribe(blob, ticket, language) {
    if (!alive.current || ticket !== version.current) return;
    if (!blob.size || blob.size > 8 * 1024 * 1024) { transition('idle'); setNotice(t('Use an audio clip under 8 MB.', '8 MB से छोटी audio clip चुनें।')); return; }
    transition('transcribing'); setNotice(t('Transcribing on this computer… First use may take a moment.', 'इसी computer पर आवाज़ को text में बदल रहे हैं… पहली बार थोड़ा समय लग सकता है।'));
    const controller = new AbortController(); request.current = controller;
    const deadline = setTimeout(() => controller.abort(), 120000);
    try {
      const response = await fetch(`/api/speech/transcribe?language=${language}`, { method: 'POST', credentials: 'same-origin', body: blob, headers: { 'Content-Type': blob.type || 'application/octet-stream' }, signal: controller.signal });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Transcription failed.');
      if (alive.current && ticket === version.current) { onTranscript(data.text); setNotice(t('Transcript added below. Review it, then press Send.', 'Transcript नीचे आ गया है। जाँचकर Send दबाएँ।')); }
    } catch (error) { if (alive.current && ticket === version.current) setNotice(error.name === 'AbortError' ? t('Transcription timed out. Try a shorter clip.', 'Transcription में समय लग रहा है। छोटी clip से कोशिश करें।') : error.message); }
    finally { clearTimeout(deadline); if (alive.current && ticket === version.current) transition('idle'); }
  }
  async function start() {
    if (state.current === 'recording') { recorder.current?.stop(); return; }
    if (state.current !== 'idle') return;
    window.speechSynthesis?.cancel();
    const ticket = ++version.current, language = lang;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { setNotice(t('This browser cannot record audio. Upload an audio clip below, or open this page in Chrome/Edge.', 'इस browser में recording उपलब्ध नहीं है। नीचे audio clip अपलोड करें या Chrome/Edge में यह page खोलें।')); return; }
    transition('permission'); setNotice(t('Allow microphone access in your browser to start recording.', 'Recording के लिए browser में microphone की अनुमति दें।'));
    try {
      const readiness = await api('/speech/status');
      if (!readiness.available) throw new Error(t('Local speech is not ready. Please run the speech setup.', 'Local speech तैयार नहीं है। Speech setup चलाएँ।'));
      if (ticket !== version.current || !alive.current) return;
      const mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
      if (ticket !== version.current || !alive.current) { mic.getTracks().forEach(track => track.stop()); return; }
      stream.current = mic;
      const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type));
      const rec = new MediaRecorder(mic, mimeType ? { mimeType } : undefined); recorder.current = rec;
      const chunks = [];
      rec.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      rec.onstop = () => { releaseMic(); transcribe(new Blob(chunks, { type: rec.mimeType }), ticket, language); };
      rec.onerror = () => { version.current++; rec.onstop = null; if (rec.state === 'recording') rec.stop(); releaseMic(); transition('idle'); setNotice(t('Recording failed. Try uploading an audio clip.', 'Recording नहीं हुई। Audio clip अपलोड करके कोशिश करें।')); };
      rec.start(250); setSeconds(0); transition('recording'); setNotice(t('Listening. Press Stop when you finish speaking.', 'सुन रहे हैं। बोलने के बाद Stop दबाएँ।'));
      const started = Date.now(); timer.current = setInterval(() => { const elapsed = Math.floor((Date.now() - started) / 1000); setSeconds(elapsed); if (elapsed >= 29 && rec.state === 'recording') rec.stop(); }, 250);
      try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (AudioContext) { const ctx = new AudioContext(); audioContext.current = ctx; const analyser = ctx.createAnalyser(); analyser.fftSize = 256; ctx.createMediaStreamSource(mic).connect(analyser); const values = new Uint8Array(256); const paint = () => { analyser.getByteTimeDomainData(values); const peak = Math.max(...values.map(v => Math.abs(v - 128))); if (levelNode.current) levelNode.current.style.width = `${Math.min(100, peak * 5)}%`; animation.current = requestAnimationFrame(paint); }; paint(); }
      } catch { /* Recording works even if a browser blocks audio metering. */ }
    } catch (error) {
      if (!alive.current || ticket !== version.current) return;
      releaseMic(); transition('idle');
      const messages = {
        NotAllowedError: t('Microphone is blocked. Allow it in browser/site permissions, then retry. In an embedded browser, use Chrome/Edge or upload audio below.', 'Microphone blocked है। Browser/site permissions में Allow करके फिर कोशिश करें। Embedded browser में Chrome/Edge खोलें या नीचे audio upload करें।'),
        NotFoundError: t('No microphone found. Connect one, or upload an audio clip.', 'Microphone नहीं मिला। उसे connect करें या audio clip अपलोड करें।'),
        NotReadableError: t('Microphone is busy or unavailable. Close other recording apps, then retry.', 'Microphone busy या उपलब्ध नहीं है। दूसरी recording app बंद करके फिर कोशिश करें।'),
      };
      setNotice(messages[error.name] || error.message);
    }
  }
  return <div className="voice-recorder">
    <div className="voice-recorder-actions"><button type="button" className={phase === 'recording' ? 'voice-record active' : 'voice-record'} onClick={start} disabled={disabled || phase === 'permission' || phase === 'transcribing'} aria-label={phase === 'recording' ? 'Stop recording' : 'Record voice'}>{phase === 'recording' ? <Square size={14} /> : phase === 'transcribing' || phase === 'permission' ? <LoaderCircle size={15} className="spinning" /> : <Mic size={15} />}{phase === 'recording' ? `${t('Stop', 'रोकें')} · ${seconds}s` : t('Record voice', 'आवाज़ रिकॉर्ड करें')}</button>
      <button type="button" className="voice-upload" onClick={() => fileInput.current?.click()} disabled={disabled || phase !== 'idle'}><Upload size={14} />{t('Upload audio', 'Audio अपलोड')}</button>
      {phase !== 'idle' && <button type="button" className="icon-button" onClick={cancel} aria-label="Cancel recording"><X size={15} /></button>}
      <input ref={fileInput} type="file" accept="audio/*,.webm,.m4a,.mp3,.wav,.ogg" hidden aria-label="Upload voice audio" onChange={e => { const file = e.target.files[0]; e.target.value = ''; if (file) transcribe(file, ++version.current, lang); }} />
    </div>
    {phase === 'recording' && <div className="mic-level" aria-label="Microphone sound level"><i ref={levelNode} /></div>}
    {notice && <p className="voice-notice" role="status">{notice}</p>}
    <small>{t('English / Hindi · up to 30 sec · audio is transcribed locally and not saved.', 'English / हिन्दी · अधिकतम 30 सेकंड · audio इसी computer पर transcribe होता है, save नहीं होता।')}</small>
  </div>;
}
