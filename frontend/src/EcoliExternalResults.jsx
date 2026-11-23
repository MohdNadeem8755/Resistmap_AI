import React from 'react';
import report from '../../data/candidate_validation/escherichia_coli/PRJEB4681/pilot_screened_retrained_model/genome_similarity/dashboard_validation.json';
import { useUI } from './context';

export default function EcoliExternalResults() {
  const { t } = useUI();
  const n = value => value.toLocaleString('en-US');
  const agreement = [Math.min(...report.spearman), Math.max(...report.spearman)]
    .map(value => value.toFixed(3)).join('–');
  const metrics = [
    [t('External samples scored (pilot excluded)', 'External samples scored (pilot हटाकर)'), `${n(report.scored)} / ${n(report.eligible)}`],
    [t('Mean anomaly score', 'औसत anomaly score'), report.mean_score.toFixed(4)],
    [t('Rank agreement across forests (Spearman)', 'Forests की rankings का agreement (Spearman)'), agreement],
    [t('Samples with unresolved identity', 'जिन samples की identity अभी स्पष्ट नहीं है'), n(report.unresolved_samples)],
  ];
  return <section className="card unsup-panel">
    <div className="card-heading"><div>
      <h3>{t('E. coli external anomaly scoring', 'E. coli की external anomaly scoring')}</h3>
      <p>{report.cohort} · {t('Independent validation pending', 'Independent validation बाकी है')}</p>
    </div></div>
    <div className="detail-grid">{metrics.map(([label, value]) =>
      <div className="detail-item" key={label}><span className="detail-label">{label}</span><strong className="detail-value">{value}</strong></div>
    )}</div>
    <p>{t(`Compared with ${n(report.references)} development references. ${n(report.unresolved_pairs)} possible sample pairs still need specimen records. Anomaly accuracy has not been measured.`,
      `${n(report.references)} development references से तुलना हुई। ${n(report.unresolved_pairs)} संभावित pairs के लिए specimen records चाहिए। Anomaly accuracy अभी मापी नहीं गई है।`)}</p>
  </section>;
}
