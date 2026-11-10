import json

import pandas as pd
import pytest

from quant.data.cache import load_or_fetch


def _series():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-02", "2024-01-03"]), name="X")
    s.attrs["source"] = "fake"
    return s


def test_fetch_called_once_within_max_age(tmp_path):
    calls = []

    def fetch():
        calls.append(1)
        return _series()

    load_or_fetch("X", fetch, cache_dir=tmp_path)
    load_or_fetch("X", fetch, cache_dir=tmp_path)
    assert len(calls) == 1


def test_stale_cache_returned_when_fetch_fails(tmp_path):
    load_or_fetch("X", _series, cache_dir=tmp_path)
    meta = tmp_path / "X.meta.json"
    m = json.loads(meta.read_text())
    m["fetched_at"] = "2000-01-01T00:00:00"
    meta.write_text(json.dumps(m))

    def boom():
        raise RuntimeError("network down")

    with pytest.warns(UserWarning):
        out = load_or_fetch("X", boom, cache_dir=tmp_path)
    assert out.tolist() == [1.0, 2.0]


def test_meta_records_source(tmp_path):
    load_or_fetch("X", _series, cache_dir=tmp_path)
    m = json.loads((tmp_path / "X.meta.json").read_text())
    assert m["source"] == "fake"
    assert "fetched_at" in m
