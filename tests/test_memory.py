from scan_vs_bim.memory import peak_rss_gb


def test_peak_rss_is_in_gigabytes():
    assert 0.01 < peak_rss_gb() < 100  # a wrong unit would be off by 1e3 or more
