import React, { useState } from 'react';
import { ArrowRight, CheckCheck, CircleAlert, Download, FileCheck2, FileText, Keyboard, Plus, Trash2, UploadCloud } from 'lucide-react';
import { api, useUI } from './context';

const quote = value => `"${String(value).replaceAll('"', '""')}"`;
export default function InputWorkspace() {
  const { t } = useUI();
  const species = 'Klebsiella pneumoniae';
  const drug = 'ceftazidime';
  const [mode, setMode] = useState('manual'), [samples, setSamples] = useState([{ id: '', genes: '' }]);
  const [paste, setPaste] = useState(''), [file, setFile] = useState(null), [result, setResult] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [checkedContent, setCheckedContent] = useState('');
  const [confirmed, setConfirmed] = useState(false), [prediction, setPrediction] = useState(null);
  const clearResult = () => { setResult(null); setError(''); setCheckedContent(''); setPrediction(null); setConfirmed(false); };

  function update(index, key, value) { clearResult(); setSamples(rows => rows.map((r, i) => i === index ? { ...r, [key]: value } : r)); }
  function choose(f) { clearResult(); if (f && (!/\.(csv|tsv)$/i.test(f.name) || f.size > 5 * 1024 * 1024)) { setError(t('Choose a CSV or TSV file smaller than 5 MB.', '5 MB से छोटी CSV या TSV file चुनें।')); setFile(null); return; } setFile(f); }
  async function content() {
    if (mode === 'upload') { if (!file) throw new Error(t('Choose a file first.', 'पहले file चुनें।')); return file.text(); }
    if (mode === 'paste') { if (!paste.trim()) throw new Error(t('Paste your CSV or TSV table first.', 'पहले CSV या TSV table paste करें।')); return paste; }
    for (let i = 0; i < samples.length; i++) {
      const row = samples[i];
      if (!/^[A-Za-z0-9_.-]{1,100}$/.test(row.id.trim())) throw new Error(t(`Sample ${i + 1}: use a sample ID with letters, numbers, dots, hyphens or underscores.`, `Sample ${i + 1}: ID में letters, numbers, dots, hyphens या underscores रखें।`));
      if (!row.genes.trim()) throw new Error(t(`Sample ${i + 1}: add at least one gene or mutation entry.`, `Sample ${i + 1}: कम से कम एक gene या mutation entry लिखें।`));
    }
    return 'BioSample\tAMR genotypes\n' + samples.map(r => `${quote(r.id.trim())}\t${quote(r.genes.trim().replace(/\r?\n/g, ', '))}`).join('\n') + '\n';
  }
  async function validate(e) {
    e.preventDefault(); setBusy(true); setError(''); setResult(null); setPrediction(null); setConfirmed(false);
    try { const text = await content(); const data = await api('/validate-input', { method: 'POST', body: JSON.stringify({ content: text }) }); setResult(data); setCheckedContent(text); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function runPrediction() {
    setBusy(true); setError(''); setPrediction(null);
    try {
      setPrediction(await api('/predict', {
        method: 'POST',
        body: JSON.stringify({
          content: checkedContent,
          species: 'Klebsiella pneumoniae',
          complete_profile: confirmed,
          drug: 'ceftazidime'
        })
      }));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  function download() { const blob = new Blob([checkedContent], { type: checkedContent.split('\n')[0].includes('\t') ? 'text/tab-separated-values' : 'text/csv' }); const link = document.createElement('a'); const url = URL.createObjectURL(blob); link.href = url; link.download = `resistmap-my-input.${blob.type === 'text/csv' ? 'csv' : 'tsv'}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  function example() {
    clearResult();
    if (mode === 'manual') setSamples([{ id: 'MY_SAMPLE_01', genes: 'blaSHV-11=COMPLETE\ngyrA_S83I=POINT' }]);
    else setPaste('BioSample\tAMR genotypes\nMY_SAMPLE_01\tblaSHV-11=COMPLETE, gyrA_S83I=POINT\n');
  }
  return <div className="input-layout"><section className="card input-card user-input-card">
    <div className="card-heading">
      <div>
        <span className="eyebrow">{t('YOUR DATA, YOUR WORKSPACE', 'आपका डेटा, आपका WORKSPACE')}</span>
        <h3>{t('Add your genomic input', 'अपना genomic input जोड़ें')}</h3>
        <p>{t('Type a sample, paste a table, or upload a file.', 'Sample लिखें, table paste करें या file upload करें।')}</p>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <span className="pill">{species}</span>
        <span className="pill">Ceftazidime · CLSI</span>
        <span className="pill small">V2 Model</span>
      </div>
    </div>
    <div className="input-mode-tabs" role="tablist" aria-label="Input method">{[['manual', Keyboard, t('Manual entry', 'खुद लिखें')], ['paste', FileText, t('Paste data', 'डेटा paste करें')], ['upload', UploadCloud, t('Upload file', 'File upload')]].map(([key, Icon, label]) => <button key={key} role="tab" id={`tab-${key}`} aria-controls="input-method-panel" aria-selected={mode === key} onClick={() => { setMode(key); clearResult(); }}><Icon size={17} />{label}</button>)}</div>
    <form onSubmit={validate}><fieldset disabled={busy} className="input-fieldset"><div id="input-method-panel" role="tabpanel" aria-labelledby={`tab-${mode}`}>
      {mode === 'manual' && <div className="manual-samples">{samples.map((row, i) => <div className="manual-sample" key={i}><div className="manual-sample-heading"><strong>{t('SAMPLE', 'SAMPLE')} {String(i + 1).padStart(2, '0')}</strong>{samples.length > 1 && <button type="button" className="icon-button" aria-label={`Remove sample ${i + 1}`} onClick={() => { setSamples(rows => rows.filter((_, index) => i !== index)); clearResult(); }}><Trash2 size={16} /></button>}</div><label className="field-label" htmlFor={`sample-${i}`}>{t('Sample ID / BioSample', 'Sample ID / BioSample')}<input id={`sample-${i}`} className="manual-id" value={row.id} onChange={e => update(i, 'id', e.target.value)} placeholder="MY_SAMPLE_01 or SAMN…" maxLength={100} autoComplete="off" /></label><label className="field-label" htmlFor={`genes-${i}`}>{t('Genes and mutations', 'Genes और mutations')}<textarea id={`genes-${i}`} value={row.genes} onChange={e => update(i, 'genes', e.target.value)} placeholder={'blaSHV-11=COMPLETE\ngyrA_S83I=POINT'} rows={4} maxLength={50000} spellCheck={false} /><small>{t('One gene=status entry per line, or separate entries with commas.', 'हर line पर gene=status लिखें या comma से अलग करें।')}</small></label></div>)}<div className="manual-add-row"><button type="button" className="text-button" onClick={() => { setSamples(rows => [...rows, { id: '', genes: '' }]); clearResult(); }} disabled={samples.length >= 20}><Plus size={15} />{t('Add another sample', 'एक और sample जोड़ें')}</button><button type="button" className="text-button" onClick={example}>{t('Load example', 'उदाहरण भरें')}</button></div></div>}
      {mode === 'paste' && <div className="paste-panel"><label className="field-label" htmlFor="pasted-table">{t('Paste a CSV or TSV table, including headers', 'Headers सहित CSV या TSV table paste करें')}<textarea id="pasted-table" value={paste} onChange={e => { setPaste(e.target.value); clearResult(); }} rows={10} maxLength={5 * 1024 * 1024} spellCheck={false} placeholder={'BioSample\tAMR genotypes\nMY_SAMPLE_01\tblaSHV-11=COMPLETE'} /></label><button type="button" className="text-button" onClick={example}>{t('Load example table', 'उदाहरण table भरें')}</button></div>}
      {mode === 'upload' && <label className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) choose(e.dataTransfer.files[0]); }}><input type="file" aria-label="Upload genomic data" accept=".csv,.tsv" onChange={e => choose(e.target.files[0])} /><span className="upload-icon"><UploadCloud size={30} /></span><strong>{file ? file.name : t('Drop your file here', 'अपनी file यहाँ डालें')}</strong><p>{t('or click to browse', 'या चुनने के लिए click करें')}</p><small>CSV / TSV · {t('up to 5 MB', 'अधिकतम 5 MB')}</small></label>}
    </div><div className="input-actions"><a className="text-button" href="/api/template"><Download size={15} />{t('Download template', 'Template डाउनलोड')}</a><button type="submit" className="button primary">{busy ? t('Checking…', 'जाँच हो रही है…') : t('Check my input', 'मेरा input जाँचें')}<ArrowRight size={16} /></button></div></fieldset></form>
    {error && <div className="error-note" role="alert">{error}</div>}
    {result && <div className="validation-result" role="status"><h3><CheckCheck size={20} />{t('Your input is ready for review', 'आपका input review के लिए तैयार है')}</h3><p>{result.samples} {t('samples checked. This is an input check, not a resistance prediction.', 'samples जाँचे गए। यह input की जाँच है, resistance prediction नहीं।')}</p>{result.preview.map(r => <div key={r.sample}><code>{r.sample}</code><span>{r.features} {t('COMPLETE / POINT entries', 'COMPLETE / POINT entries')} · {r.other_entries} {t('other entries', 'अन्य entries')}</span></div>)}<button type="button" className="text-button" onClick={download}><Download size={15} />{t('Download my input', 'मेरा input डाउनलोड करें')}</button></div>}
    {result && checkedContent && <div className="validation-result">
      <label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />{t('I confirm these are complete annotated AMR profiles from Klebsiella pneumoniae, not selected example genes.', 'मैं पुष्टि करता हूँ कि ये Klebsiella pneumoniae के पूरे annotated AMR profiles हैं, केवल चुने हुए उदाहरण genes नहीं।')}</label>
      <p>{t('V2 research baseline. Fresh independent validation is pending.', 'V2 research model। नई स्वतंत्र validation बाकी है।')}</p>
      <button type="button" className="button primary" disabled={!confirmed || busy} onClick={runPrediction}>{busy ? t('Running…', 'चल रहा है…') : t('Run research prediction', 'Research prediction चलाएँ')}</button>
      {prediction && <><p>{prediction.model} · {t('Target drug', 'Target drug')}: <strong>{prediction.target}</strong> · {t('Threshold', 'Threshold')} {prediction.threshold}</p>{prediction.results.map(r => <div key={r.sample}><code>{r.sample}</code><strong>{r.prediction === 'Resistant' ? t('Likely resistant to ceftazidime', 'Ceftazidime के लिए likely resistant') : r.prediction === 'Susceptible' ? t('Likely susceptible to ceftazidime', 'Ceftazidime के लिए likely susceptible') : t('Result unavailable', 'Result उपलब्ध नहीं')}</strong><span>{t('Research estimate · resistance score', 'Research estimate · resistance score')}: {r.probability_R == null ? '—' : r.probability_R.toFixed(3)} · {r.unseen_features.length} {t('unseen features', 'अनदेखे features')}</span></div>)}<p>{prediction.notice}</p><button type="button" className="text-button" onClick={() => { const url = URL.createObjectURL(new Blob([JSON.stringify(prediction, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = 'resistmap-predictions.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }}>{t('Download predictions', 'Predictions डाउनलोड')}</button></>}
    </div>}
    <p className="input-privacy">{t('Data is checked locally and is not saved on the server. Download your input before leaving this page.', 'डेटा इसी computer पर जाँचा जाता है, server पर save नहीं होता। Page छोड़ने से पहले अपना input डाउनलोड करें।')}</p>
  </section><aside className="card input-guide"><span className="stat-icon mint"><FileCheck2 size={22} /></span><h3>{t('What can I enter?', 'क्या लिख सकते हैं?')}</h3><p>{t('Use your own sample name or a BioSample accession, then add the AMR gene or mutation calls for that sample.', 'अपना sample नाम या BioSample accession लिखें, फिर उस sample के AMR gene या mutation calls डालें।')}</p><code>blaSHV-11=COMPLETE<br />gyrA_S83I=POINT</code><p>{t('Raw DNA or protein sequences are not AMR calls. Sequence files need annotation before this input step.', 'Raw DNA या protein sequence, AMR calls नहीं हैं। Sequence files को पहले annotate करना होगा।')}</p><div className="pending-box"><CircleAlert size={17} /><span>{t('Validate input first, then run the saved V2 research model. Independent validation remains pending.', 'पहले input जाँचें, फिर V2 research model चलाएँ। स्वतंत्र validation अभी बाकी है।')}</span></div></aside></div>;
}
