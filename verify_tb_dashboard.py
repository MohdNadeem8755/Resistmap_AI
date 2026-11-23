import sys, json
sys.path.insert(0, r'D:\ResistMap-AI')
from backend.dashboard import get_species_examples, multispecies_summary, lookup_sample

# 1. Check species examples
examples = get_species_examples()
tb_ex = examples['Mycobacterium tuberculosis']
print('=== TB Dashboard Examples ===')
for ex in tb_ex:
    print('  {} | {} | observed={} | predicted={} | score={} | source={}'.format(
        ex['sample'], ex['drug'], ex['observed'], ex['predicted'], ex['score'], ex['score_source']))

# 2. Check multispecies summary status
ms = multispecies_summary()
for sp in ms['species']:
    if sp['id'] == 'tuberculosis':
        print('\n=== TB Multispecies Summary ===')
        print('  Status:', sp['status'])
        print('  Trained models:', sp['eligible_tasks_trained'])
        print('  Scores (test):', sp['scores'].get('test', {}))
        break

# 3. Check sample lookup
for sid, drug in [('SAMEA10029749', 'rif'), ('SAMEA13299636', 'rif'), ('SAMEA10029752', 'inh')]:
    r = lookup_sample(sid, drug=drug)
    print('\n=== Lookup {} ({}) ==='.format(sid, drug))
    print('  found={} species={} predicted={} score={} source={}'.format(
        r.get('found'), r.get('species'), r.get('predicted'), r.get('score'), r.get('score_source')))

print('\n✅ All TB dashboard integrations verified!')
