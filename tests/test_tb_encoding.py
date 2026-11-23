import pytest
from tools.audit_tb_encoding import audit, encode_pairs


def test_original_mutations_match_saved_matrix():
    result = audit()
    assert result['encoding_matches']
    assert len(result['raw_record_comparisons']) == 5
    assert not result['model_ordering_certified']


def test_binary_pairs_preserve_boundaries():
    vocabulary = [['a_b', 'c'], ['a', 'b_c']]
    assert encode_pairs([('a_b', 'c')] * 300, vocabulary).toarray().tolist() == [[1, 0]]
    with pytest.raises(ValueError, match='absent'):
        encode_pairs([('missing', 'mutation')], vocabulary)
    with pytest.raises(ValueError, match='Duplicate'):
        encode_pairs([], [['a', 'b'], ['a', 'b']])
