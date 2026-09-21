# Desktop Metrics changelog

## 1.8.1

- Shortened unavailable CPU/GPU fan text while keeping the complete diagnostic in a tooltip.
- Added single-line ellipsis handling so long sensor, process, disk, and adapter details cannot widen the widget.
- Made every metric card use the same exact height at each interface scale.
- Reserved a fixed progress-bar slot so cards with and without percentages keep identical internal spacing.
- Made grid columns ignore content width hints, keeping all cards evenly sized.
- Suppressed the obsolete `pynvml` distribution warning while retaining the supported `nvidia-ml-py` NVML backend.

## 1.8.0

- Added NVIDIA GPU graphics and memory clocks with a session graphics-clock peak.
- Added NVIDIA GPU fan duty reporting, including multi-fan support where NVML exposes it.
- Added CPU fan RPM through compatible platform sensors, LibreHardwareMonitor/OpenHardwareMonitor WMI, and a limited Windows fallback.
- Added top GPU application reporting with NVIDIA process-engine utilization and a highest-VRAM fallback.
- Added dynamic high-level health cards for every Windows physical disk.
- Added native Windows Wi-Fi signal quality, estimated dBm, SSID, adapter, and link-rate reporting.
- Split battery time remaining into its own selectable card.
- Added a private, text-only, in-memory clipboard history for the current Desktop Metrics session, with a viewer and clear action.
- Added optional always-on-top behavior.
- Added click-through mode restricted to locked, always-on-top widgets, with permanent tray recovery controls.
- Added configuration migration for the new window behavior options and expanded release/collector tests.

## 1.7.2

- Reserved a permanent transparent scrollbar gutter in combined-widget mode to stop horizontal layout jitter as live cards update.
- Clarified portable-Python drag-and-drop and command-line build instructions.
- Kept the installer per-user/no-admin.

## 1.7.0

- Added a true one-file portable build with sidecar `DesktopMetricsData` configuration and logs.
- Added a per-user Inno Setup installer with startup, Start Menu, desktop shortcut, update, and uninstall integration.
- Added one-command Windows release scripts that accept installed or complete portable Python.
- Changed the installed build to PyInstaller one-folder mode for faster startup while retaining one-file mode for portable use.
- Unified the tray, window, portable EXE, installed EXE, setup, and uninstaller icons around the same multi-resolution ICO asset.
- Added Windows executable version resources.
- Added a named Windows mutex so Setup can detect a running tray instance before update or uninstall.
- Synchronized the in-app startup checkbox with the real per-user Windows startup registry entry.
- Explicitly preserved Qt per-monitor fractional DPI scaling and documented Full HD, 2K, and mixed-DPI behavior.
- Added portable configuration migration and release-related tests.

## 1.6.0

- Added an X button that hides an individual widget without stopping the tray app.
- Added combined-dashboard and one-window-per-metric layout modes.
- Added independent saved geometry for every separate metric window.
- Added dynamic all-volume storage cards.
- Added dynamic per-physical-disk read/write cards with Windows drive-letter mapping.
- Added selectable network adapters and an all-adapters mode.
- Changed the default network display to decimal Mbps/Kbps while retaining optional byte units.
- Reworked top CPU process sampling to exclude System Idle Process, use CPU-time deltas, normalize to whole-system percentage, and group identical executables.
- Reworked top memory reporting to group multi-process applications such as Chrome.
- Added friendly process names for common browsers, Explorer, and Python.
- Added boost-aware Windows CPU frequency sampling with current, nominal, and session-peak values.
- Added v1 configuration migration for separate-widget, network-unit, and adapter preferences.
- Added collector, dynamic-layout, formatting, configuration, and optional off-screen UI tests.

## 1.5.0

- Replaced Explorer/WorkerW parenting with a reliable normal non-topmost tool window.
- Removed native child-window coordinate conversion that caused invisible widgets and multi-monitor geometry warnings.
- Rebuilt metric selection as large `[ ]` / `[x]` checkable rows that remain visible across Windows and portable-Qt themes.
- Named presets now apply immediately when selected.
- Added Select all, Clear all, and a live selected-metric count.
- Applying or saving settings makes the widget visible.
- Tray Show explicitly reveals and activates the widget; Hide reliably hides it.
- Added screen-intersection recovery for stored positions that no longer touch a connected monitor.
- Forced Qt Fusion style for consistent controls.
- Added visible version labels to confirm which build is running.
