# Building Desktop Metrics v1.8.1 for Windows

The release build has two targets:

1. `DesktopMetrics-Portable-v1.8.1.exe` — one self-contained EXE. No Python installation is required on the destination computer. Its settings live in `DesktopMetricsData` beside the EXE.
2. `DesktopMetrics-Setup-v1.8.1.exe` — a normal per-user installer. It creates a Start Menu shortcut, supports uninstall, can create a desktop shortcut, and can start the app when the user signs in.

Both targets use `assets\desktop_metrics.ico`, which is also the tray icon. The ICO contains 16, 24, 32, 48, 64, 128, and 256 pixel images.


## Exactly how to drag portable Python onto the builder

In Windows File Explorer, open the folder containing `build_release.bat` in one window and the folder containing your portable `python.exe` in another. Click and hold `python.exe`, drag it directly on top of the `build_release.bat` file icon/name, then release the mouse button. Windows starts the batch file and passes the Python path as its first argument.

You can do exactly the same thing from Command Prompt without dragging:

```bat
"C:\Path\To\DesktopMetrics\build_release.bat" "D:\PortablePython311\python.exe"
```

The generated Desktop Metrics installer is already per-user and does not require administrator rights. It installs under `%LOCALAPPDATA%\Programs\Desktop Metrics`.

## Requirements on the build PC

- 64-bit Windows 10 or Windows 11
- Complete 64-bit Python 3.10 through 3.14, including pip; a complete portable Python 3.11 is supported
- Internet access during the first build so pip can install build dependencies
- Inno Setup 6 to compile the installer

Python and Inno Setup are build-time requirements only. Neither is required on computers that run the finished portable EXE or installer.

## One-command release build

Place the project in a writable folder. Then either:

- double-click `build_release.bat` when a normal Python installation is available; or
- drag a complete portable `python.exe` onto `build_release.bat`.

The script:

1. validates the Python version and architecture;
2. creates `.build-venv` when `venv` is available;
3. installs `requirements-build.txt`;
4. builds the one-file portable EXE;
5. builds the faster one-folder application used by Setup;
6. compiles the installer when Inno Setup 6 is available.

Finished files are placed in:

```text
release\DesktopMetrics-Portable-v1.8.1.exe
release\DesktopMetrics-Setup-v1.8.1.exe
```

Intermediate PyInstaller output is placed in `build` and `dist`.

## Build the installer later

If Inno Setup was missing during the first build, the portable EXE is still completed. After installing Inno Setup 6, run:

```text
build_installer.bat
```

The installer definition is `installer\DesktopMetrics.iss`.

## Optional Inno Setup code signing

Unsigned personal builds work, but Windows can display an Unknown publisher or SmartScreen warning. Signing requires a code-signing certificate and Microsoft `signtool.exe`. The project leaves signing disabled by default so a builder without a certificate can still compile the installer.

In Inno Setup Compiler, open **Tools -> Configure Sign Tools**, add a tool named `DesktopMetricsSign`, and use a command similar to:

```text
"C:\Program Files (x86)\Windows Kits\10\bin\<SDK version>\x64\signtool.exe" sign /a /n "Desktop Metrics" /fd SHA256 $f
```

Use the real certificate subject and SDK path on the build PC. Then open `installer\DesktopMetrics.iss` and uncomment these two lines in `[Setup]`:

```ini
SignTool=DesktopMetricsSign
SignedUninstaller=yes
```

Compile again with `build_release.bat` or `build_installer.bat`. Inno Setup will invoke the configured Sign Tool for Setup and its generated uninstaller. A self-signed certificate is useful only on computers where that certificate has been explicitly trusted; public distribution normally needs a certificate trusted by Windows.

## Installed behavior

The installer uses this per-user location:

```text
%LOCALAPPDATA%\Programs\Desktop Metrics
```

No administrator elevation is required for the normal install. The startup option is selected by default and writes:

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run\DesktopMetrics
```

The app reads that entry at startup, so the Settings checkbox stays synchronized with the installer choice. Uninstall removes the startup entry and program files but intentionally keeps user preferences in `%APPDATA%\DesktopMetrics`.

## Portable behavior

The portable build creates:

```text
DesktopMetrics-Portable-v1.8.1.exe
DesktopMetricsData\
```

Move both together to retain settings. The folder containing the portable EXE must be writable. On its first launch, the portable build imports an existing `%APPDATA%\DesktopMetrics\config.json` when no local portable config exists.

## DPI and monitor scaling

Qt 6 applies Windows per-monitor scaling automatically. Desktop Metrics also explicitly uses the pass-through rounding policy for fractional settings such as 125%, 150%, and 175%.

The application uses logical pixels. At identical 100% Windows scale, a `620 x 480` widget has the same logical dimensions on Full HD and 2K displays, so it occupies more of the Full HD desktop. Use the in-app Interface scale slider or resize the window when a more compact layout is preferred.

## Icon and version resources

- Runtime tray/window icon: `assets\desktop_metrics.ico`
- Portable EXE icon: the same ICO through PyInstaller
- Installed EXE icon: the same ICO through PyInstaller
- Setup/uninstaller icon: the same ICO through Inno Setup
- Windows file metadata: `packaging\version_info_portable.txt` and `packaging\version_info_installed.txt`

## Updating the version

Before a future release, update all of these values together:

- `APP_VERSION` in `desktop_metrics\constants.py`
- `APP_VERSION` in `build_release.bat`
- version fields in both files under `packaging`
- version defines in `installer\DesktopMetrics.iss`
- README and changelog headings

The Inno Setup `AppId` must remain unchanged so upgrades use the same installed application identity.

The release builder uses Windows CRLF line endings and avoids batch subroutines for Python commands, preserving compatibility with normal and portable Python paths.
