import React, { useEffect, useRef, useState } from 'react';
import { Mic, Square } from 'lucide-react';
import { useUI } from './context';

export default function HostedVoiceInput({ onTranscript, onBusy, disabled }) {
  const { t, lang } = useUI();
  const active = useRef(null);
  const deadline = useRef(null);
  const [listening, setListening] = useState(false);
  const [notice, setNotice] = useState('');
  const Engine = window.SpeechRecognition || window.webkitSpeechRecognition;
  useEffect(() => () => {
    clearTimeout(deadline.current);
    const session = active.current;
    active.current = null;
    session?.abort();
    onBusy(false);
  }, []);
  function toggle() {
    if (active.current) { active.current.stop(); return; }
    const session = new Engine();
    active.current = session;
    session.lang = lang === 'hi' ? 'hi-IN' : 'en-IN';
    session.interimResults = false;
    setNotice('');
    let received = false;
    let failed = false;
    session.onresult = event => {
      if (active.current !== session) return;
      const text = Array.from(event.results).slice(event.resultIndex).filter(r => r.isFinal)
        .map(r => r[0].transcript).join(' ').trim();
      if (text) { received = true; onTranscript(text); setNotice(t('Review your question, then press Send.', 'सवाल जाँचकर भेजें।')); }
    };
    session.onerror = e => {
      if (active.current !== session) return;
      failed = true;
      setNotice(e.error === 'not-allowed' || e.error === 'service-not-allowed'
        ? t('Microphone permission was denied. Allow it in browser settings, or type your question.', 'माइक की अनुमति दें या सवाल लिखें।')
        : t('Voice recognition stopped. Try again or type your question.', 'आवाज़ पहचानना रुक गया। फिर कोशिश करें या सवाल लिखें।'));
    };
    const finish = () => {
      if (active.current !== session) return;
      clearTimeout(deadline.current); active.current = null; setListening(false); onBusy(false);
      if (!failed && !received) setNotice(t('No speech detected. Try again or type your question.', 'आवाज़ नहीं मिली। फिर कोशिश करें या सवाल लिखें।'));
    };
    session.onend = finish;
    try {
      window.speechSynthesis?.cancel(); session.start(); setListening(true); onBusy(true);
      deadline.current = setTimeout(() => session.stop(), 30000);
    } catch { finish(); setNotice(t('Could not start the microphone. You can type your question.', 'माइक शुरू नहीं हुआ। आप सवाल लिख सकते हैं।')); }
  }
  return <div className="voice-input"><button type="button" disabled={!Engine || disabled} onClick={toggle}>
    {listening ? <Square size={14}/> : <Mic size={14}/>} {listening ? t('Stop listening', 'सुनना रोकें') : t('Use microphone', 'माइक इस्तेमाल करें')}
  </button><p className="voice-notice" role="status">{notice || (!Engine
    ? t('This browser does not offer speech recognition. Type your question or try Chrome.', 'इस ब्राउज़र में आवाज़ की पहचान उपलब्ध नहीं है। सवाल लिखें या Chrome खोलें।')
    : t('Your browser may send audio to its speech provider. Only your submitted question goes to ResistMap.', 'ब्राउज़र ऑडियो अपने speech provider को भेज सकता है। ResistMap को केवल भेजा गया सवाल मिलता है।'))}</p></div>;
}
