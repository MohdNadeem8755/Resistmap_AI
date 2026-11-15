import React, { useState } from 'react';
import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail, UserRound, Moon, Sun, ArrowUpRight, ShieldCheck } from 'lucide-react';
import { Brand, GenomeArt } from './Brand';
import { api, useUI } from './context';

export default function Login({ onLogin }) {
  const { t, theme, setTheme, lang, setLang } = useUI();
  const [register, setRegister] = useState(false);
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('');
    const form = new FormData(e.currentTarget);
    try { const result = await api(`/auth/${register ? 'register' : 'login'}`, { method: 'POST', body: JSON.stringify({ name: form.get('name') || '', email: form.get('email'), password: form.get('password'), remember: form.get('remember') === 'on' }) }); onLogin(result.user); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <div className="login-page"><section className="login-story"><Brand large /><div className="login-story-copy"><span className="eyebrow light">{t('SEE THE SIGNAL IN EVERY SEQUENCE', 'हर SEQUENCE में छिपा संकेत देखें')}</span><h1>{t('Small sequences.', 'छोटी sequences.')}<br /><em>{t('Bigger insights.', 'बड़े insights.')}</em></h1><p>{t('A clearer view of antibiotic resistance. Connect genomic evidence, explore patterns, and follow every step of your research.', 'Antibiotic resistance को बेहतर समझें। Genomic evidence जोड़ें, patterns देखें और research की हर stage को track करें।')}</p></div><div className="login-art"><GenomeArt large /><div className="floating-stat one"><span className="live-dot" />{t('Evidence, connected.', 'Evidence, एक साथ।')}</div><div className="floating-stat two"><ShieldCheck size={19} /><span>{t('Built for careful science', 'विश्वसनीय research के लिए')}</span></div></div><div className="login-footer"><span>GENOMES → FEATURES → INSIGHTS</span><span>ResistMap AI <ArrowUpRight size={14} /></span></div></section>
    <section className="login-form-side"><div className="login-controls"><button className="text-button" onClick={() => setLang(lang === 'en' ? 'hi' : 'en')}>{lang === 'en' ? 'हिन्दी' : 'English'}</button><button className="icon-button" aria-label={t('Toggle theme', 'थीम बदलें')} onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}</button></div>
      <div className="login-form-wrap"><span className="mini-label">{t('YOUR RESEARCH WORKSPACE', 'आपका RESEARCH WORKSPACE')}</span><h2>{register ? t('Start your next discovery.', 'अपनी अगली खोज शुरू करें।') : t('Welcome back.', 'फिर से स्वागत है।')}</h2><p className="muted">{register ? t('Create an account for your local ResistMap workspace.', 'अपने local ResistMap workspace के लिए account बनाएँ।') : t('Sign in to see your research take shape.', 'अपनी research की प्रगति देखने के लिए sign in करें।')}</p>
        <form onSubmit={submit}>{register && <label className="field-label">{t('Full name', 'पूरा नाम')}<div className="input-icon"><UserRound size={18} /><input name="name" required maxLength={80} autoComplete="name" placeholder={t('Your name', 'आपका नाम')} /></div></label>}
          <label className="field-label">{t('Email address', 'ईमेल पता')}<div className="input-icon"><Mail size={18} /><input name="email" type="email" required maxLength={254} autoComplete="email" placeholder="you@research.org" /></div></label>
          <label className="field-label">{t('Password', 'पासवर्ड')}<div className="input-icon"><LockKeyhole size={18} /><input name="password" type={show ? 'text' : 'password'} required minLength={register ? 8 : 1} maxLength={256} autoComplete={register ? 'new-password' : 'current-password'} placeholder={register ? t('At least 8 characters', 'कम से कम 8 अक्षर') : t('Enter your password', 'अपना पासवर्ड लिखें')} /><button type="button" aria-label={show ? 'Hide password' : 'Show password'} onClick={() => setShow(!show)}>{show ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>
          <label className="small-check remember"><input type="checkbox" name="remember" />{t('Keep me signed in', 'मुझे signed in रखें')}</label>
          {error && <div className="error-note" role="alert">{error}</div>}
          <button className="button primary login-submit" disabled={busy}>{busy ? t('Opening workspace…', 'Workspace खुल रहा है…') : register ? t('Create account', 'Account बनाएँ') : t('Sign in to workspace', 'Workspace में sign in करें')}<ArrowRight size={18} /></button>
        </form><p className="signup-prompt">{register ? t('Already have an account?', 'Account पहले से है?') : t('New to ResistMap?', 'ResistMap पर नए हैं?')} <button className="text-button" onClick={() => { setRegister(!register); setError(''); }}>{register ? t('Sign in', 'Sign in करें') : t('Create an account', 'Account बनाएँ')}</button></p><div className="local-note"><span className="small-dot" />{t('Local workspace · Your account stays on this computer', 'Local workspace · आपका account इसी computer पर रहता है')}</div></div>
      <p className="login-bottom">{t('Research prototype. Built for exploration and expert review.', 'Research prototype. Exploration और expert review के लिए।')}</p>
    </section></div>;
}
