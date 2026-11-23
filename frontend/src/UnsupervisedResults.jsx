import React, { useState } from 'react';
import { SourceDonut } from './Charts';
import EcoliExternalResults from './EcoliExternalResults';
import { format, pct } from './context';

export default function UnsupervisedResults({ summary, cohortId }) {
  const [chosen, setSelected] = useState('escherichia_coli');
  const selected = cohortId ?? chosen;
  const [imageError, setImageError] = useState(false);
  const species = summary?.species || [];
  const current = species.find(s => s.id === selected);
  const c = current?.clustering || {};
  const projection = current?.projection || {};
  const anomaly = current?.anomaly_review || {};
  const sizes = c.cluster_sizes || [];
  const total = sizes.reduce((sum, n) => sum + n, 0);
  const isTB = selected === 'tuberculosis';
  const hasUnsupervised = !!current && current.unsupervised_available !== false;
  return <>
    {!cohortId && <section className="card unsup-panel">
      <div className="card-heading"><div><h3>Multispecies models & exploration</h3><p>Saved research baselines · Supervised resistance models & unsupervised clustering</p></div></div>
      <label className="unsup-selector">Choose a cohort<select value={selected} onChange={e => { setSelected(e.target.value); setImageError(false); }}>{species.map(s => <option value={s.id} key={s.id}>{s.species}{s.unsupervised_available === false ? ' · unsupervised unavailable' : ''}</option>)}</select></label>
    </section>}

    {selected === 'escherichia_coli' && <EcoliExternalResults />}
    {current?.supervised_summary?.length > 0 && !isTB && <section className="card unsup-panel">
      <div className="card-heading">
        <div>
          <h3>Supervised Model Scores · {current.species}</h3>
          <p>Training score, Validation score, and Testing score across {current.eligible_tasks_trained} eligible drug models</p>
        </div>
        <span className="pill">LogisticRegression · {current.eligible_tasks_trained} Tasks</span>
      </div>
      <div className="score-summary-grid">
        {['train', 'validation', 'test'].map(sp => {
          const row = current.supervised_summary.find(s => s.split === sp);
          if (!row) return null;
          const title = sp === 'train' ? 'Training score' : sp === 'validation' ? 'Validation score' : 'Testing score';
          return <div className="stat-card" key={sp}>
            <div className="stat-top">
              <span className="muted">{title}</span>
              <span className="pill small">{sp}</span>
            </div>
            <div className="stat-value" style={{ fontSize: 28 }}>{pct(row.macro_accuracy)}</div>
            <p>Balanced: {pct(row.macro_balanced_accuracy)} · F1: {pct(row.macro_f1_resistant)} · AUC: {pct(row.macro_roc_auc)}</p>
          </div>;
        })}
      </div>
      {current.per_drug_metrics?.length > 0 && <details style={{ marginTop: 16 }}>
        <summary>Per-drug evaluation breakdown ({Math.round(current.per_drug_metrics.length / 3)} drugs × 3 splits)</summary>
        <div className="table-scroll"><table className="samples-table">
          <thead><tr><th>Antibiotic</th><th>Split</th><th>Samples</th><th>Accuracy</th><th>Balanced Acc</th><th>F1 (Resistant)</th><th>ROC AUC</th></tr></thead>
          <tbody>{current.per_drug_metrics.map((m, idx) => <tr key={idx}>
            <td><strong>{m.antibiotic}</strong></td>
            <td><span className="pill small">{m.split}</span></td>
            <td className="mono">{m.samples}</td>
            <td className="mono">{pct(m.accuracy)}</td>
            <td className="mono">{pct(m.balanced_accuracy)}</td>
            <td className="mono">{pct(m.f1_resistant)}</td>
            <td className="mono">{pct(m.roc_auc)}</td>
          </tr>)}</tbody>
        </table></div>
      </details>}
      <p className="card-note">Model: LogisticRegression(class_weight=balanced, solver=liblinear). Group-aware split applied to prevent isolate leakage. Development baselines; independent clinical validation pending.</p>
    </section>}

    {isTB && <section className="card unsup-panel">
      <h3>M. tuberculosis · supervised training complete</h3>
      <p>{format(summary?.tb_features?.samples)} samples in the saved feature matrix · {format(summary?.tb_features?.features)} genomic mutation features.</p>
      {summary?.tb_supervised?.eligible_tasks_trained > 0 && <>
        <p><strong>{summary.tb_supervised.eligible_tasks_trained}</strong> drug models trained · <strong>{summary.tb_supervised.drugs_skipped}</strong> drugs skipped (insufficient class support).</p>
        <p>Split: {summary.tb_supervised.split_counts && `${format(summary.tb_supervised.split_counts.train)} train / ${format(summary.tb_supervised.split_counts.validation)} validation / ${format(summary.tb_supervised.split_counts.test)} test`}. Model: {summary.tb_supervised.model}.</p>
        {summary.tb_supervised.summary?.length > 0 && <div className="score-summary-grid">
          {['train', 'validation', 'test'].map(sp => {
            const row = summary.tb_supervised.summary.find(s => s.split === sp);
            if (!row) return null;
            const title = sp === 'train' ? 'Training score' : sp === 'validation' ? 'Validation score' : 'Testing score';
            return <div className="stat-card" key={sp}>
              <div className="stat-top"><span className="muted">{title}</span><span className="pill small">{sp}</span></div>
              <div className="stat-value" style={{ fontSize: 28 }}>{pct(row.macro_accuracy)}</div>
              <p>Balanced: {pct(row.macro_balanced_accuracy)} · F1: {pct(row.macro_f1_resistant)} · AUC: {pct(row.macro_roc_auc)}</p>
            </div>;
          })}
        </div>}
        {summary.tb_supervised.per_drug_test?.length > 0 && <details>
          <summary>Per-drug test results ({summary.tb_supervised.per_drug_test.length} drugs)</summary>
          <div className="table-scroll"><table className="samples-table">
            <caption>Saved development test-split results · not independent validation</caption>
            <thead><tr><th>Drug</th><th>Test samples</th><th>Accuracy</th><th>Balanced acc.</th><th>F1 (resistant)</th><th>ROC AUC</th></tr></thead>
            <tbody>{summary.tb_supervised.per_drug_test.map(d => <tr key={d.drug}>
              <td><strong>{d.drug}</strong></td>
              <td className="mono">{format(d.test_samples)}</td>
              <td className="mono">{pct(d.test_accuracy)}</td>
              <td className="mono">{pct(d.test_balanced_acc)}</td>
              <td className="mono">{pct(d.test_f1_resistant)}</td>
              <td className="mono">{pct(d.test_roc_auc)}</td>
            </tr>)}</tbody>
          </table></div>
        </details>}
      </>}
      <p>Saved descriptive results are shown below when their artifacts are available. No analysis job runs from this page.</p>
      <p className="card-note">{summary?.tb_supervised?.limitations || 'Development baselines only. No external validation cohort used.'}</p>
      <p className="card-note">{summary?.tb_supervised?.split_policy}</p>
      <span className="pill">{hasUnsupervised ? 'Saved exploration available' : 'Exploration unavailable'} · Supervised training recorded</span>
    </section>}
    {hasUnsupervised ? <>
      <div className="dashboard-row">
        <section className="card unsup-panel"><h3>Cluster composition · {current?.species}</h3><p>{format(total)} records · {sizes.length} saved groups</p>{sizes.length ? <SourceDonut total={total} label="records" data={sizes.map((value, i) => ({ name: `Cluster ${i}`, value }))} /> : <p>Saved cluster sizes unavailable.</p>}<p className="card-note">{c.scope}</p></section>
        <section className="card unsup-panel"><h3>Compare cluster sizes</h3><p>Click a group for its descriptive summary.</p>{sizes.map((size, i) => <details className="unsup-cluster" key={`${selected}-${i}`}><summary><span>Cluster {i}</span><strong>{format(size)} · {pct(size / total)}</strong><span className="unsup-bar"><span style={{ width: `${size / Math.max(...sizes) * 100}%` }} /></span></summary><p>This saved group contains {format(size)} records ({pct(size / total)} of this cohort). The longest bar represents the largest cluster. Its ID describes a similarity group, not a clinical category.</p></details>)}<p className="card-note">Location/year comparisons are not connected to these cluster assignments.</p></section>
      </div>
      <section className="card unsup-panel"><h3>2D landscape · saved SVD projection</h3><p>{format(projection.plot_samples)} plotted records · two displayed dimensions explain {pct(projection.two_dimensional_variance)} of variance.</p>{projection.plot_samples && !imageError ? <a href={`/api/unsupervised/${selected}/projection.png`} target="_blank" rel="noreferrer"><img className="unsup-projection" src={`/api/unsupervised/${selected}/projection.png`} alt={`${current?.species}: saved SVD scatterplot and cumulative explained variance`} onError={() => setImageError(true)} /></a> : <p>Saved projection image unavailable.</p>}<p className="card-note">Click the plot to enlarge. These points are not colored by cluster. {projection.limitations}</p></section>
      <section className="card unsup-panel"><h3>Anomaly detection · stability review</h3><p>How consistently the saved analysis ranks unusual records across resampled runs.</p><div className="score-summary-grid">{[['Review records', format(anomaly.validation_samples)], ['Rank correlation range', anomaly.pairwise_spearman_range?.map(x => x.toFixed(3)).join(' – ') || 'Unavailable'], ['Top 5% overlap (Jaccard)', pct(anomaly.mean_top_5pct_jaccard)]].map(([label, value]) => <div className="stat-card" key={label}><span>{label}</span><div className="stat-value" style={{ fontSize: 27 }}>{value}</div></div>)}</div><p>No automatic anomaly threshold is recorded. This page does not label individual records as unusual or assign new samples to clusters.</p><details><summary>Analysis limitations and provenance</summary><p>{anomaly.limitations}</p><p>{c.limitations}</p><p>Source: data/processed/multispecies/{selected}/unsupervised_profiles/ — clusters, svd and anomaly_resampling reports.</p></details></section>
    </> : <section className="card unsup-panel">
      <h3>{current?.species} · unsupervised results unavailable</h3>
      <p>Unsupervised clustering, anomaly detection and 2D visualization have not been generated for this species.</p>
      {current?.eligible_tasks_trained > 0 && <p>{current.eligible_tasks_trained} supervised drug models are recorded separately.</p>}
      <span className="pill">Results unavailable</span>
    </section>}
  </>;
}
