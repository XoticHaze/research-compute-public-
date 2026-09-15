import pandas as pd

from scripts.p04_r3_h24_context_consumer_v1 import _same_bucket_count


def test_five_of_eight_same_bucket_passes_support_count():
    nearest = pd.DataFrame({"h24_bucket": [1, 1, 1, 1, 1, 2, 3, 4]})
    assert _same_bucket_count(nearest, 1) == 5


def test_four_of_eight_same_bucket_fails_support_count():
    nearest = pd.DataFrame({"h24_bucket": [1, 1, 1, 1, 2, 2, 3, 4]})
    assert _same_bucket_count(nearest, 1) == 4


def test_missing_query_bucket_fails_closed():
    nearest = pd.DataFrame({"h24_bucket": [1, 1, 1, 1, 1, 1, 1, 1]})
    assert _same_bucket_count(nearest, None) == 0
    assert _same_bucket_count(nearest, float("nan")) == 0


def test_arbitrary_relabeling_preserves_concordance():
    original = pd.DataFrame({"h24_bucket": [1, 1, 1, 1, 1, 2, 3, 4]})
    mapping = {1: 5, 2: 2, 3: 1, 4: 3, 5: 4}
    relabeled = pd.DataFrame({"h24_bucket": [mapping[x] for x in original.h24_bucket]})
    assert _same_bucket_count(original, 1) == _same_bucket_count(relabeled, mapping[1]) == 5
