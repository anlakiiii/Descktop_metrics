from desktop_metrics.windows_storage import DiskHealthProvider, disk_health_score


def test_disk_health_score() -> None:
    assert disk_health_score("Healthy") == 100.0
    assert disk_health_score("Warning") == 55.0
    assert disk_health_score("Unhealthy") == 10.0
    assert disk_health_score("Unknown") is None


def test_disk_health_normalization() -> None:
    item = DiskHealthProvider._normalize(
        {
            "device_id": 2,
            "name": "Example SSD",
            "health": "Healthy",
            "operational": ["OK"],
            "media_type": "SSD",
            "size": "1000",
        },
        0,
    )
    assert item["device_id"] == "2"
    assert item["name"] == "Example SSD"
    assert item["operational"] == "OK"
    assert item["size"] == 1000


def test_disk_health_query_runs_in_background(monkeypatch) -> None:
    import time
    from threading import Event
    from types import SimpleNamespace

    import desktop_metrics.windows_storage as storage_module

    monkeypatch.setattr(storage_module, "os", SimpleNamespace(name="nt"))
    provider = DiskHealthProvider(cache_seconds=60)
    release = Event()

    def slow_query():
        release.wait(1.0)
        return ([{"device_id": "0", "name": "Example SSD", "health": "Healthy"}], "")

    monkeypatch.setattr(provider, "_query_windows", slow_query)
    started = time.perf_counter()
    items, message = provider.collect()
    assert time.perf_counter() - started < 0.2
    assert items == []
    assert "starting" in message.lower()

    release.set()
    deadline = time.perf_counter() + 1.0
    while time.perf_counter() < deadline:
        items, _message = provider.collect()
        if items:
            break
        time.sleep(0.01)
    assert items[0]["health"] == "Healthy"
