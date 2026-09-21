from desktop_metrics.autostart import _commands_match


def test_startup_command_comparison_is_case_and_whitespace_insensitive() -> None:
    assert _commands_match(
        '  "C:\\Program Files\\Desktop Metrics\\DesktopMetrics.exe"  ',
        '"c:\\program files\\desktop metrics\\desktopmetrics.exe"',
    )
    assert not _commands_match('"C:\\Old\\DesktopMetrics.exe"', '"C:\\New\\DesktopMetrics.exe"')


def test_startup_command_allows_optional_quotes_for_single_executable() -> None:
    assert _commands_match('"C:\\Tools\\DesktopMetrics.exe"', 'C:\\Tools\\DesktopMetrics.exe')
