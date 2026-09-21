from desktop_metrics.windows_wifi import signal_quality_to_dbm


def test_windows_wifi_quality_conversion() -> None:
    assert signal_quality_to_dbm(0) == -100.0
    assert signal_quality_to_dbm(50) == -75.0
    assert signal_quality_to_dbm(100) == -50.0
    assert signal_quality_to_dbm(150) == -50.0
