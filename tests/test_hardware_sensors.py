from desktop_metrics.hardware_sensors import HardwareFanProvider


def test_cpu_fan_prefers_cpu_label(monkeypatch) -> None:
    provider = HardwareFanProvider()
    monkeypatch.setattr(
        provider,
        "collect",
        lambda force=False: (
            [
                {"name": "GPU Fan", "identifier": "/gpu/0/fan/0", "parent": "GPU", "source": "test", "rpm": 1800.0},
                {"name": "CPU Fan", "identifier": "/lpc/cpu/fan/0", "parent": "CPU", "source": "test", "rpm": 1200.0},
            ],
            "",
        ),
    )
    result = provider.cpu_fan()
    assert result["available"] is True
    assert result["rpm"] == 1200.0
    assert result["name"] == "CPU Fan"


def test_fan_query_runs_in_background(monkeypatch) -> None:
    import time
    from threading import Event

    provider = HardwareFanProvider(cache_seconds=60)
    release = Event()

    def slow_query():
        release.wait(1.0)
        return (
            [
                {
                    "name": "CPU Fan",
                    "identifier": "cpu",
                    "parent": "CPU",
                    "source": "test",
                    "rpm": 1234.0,
                }
            ],
            "",
        )

    monkeypatch.setattr(provider, "_perform_query", slow_query)
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
    assert items[0]["rpm"] == 1234.0
