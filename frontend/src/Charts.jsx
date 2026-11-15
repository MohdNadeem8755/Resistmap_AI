import React, { useState } from 'react';
import { useUI, format } from './context';

export const COLORS = ['#167966', '#e2a17d', '#91ada6', '#8792bb', '#a8bd70', '#cc8e97', '#58a6aa', '#bfad83'];

export function SourceDonut({ data, total, label }) {
  let offset = 0;
  return <div className="donut-layout"><div className="donut-wrap"><svg viewBox="0 0 180 180" role="img" aria-label={`${label}: ${data.map(d => `${d.name} ${d.value}`).join(', ')}`}>
    <circle cx="90" cy="90" r="65" fill="none" stroke="var(--line)" strokeWidth="20" />
    {data.map((d, i) => { const length = total ? d.value / total * 408.407 : 0; const start = offset; offset += length; return <circle key={d.name} cx="90" cy="90" r="65" fill="none" stroke={COLORS[i % COLORS.length]} strokeWidth="20" strokeDasharray={`${Math.max(0, length - 3)} ${408.407 - Math.max(0, length - 3)}`} strokeDashoffset={-start} transform="rotate(-90 90 90)"><title>{d.name}: {format(d.value)}</title></circle>; })}
    <text x="90" y="89" textAnchor="middle" className="donut-value">{format(total)}</text><text x="90" y="109" textAnchor="middle" className="chart-label">{label}</text>
  </svg></div><div className="donut-legend">{data.map((d, i) => <div key={d.name}><span className="legend-dot" style={{ background: COLORS[i % COLORS.length] }} /><span>{d.name}</span><strong>{format(d.value)}</strong></div>)}</div></div>;
}

export function FoldBars({ folds }) {
  const { t } = useUI();
  return <div className="fold-chart"><div className="legend"><span><i style={{ background: COLORS[0] }} />{t('Susceptible recall', 'Susceptible recall')}</span><span><i style={{ background: COLORS[1] }} />{t('Resistant recall', 'Resistant recall')}</span></div>
    <svg viewBox="0 0 560 232" role="img" aria-label="Susceptible and resistant recall by development fold">
      {[0, 25, 50, 75, 100].map(v => <g key={v}><line x1="43" y1={190 - v * 1.5} x2="546" y2={190 - v * 1.5} stroke="var(--line)" strokeDasharray="3 5" /><text x="32" y={194 - v * 1.5} textAnchor="end" className="chart-label">{v}</text></g>)}
      {folds.map((f, i) => <g key={f.fold}>{['S_recall', 'R_recall'].map((key, j) => <g key={key}><rect className="grow-bar" x={100 + i * 165 + j * 39} y={190 - (f[key] || 0) * 150} width="29" height={(f[key] || 0) * 150} rx="4" fill={COLORS[j]}><title>{key}: {(f[key] * 100).toFixed(2)}%</title></rect><text x={114 + i * 165 + j * 39} y={180 - (f[key] || 0) * 150} textAnchor="middle" className="bar-value">{(f[key] * 100).toFixed(1)}</text></g>)}<text x={134 + i * 165} y="217" textAnchor="middle" className="chart-label">{t('Fold', 'फ़ोल्ड')} {f.fold}</text></g>)}
    </svg></div>;
}

export function Scatter({ data, compact = false }) {
  const { t } = useUI();
  const [active, setActive] = useState(null);
  const [reviewOnly, setReviewOnly] = useState(false);
  const points = data?.points || [];
  const maxX = Math.max(10, ...points.map(p => p.x));
  const minY = Math.floor(Math.min(.4, ...points.map(p => p.y)) * 10) / 10;
  const maxY = Math.ceil(Math.max(.6, ...points.map(p => p.y)) * 10) / 10;
  const x = v => 55 + v / maxX * 485, y = v => 225 - (v - minY) / (maxY - minY) * 180;
  return <div className="scatter"><div className="chart-toolbar"><div className="legend"><span><i style={{ background: COLORS[0] }} />{t('Routine', 'सामान्य')}</span><span><i style={{ background: COLORS[1] }} />{t('Flagged for review', 'समीक्षा के लिए')}</span></div><label className="small-check"><input type="checkbox" checked={reviewOnly} onChange={e => setReviewOnly(e.target.checked)} />{t('Flagged only', 'केवल चिह्नित')}</label></div>
    <svg viewBox="0 0 575 275" role="img" aria-label="Scatterplot of complete gene count versus anomaly score">
      {Array.from({ length: 5 }, (_, i) => <g key={i}><line x1="55" y1={45 + i * 45} x2="540" y2={45 + i * 45} stroke="var(--line)" strokeDasharray="3 5" /><text x="43" y={49 + i * 45} textAnchor="end" className="chart-label">{(maxY - i * (maxY - minY) / 4).toFixed(2)}</text><text x={55 + i * 121.25} y="244" textAnchor="middle" className="chart-label">{Math.round(maxX * i / 4)}</text></g>)}
      <g>{points.filter(p => !reviewOnly || p.review).map(p => <circle key={p.id} cx={x(p.x)} cy={y(p.y)} r={p.review ? 3.9 : 2.7} fill={p.review ? COLORS[1] : COLORS[0]} opacity={p.review ? .9 : .33} onMouseEnter={() => setActive(p)} onMouseLeave={() => setActive(null)}><title>{p.id} · {p.x} genes · score {p.y.toFixed(3)}</title></circle>)}</g>
      <text x="300" y="270" textAnchor="middle" className="chart-label">{t('Complete gene count', 'पूर्ण जीन संख्या')}</text><text transform="translate(13 130) rotate(-90)" textAnchor="middle" className="chart-label">{t('Anomaly score', 'Anomaly score')}</text>
    </svg><div className="chart-footnote">{active ? `${active.id} · ${active.x} genes · ${active.y.toFixed(4)}` : t('Each dot is an isolate. Hover to inspect.', 'हर बिंदु एक isolate है। विवरण के लिए hover करें।')}</div>
  </div>;
}

export function Heatmap({ data }) {
  const { t, theme } = useUI();
  if (!data?.genes?.length) return <p>{t('No gene prevalence data available.', 'Gene prevalence डेटा उपलब्ध नहीं है।')}</p>;
  return <div className="heatmap-scroll"><table className="heatmap-table"><thead><tr><th>{t('Cluster', 'क्लस्टर')}</th>{data.genes.map(g => <th key={g}><span>{g}</span></th>)}</tr></thead><tbody>{data.rows.map(row => <tr key={row.cluster}><th>C{row.cluster}<small>n={row.n}</small></th>{row.values.map((v, i) => <td key={i}><div style={{ background: `color-mix(in srgb, var(--accent) ${Math.max(4, v)}%, var(--card))`, color: v > 55 ? (theme === 'dark' ? '#0d2d23' : '#fff') : 'var(--text)' }} title={`${data.genes[i]} · Cluster ${row.cluster}: ${v}%`}>{Math.round(v)}<span>%</span></div></td>)}</tr>)}</tbody></table><div className="heat-key"><span>0%</span><i /><span>100% {t('prevalence', 'prevalence')}</span></div></div>;
}

export function CountryBars({ data }) {
  const max = Math.max(1, ...data.map(d => d.count));
  return <div className="horizontal-bars">{data.map((d, i) => <div key={d.name}><div><span>{d.name}</span><strong>{format(d.count)}</strong></div><div className="bar-track"><i style={{ width: `${d.count / max * 100}%`, background: COLORS[i % 3] }} /></div></div>)}</div>;
}

export function Confusion({ values }) {
  const { t, theme } = useUI();
  if (!values?.length) return null;
  const max = Math.max(...values.flat());
  return <div className="confusion"><span className="muted">{t('Predicted', 'Predicted')}</span><div className="confusion-grid"><span /><span>S</span><span>R</span>{values.map((row, i) => <React.Fragment key={i}><span>{i ? 'R' : 'S'}</span>{row.map((v, j) => <div key={j} style={{ background: i === j ? `color-mix(in srgb, var(--accent) ${35 + v / max * 60}%, var(--card))` : 'var(--peach-bg)', color: i === j ? (theme === 'dark' ? '#0d2d23' : '#fff') : 'var(--peach-text)' }}><strong>{v}</strong><small>{i === j ? t('Correct', 'सही') : t('Error', 'गलत')}</small></div>)}</React.Fragment>)}</div><small>{t('Rows = actual label · S = susceptible · R = resistant', 'पंक्तियाँ = actual label · S = susceptible · R = resistant')}</small></div>;
}
