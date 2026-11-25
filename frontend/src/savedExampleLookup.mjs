// Lookup only: this does not run or change a model.
const tbDrugCodes = {
  rifampicin: 'rif', isoniazid: 'inh', ethambutol: 'emb', pyrazinamide: 'pza',
  amikacin: 'ami', capreomycin: 'cap', ethionamide: 'eth', kanamycin: 'kan',
  levofloxacin: 'lev', moxifloxacin: 'mxf', ofloxacin: 'ofx', streptomycin: 'stm',
  bedaquiline: 'bdq', clofazimine: 'cfz', linezolid: 'lzd',
  'para-aminosalicylic acid': 'pas', rifabutin: 'rfb',
};

function tbDrugCode(value) {
  const name = String(value || '').trim().toLowerCase();
  return tbDrugCodes[name] ?? name;
}

export function reconcileRecordedTest(result) {
  if (result.species !== 'Mycobacterium tuberculosis' || result.score_source !== 'not_available') return result;
  const recorded = result.drugs?.find(row => tbDrugCode(row.drug) === tbDrugCode(result.drug));
  if (!recorded) return result;
  return {
    ...result,
    status: recorded.status,
    explanation: `Recorded lab result for ${result.drug}: ${recorded.status}. No model prediction was returned for this lookup.`,
  };
}

export function lookupSavedExamples(text, examples) {
  const ids = [...new Set(text.trim().toUpperCase().split(/[\s,;]+/).filter(Boolean))];
  const index = new Map(examples.map(row => [row.sample.toUpperCase(), row]));
  return ids.map(sample => ({ sample, record: index.get(sample) || null }));
}
