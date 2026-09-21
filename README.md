# Desktop Metrics v1.8.1

Desktop Metrics is a Windows-first monitoring widget written in Python and PySide6. It runs from the system tray, continuously refreshes the selected readings, and supports either one combined dashboard or a separate movable window for every metric.

By default, each widget is a normal frameless non-topmost tool window: regular applications can cover it, it does not occupy a normal taskbar button, and monitoring continues while it is hidden. Version 1.8 also adds optional always-on-top and safe click-through modes.

### v1.8.1 maintenance fixes

- Long sensor and process details are shortened with an ellipsis instead of widening the widget; hover the detail line to see the complete text.
- Unavailable CPU/GPU fan cards use compact messages while retaining the full diagnostic in a tooltip.
- Every metric card now has the same exact scaled height and equal-width grid behavior.
- The obsolete `pynvml` package warning is suppressed; NVIDIA monitoring continues to use the supported `nvidia-ml-py` dependency.

## What is new in v1.8

- Added current NVIDIA GPU graphics clock, memory clock, and the highest graphics clock observed during the current app session.
- Added NVIDIA GPU fan duty percentage, including multi-fan boards when NVML exposes individual fans.
- Added CPU fan RPM through compatible platform sensors. On Windows, Desktop Metrics can read LibreHardwareMonitor or OpenHardwareMonitor WMI sensors and uses a limited `Win32_Fan` fallback.
- Added a top GPU application card. It uses NVIDIA per-process engine utilization when supported and falls back to the application using the most VRAM.
- Added one high-level health card per Windows physical disk.
- Added connected Wi-Fi signal quality, estimated dBm, SSID, adapter name, and receive/transmit link rates through the native Windows WLAN API.
- Added battery time remaining as an independent selectable card.
- Added a private session clipboard-history card and viewer for copied text.
- Added optional always-on-top behavior.
- Added click-through mode for locked, always-on-top widgets, so windows and desktop controls underneath remain clickable.
- Kept click-through recoverable from the system tray and automatically disables it when topmost or lock is turned off.
- Retained the portable one-file EXE, per-user/no-admin installer, common application icon, combined/separate layouts, per-disk I/O, adapter selection, process grouping, and Full HD/2K scaling support.

## Upgrade from an older version

1. Right-click the old Desktop Metrics tray icon and choose **Quit**. Only one instance can run at a time.
2. Extract v1.8 into a new folder rather than merging it into an older source folder.
3. Run `setup_portable.bat`, `setup_and_run.bat`, or `main.py`.
4. Open Settings and confirm the heading says **Desktop Metrics v1.8.1**.

Existing AppData settings are migrated automatically. The portable EXE also imports an existing AppData configuration once when no portable configuration exists yet. The new always-on-top and click-through options default to off. Clipboard contents are never migrated or stored in the configuration.

## Selecting metrics

Open **Settings -> Metrics**.

- An unselected row begins with `[ ]`.
- A selected row begins with `[x]` and has a blue background.
- Choosing **Minimal**, **Gaming**, **Workstation**, or **Everything** updates the selected rows immediately.
- Manually changing a row changes the preset to **Custom**, unless the exact selection matches another preset.
- Press **Apply** or **Save and close** to save the selection and show the widget.

The storage options are expandable:

- **System disk space**: one card for the Windows system volume.
- **All disk space**: one card for every accessible mounted volume.
- **Total disk read / write**: one combined throughput card.
- **Per-disk read / write**: one throughput card for every physical disk reported by the operating system.
- **Physical disk health**: one high-level Windows health-status card for every physical disk.

## Combined or separate widgets

Open **Settings -> Appearance and behavior -> Widget layout**.

Leave **Show every metric in its own movable and resizable widget** unchecked to keep the combined dashboard. Enable it to create an independent window for every selected metric. Expandable storage selections also split into one window per volume or physical disk, and every window remembers its own geometry.

Use the tray command **Reset widget positions** to arrange all separate windows on the primary screen.

## Widget controls

- Drag the header to move an unlocked widget.
- Drag the bottom-right grip to resize it.
- Press **X** to hide only that widget.
- Double-click the header to open Settings.
- Double-click the Clipboard history card to open its viewer.
- Right-click a widget for Settings, lock, always-on-top, click-through, reset, hide, and quit commands.
- Left-click the tray icon to show or hide the active widget layout.
- Double-click the tray icon to open Settings.
- Use **Lock position and size** after arranging the windows.

The collector continues refreshing while the windows are hidden. The refresh interval can be 0.5, 1, 2, or 5 seconds.

## Always on top and click-through

Open **Settings -> Appearance and behavior** or use the tray menu.

- **Always on top** keeps every active Desktop Metrics widget above normal application windows.
- **Lock widgets** prevents moving and resizing them.
- **Click-through** passes mouse input to the application, icon, or desktop underneath the widget.

For safety, click-through is available only when both **Always on top** and **Lock widgets** are enabled. Disabling either prerequisite automatically disables click-through. While click-through is active, use the tray menu to hide the widgets or turn the mode off; the on-widget X button cannot receive clicks.

These settings are global: in separate-widget mode they apply to all metric windows.

## Clipboard history privacy

The Clipboard history metric is intentionally private and limited:

- It records only text copied after the metric is enabled and while Desktop Metrics remains running.
- It keeps at most 20 unique entries in memory.
- It does not read or replace the full Windows `Win+V` history.
- It does not save clipboard text to `config.json`, logs, or any other file.
- Disabling the metric or quitting Desktop Metrics clears the entries.
- Extremely large copied text is truncated to keep the viewer responsive.

Use the tray menu or double-click the card to open the viewer. The viewer can copy an entry back to the clipboard or clear all entries.

## Network units and adapter selection

`psutil` supplies cumulative network counters in bytes. Desktop Metrics calculates the change between refreshes.

The default display is:

```text
Receive 8.80 Mbps
Send 104 Kbps | Ethernet
```

This is approximately the same data rate as:

```text
Receive 1.1 MB/s
Send 13 KB/s
```

To use byte units, select **MB/s / KB/s** in Settings.

Automatic adapter mode prefers an active physical Ethernet or Wi-Fi adapter and avoids rapidly jumping between adapters while traffic is low. When comparing against Task Manager, select the same named adapter in Desktop Metrics. Choose **All adapters combined** only when you intentionally want traffic summed across every interface.

The Wi-Fi signal card is separate from traffic speed. It shows the strongest currently connected Windows Wi-Fi interface and its link information; it is unavailable while using Ethernet only or when Windows reports no connected WLAN interface.

## CPU frequency and fan notes

On Windows, `psutil.cpu_freq()` commonly exposes the nominal clock rather than the current boosted clock. Desktop Metrics therefore queries Windows Processor Information performance counters and estimates the live effective clock from the nominal frequency and processor-performance percentage. The card shows:

- current live frequency;
- nominal frequency;
- highest frequency observed during the current Desktop Metrics session.

Frequency reporting is best-effort because firmware, power plans, virtualization, hybrid-core scheduling, and hardware-monitoring utilities can use different averaging methods. Small differences from Task Manager or a motherboard utility are normal.

CPU fan RPM is not exposed through one universal Windows API. For the most reliable result, run LibreHardwareMonitor or OpenHardwareMonitor with its WMI sensor provider enabled. Desktop Metrics will show `Unavailable` when it cannot identify a CPU-labelled fan. The Windows sensor query is cached so it does not launch an expensive hardware query every one-second UI refresh.

## GPU notes

NVIDIA cards are monitored through NVML using the installed NVIDIA driver. AMD and Intel GPU monitoring are not implemented in this release; their GPU cards show `Unavailable`, while non-GPU monitors continue working.

- GPU graphics clock shows the current clock and the highest value observed during the current Desktop Metrics session.
- GPU fan speed is the NVML fan duty percentage, not fan RPM.
- Some laptops, passively cooled boards, and driver/GPU combinations do not expose fan data.
- Top GPU app uses process engine utilization when the driver exposes it. If that query is unsupported, Desktop Metrics falls back to the process group using the most VRAM and labels the result accordingly.
- Multi-process applications are grouped by executable name where possible.

## Disk health notes

Physical disk health uses the high-level status exposed by Windows Storage (`Healthy`, `Warning`, `Unhealthy`, or another vendor/driver status). If the Storage provider is unavailable, Desktop Metrics uses a simpler Windows disk status fallback.

This card is not a complete SMART attribute, SSD wear, temperature, or remaining-life analyzer. A healthy result means Windows currently reports the disk as healthy; it is not a backup guarantee.

## Process-monitor notes

The process cards need two samples to calculate CPU use, so **Top CPU app** may show a warm-up message for one refresh.

- `System Idle Process` is excluded.
- CPU use is calculated from process CPU-time changes and normalized to the whole-PC 0-100% scale.
- Processes with the same executable name are grouped.
- Browser helper processes are combined, so Chrome appears as **Google Chrome** rather than one arbitrary `chrome.exe` process.
- Top memory uses combined resident/working-set memory. Task Manager can still differ slightly because its grouping and memory definitions vary by view and Windows version.

## Battery notes

The normal Battery card shows charge and plugged-in state. **Battery time remaining** is a separate card based on the operating-system estimate. The value can change quickly with workload, display brightness, charging state, and battery firmware. It shows `Unavailable` when the computer has no battery or Windows does not provide an estimate.

## Included monitors

- Date and time and PC uptime
- CPU usage, boost-aware frequency, temperature when exposed, and CPU fan RPM when exposed
- RAM and swap/page-file usage
- NVIDIA GPU usage, VRAM, temperature, power, graphics/memory clocks, fan duty, and top GPU application
- System-volume space and all-volume space
- Total disk throughput and per-physical-disk read/write throughput
- High-level health status for every Windows physical disk
- Network receive/send rate and totals
- Connected Wi-Fi signal, estimated dBm, SSID, interface, and link rates
- Process count, top CPU application, and top memory application
- Battery charge/state and battery time remaining
- Private in-memory text clipboard history for the current session

Unsupported hardware readings display `Unavailable` without stopping other metrics.

## Run with installed Python

Desktop Metrics supports 64-bit Python 3.10 through 3.14.

From Command Prompt inside the project folder:

```bat
python -m pip install -r requirements.txt
python main.py
```

Or double-click `setup_and_run.bat`. It creates a local `.venv`, installs dependencies, and launches the app. Later launches can use `run.bat`.

## Run with portable Python 3.11

Drag your portable `python.exe` onto `setup_portable.bat`. The launcher stores the interpreter path, installs dependencies, and starts Desktop Metrics.

For later launches, double-click `run_portable.bat`.

Manual example:

```bat
"D:\PortablePython311\python.exe" -m pip install -r requirements.txt
"D:\PortablePython311\python.exe" main.py
```

If the portable distribution includes `venv`, `setup_portable.bat` creates a local `.venv`. If it lacks `venv` but has working pip, dependencies are installed into the portable interpreter. Python's minimal embeddable ZIP is not a supported pip environment.

## Configuration and logs

The source and installed versions store their per-user files in:

```text
%APPDATA%\DesktopMetrics
```

The true portable EXE stores them beside itself instead:

```text
DesktopMetrics-Portable-v1.8.1.exe
DesktopMetricsData\
    config.json
    desktop_metrics.log
    DesktopMetrics.lock
```

Keep the EXE and `DesktopMetricsData` folder together when moving the portable copy. The destination folder must be writable. Clipboard text is not stored in either location.

## Build the portable EXE and installer

Windows executables must be built on Windows. Drag a complete 64-bit Python 3.10-3.14 `python.exe` onto:

```text
build_release.bat
```

A normal installed Python also works by double-clicking the script. It creates an isolated `.build-venv`, installs the build dependencies, and produces:

```text
release\DesktopMetrics-Portable-v1.8.1.exe
release\DesktopMetrics-Setup-v1.8.1.exe
```

The portable EXE is self-contained and does not require Python on the destination PC.

The installer requires **Inno Setup 6** on the build PC. If it is not installed, the portable EXE is still completed; install Inno Setup and then run:

```text
build_installer.bat
```

The installer is per-user, so normal installation does not require administrator rights. Its startup checkbox writes the same current-user startup entry controlled by the app's **Start with Windows** setting.

`build_windows.bat` remains a compatibility shortcut to `build_release.bat`. See `BUILDING.md` for the complete release procedure.

## Full HD, 2K, and mixed-DPI monitors

Desktop Metrics uses Qt 6 Widgets, so Windows display scaling is applied automatically per monitor. A monitor set to 125% or 150% receives the corresponding Qt device-pixel ratio, and moving the widget between differently scaled monitors triggers per-monitor scaling. The application also uses a multi-resolution 16-256 px icon so icons remain sharp.

Resolution and Windows scale are different settings. At 100% Windows scale, the saved default window remains approximately `620 x 480` logical pixels on both Full HD and 2K displays. It therefore occupies a larger percentage of a 1920 x 1080 desktop than of a 2560 x 1440 desktop, but its text and controls do not become blurry or clipped. Resize the widget normally, or use **Settings -> Appearance and behavior -> Interface scale**:

- `100%` is the normal default.
- `85-90%` is a useful compact setting on many Full HD screens.
- `75%` is the smallest supported interface scale.

The Interface scale is an extra preference applied after Windows display scaling; it is not a replacement for the Windows scale setting.

## Troubleshooting

### The new version appears not to start

An older tray instance is probably still running. Open the Windows notification area, right-click Desktop Metrics, choose **Quit**, and then start v1.8. The Settings title must show `v1.8.1`.

### The widget is hidden or click-through prevents interaction

Use the tray menu and choose **Show widget** or **Show widgets**. The tray also lets you disable **Click through**, unlock the widgets, or disable **Always on top**. Applying Settings reveals the selected layout.

### A fan, GPU, disk-health, Wi-Fi, or battery-time card is unavailable

That provider is not exposed by the current hardware, driver, Windows service, or sensor backend. Read the matching notes above. Unsupported cards do not stop the rest of the monitor.

### The process cards look wrong immediately after startup

Wait for the second refresh. CPU and some GPU rates require an earlier sample. Also make sure you are comparing the same Task Manager view: Desktop Metrics groups identical executable names.

### Network speed differs by about eight times

Check the selected unit. `1 MB/s` is approximately `8 Mbps`; they are different units for the same transfer rate. Desktop Metrics defaults to Mbps/Kbps.

### Network speed still differs noticeably

Select the same adapter that Task Manager is displaying. VPNs, Hyper-V, WSL, Docker, virtual switches, and simultaneous Ethernet/Wi-Fi connections can cause aggregate and per-adapter values to differ.

### Per-disk I/O is unavailable on Windows

Open an Administrator Command Prompt and run:

```bat
diskperf -y
```

Restart Desktop Metrics afterward. Some Windows systems do not expose per-disk performance counters until disk performance collection is enabled.

### Theme colors look wrong

Desktop Metrics forces Qt's Fusion style and explicitly styles its controls. This avoids white-on-white controls caused by some Windows and portable-Qt theme combinations.
