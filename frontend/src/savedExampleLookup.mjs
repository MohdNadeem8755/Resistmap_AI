// Lookup only: this does not run or change a model.
export function lookupSavedExamples(text, examples) {
  const ids = [...new Set(text.trim().toUpperCase().split(/[\s,;]+/).filter(Boolean))];
  const index = new Map(examples.map(row => [row.sample.toUpperCase(), row]));
  return ids.map(sample => ({ sample, record: index.get(sample) || null }));
}
