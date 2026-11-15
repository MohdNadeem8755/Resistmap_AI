import React, { createContext, useContext, useEffect, useState } from 'react';

const UIContext = createContext(null);
export function UIProvider({ children }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('rm-theme') || 'light');
  const [lang, setLang] = useState(() => localStorage.getItem('rm-language') || 'en');
  const [motion, setMotion] = useState(() => localStorage.getItem('rm-motion') || 'auto');
  const [voice, setVoice] = useState(() => localStorage.getItem('rm-voice') === 'true');
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('rm-theme', theme); }, [theme]);
  useEffect(() => { document.documentElement.lang = lang; localStorage.setItem('rm-language', lang); }, [lang]);
  useEffect(() => { document.documentElement.dataset.motion = motion; localStorage.setItem('rm-motion', motion); }, [motion]);
  useEffect(() => { localStorage.setItem('rm-voice', String(voice)); }, [voice]);
  const t = (en, hi) => lang === 'hi' ? (hi || en) : en;
  return <UIContext.Provider value={{ theme, setTheme, lang, setLang, motion, setMotion, voice, setVoice, t }}>{children}</UIContext.Provider>;
}
export const useUI = () => useContext(UIContext);
export const format = n => n == null ? '—' : new Intl.NumberFormat('en-IN').format(n);
export const pct = n => n == null ? '—' : `${(n * 100).toFixed(2)}%`;

export async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, { credentials: 'same-origin', ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Please check your input and try again.');
    error.status = response.status; throw error;
  }
  return data;
}
