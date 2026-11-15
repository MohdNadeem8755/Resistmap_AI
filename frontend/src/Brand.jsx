import React from 'react';

export function BrandMark({ size = 36, className = '' }) {
  return <svg width={size} height={size} viewBox="0 0 64 64" className={`brand-mark ${className}`} role="img" aria-label="ResistMap DNA and protein fold logo">
    <path d="M32 3 57 17v30L32 61 7 47V17Z" fill="currentColor" opacity=".09" />
    <path d="M32 3 57 17v30L32 61 7 47V17Z" stroke="currentColor" strokeWidth="1.4" opacity=".35" fill="none" />
    <g fill="none" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12C48 12 48 25 32 32S16 52 42 52" stroke="currentColor" strokeWidth="4" /><path className="logo-protein" d="M42 12C16 12 16 25 32 32S48 52 22 52" stroke="#dfa179" strokeWidth="3.4" /><path d="M24 17h16M25 24h14M25 40h14M24 47h16" stroke="currentColor" strokeWidth="2.1" opacity=".7" /></g>
    <g className="logo-orbit"><circle className="molecule-node" cx="32" cy="3" r="3.2" fill="currentColor" /><circle className="molecule-node second" cx="57" cy="47" r="3.2" fill="#dfa179" /><circle cx="7" cy="47" r="2.6" fill="currentColor" /></g>
    <circle cx="32" cy="32" r="3" fill="var(--card,white)" /><circle cx="32" cy="32" r="1.5" fill="currentColor" />
  </svg>;
}

export function Brand({ large = false }) {
  return <div className={`brand ${large ? 'large' : ''}`}><BrandMark size={large ? 43 : 35} /><span>ResistMap<span className="brand-ai">AI</span><small>GENOMIC INTELLIGENCE</small></span></div>;
}

export function GenomeArt({ large = false }) {
  const rungs = Array.from({ length: 22 }, (_, i) => {
    const y = 20 + i * 14, offset = Math.sin(i * .4) * 53;
    return <g className="helix-rung" key={i} style={{ animationDelay: `${i * -.18}s` }}>
      <line x1={140 - offset} y1={y} x2={140 + offset} y2={y} stroke={i % 3 === 0 ? '#ecb894' : '#65b49d'} strokeWidth="2" opacity=".6" />
      <circle cx={140 - offset} cy={y} r={i % 3 === 0 ? 4 : 3} fill="#dfedc5" /><circle cx={140 + offset} cy={y} r="3" fill="#69b7a1" />
    </g>;
  });
  return <svg className={`genome-art ${large ? 'genome-large' : ''}`} viewBox="0 0 330 350" fill="none" aria-hidden="true">
    <circle cx="160" cy="175" r="139" stroke="#81bca1" strokeDasharray="3 9" opacity=".25" className="orbit" />
    <ellipse cx="160" cy="175" rx="112" ry="139" stroke="#81bca1" opacity=".12" />
    <g transform="translate(21 9) rotate(-22 140 175)">{rungs}</g>
    <g className="art-tag"><rect x="223" y="68" width="80" height="30" rx="7" fill="#3c7669" /><text x="263" y="87" fill="#e0efdf" textAnchor="middle" fontSize="10" fontFamily="monospace">ATCG · 01</text></g>
    <g className="art-tag tag-two"><rect x="7" y="247" width="92" height="32" rx="7" fill="#316458" /><circle cx="23" cy="263" r="3" fill="#ecb894" /><text x="36" y="266" fill="#e0efdf" fontSize="10" fontFamily="monospace">gene signal</text></g>
  </svg>;
}
