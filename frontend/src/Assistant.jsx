import React, { useEffect, useRef, useState } from 'react';
import { X, Send, Volume2, VolumeX, Sparkles, ArrowUpRight } from 'lucide-react';
import { api, useUI } from './context';
import { BrandMark } from './Brand';
import VoiceInput from './VoiceInput';
import HostedVoiceInput from './HostedVoiceInput';
const AssistantInput = import.meta.env.VITE_RENDER_PUBLIC === '1' ? HostedVoiceInput : VoiceInput;

export default function Assistant({ open, setOpen, navigate }) {
  const { t, lang, setLang, setTheme, voice, setVoice } = useUI();
  const [messages, setMessages] = useState([]), [input, setInput] = useState('');
  const [busy, setBusy] = useState(false), [voiceBusy, setVoiceBusy] = useState(false), [notice, setNotice] = useState('');
  const bottom = useRef(null);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [messages, busy]);
  useEffect(() => () => window.speechSynthesis?.cancel(), []);
  useEffect(() => { if (!open) window.speechSynthesis?.cancel(); }, [open]);
  function speak(text) {
    if (!('speechSynthesis' in window)) { setNotice(t('Speech playback is unavailable in this browser.', 'इस browser में आवाज़ उपलब्ध नहीं है।')); return; }
    window.speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang === 'hi' ? 'hi-IN' : 'en-IN'; utterance.rate = .97;
    const chosen = window.speechSynthesis.getVoices().find(v => v.lang.startsWith(lang));
    if (chosen) utterance.voice = chosen;
    utterance.onerror = event => { if (!['canceled', 'interrupted'].includes(event.error)) setNotice(t('Speech playback failed. The answer is available as text.', 'आवाज़ नहीं चल सकी। जवाब text में उपलब्ध है।')); };
    window.speechSynthesis.speak(utterance);
  }
  function command(text) {
    const q = text.toLowerCase();
    if (/dark (mode|theme)|डार्क/.test(q)) { setTheme('dark'); return t('Dark theme is on.', 'Dark theme चालू है।'); }
    if (/light (mode|theme)|white theme|लाइट थीम/.test(q)) { setTheme('light'); return t('Light theme is on.', 'Light theme चालू है।'); }
    if (/switch to hindi|हिंदी में|हिन्दी में/.test(q)) { setLang('hi'); return 'हिन्दी चुनी गई है।'; }
    if (/switch to english|अंग्रेजी में|अंग्रेज़ी में/.test(q)) { setLang('en'); return 'English is selected.'; }
    const destinations = [['overview', /open (overview|dashboard)|डैशबोर्ड खोल/], ['genomes', /open genomes|जीनोम खोल/], ['explore', /open (charts|explore)|चार्ट खोल/], ['models', /open model|मॉडल खोल/], ['workflow', /open (workflow|video)|वीडियो खोल/], ['settings', /open settings|सेटिंग खोल/], ['input', /open (input|upload)|add (my )?(sample|input)|इनपुट खोल/]];
    const match = destinations.find(([, pattern]) => pattern.test(q));
    if (match) { navigate(match[0]); return t(`Opened ${match[0]}.`, `${match[0]} खोल दिया है।`); }
    return null;
  }
  async function send(text = input) {
    const value = text.trim(); if (!value || busy || voiceBusy) return;
    setInput(''); setNotice(''); setMessages(m => [...m, { role: 'user', text: value }]); setBusy(true);
    try {
      const action = command(value);
      const result = action ? { answer: action, source: t('Workspace action', 'Workspace action') } : await api('/chat', { method: 'POST', body: JSON.stringify({ message: value, language: lang }) });
      setMessages(m => [...m, { role: 'assistant', text: result.answer, source: result.source }]);
      if (voice) speak(result.answer);
    } catch (err) { setMessages(m => [...m, { role: 'assistant', text: err.message, error: true }]); }
    finally { setBusy(false); }
  }
  if (!open) return <button className="assistant-fab" onClick={() => setOpen(true)} aria-label={t('Open assistant', 'Assistant खोलें')}><Sparkles size={20} /><span>{t('Ask ResistMap', 'ResistMap से पूछें')}</span></button>;
  return <aside className="assistant-panel" aria-label="Workspace assistant">
    <header><BrandMark size={33} /><div><strong>ResistMap assistant</strong><small><span className="live-dot" />{t('Your project, in context', 'आपके प्रोजेक्ट की जानकारी')}</small></div><button className="icon-button" onClick={() => setOpen(false)} aria-label="Close assistant"><X size={19} /></button></header>
    <div className="chat-content"><div className="chat-welcome"><div className="assistant-orb"><Sparkles size={27} /></div><h3>{t('Make sense of your research.', 'अपनी research को समझें।')}</h3><p>{t('Type a question or record your voice. Answers use saved project results and a local guide.', 'सवाल लिखें या अपनी आवाज़ रिकॉर्ड करें। जवाब saved project results और local guide से मिलते हैं।')}</p></div>
      {messages.length === 0 && <div className="chat-suggestions">{[t('What is the current progress?', 'अभी कितना काम पूरा हुआ?'), t('Explain the accuracy scores', 'Accuracy scores समझाओ'), t('Open input workspace', 'इनपुट खोलो')].map(q => <button onClick={() => send(q)} disabled={voiceBusy || busy} key={q}>{q}<ArrowUpRight size={14} /></button>)}</div>}
      {messages.map((m, i) => <div className={`chat-message ${m.role} ${m.error ? 'error' : ''}`} key={i}><p>{m.text}</p>{m.source && <div className="chat-source"><span>{m.source}</span><button className="icon-button" aria-label="Read answer aloud" disabled={voiceBusy} onClick={() => speak(m.text)}><Volume2 size={14} /></button></div>}</div>)}{busy && <div className="typing"><i /><i /><i /></div>}<div ref={bottom} />
    </div>
    <footer><div className="voice-controls"><button className={voice ? 'active' : ''} onClick={() => { setVoice(!voice); window.speechSynthesis?.cancel(); }}>{voice ? <Volume2 size={14} /> : <VolumeX size={14} />}{t('Read replies aloud', 'जवाब बोलकर सुनाएँ')}</button><span>{lang === 'hi' ? 'हिन्दी' : 'English'}</span></div>
      {notice && <p className="voice-notice" role="status">{notice}</p>}
      <form className="chat-input" onSubmit={e => { e.preventDefault(); send(); }}><textarea rows={2} aria-label={t('Ask a question', 'सवाल पूछें')} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }} maxLength={1500} placeholder={t('Type your question here…', 'अपना सवाल यहाँ लिखें…')} /><button className="send-button" disabled={!input.trim() || busy || voiceBusy} aria-label="Send message"><Send size={17} /></button></form>
      <AssistantInput onTranscript={text => setInput(previous => `${previous.trim()}${previous.trim() ? ' ' : ''}${text}`.slice(0, 1500))} onBusy={setVoiceBusy} disabled={busy} />
    </footer>
  </aside>;
}
