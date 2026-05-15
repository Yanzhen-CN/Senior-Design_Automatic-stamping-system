# Automatic Stamping System

自动盖章机控制项目。主框架是一条线：

```text
Frontend target rule / relative position
USB camera snapshot
Paper / text / target detection
Pixel -> paper mm -> machine mm
Python generates G-code
Serial sends G-code to Arduino / GRBL
XY move -> Z press -> Z reset -> paper feed
```

## Quick Start

Create or update the `SD` conda environment:

```cmd
scripts\setup_env.bat
```

Run in browser mode:

```cmd
scripts\run_web.bat
```

Then open:

```text
http://127.0.0.1:8000
```

Run as a desktop window:

```cmd
scripts\run_app.bat
```

Build a Windows exe:

```cmd
scripts\build_exe.bat
```

Output:

```text
desktop\pywebview\dist\AutomaticStampingSystem.exe
```

The built exe does not require the target user to install Python or conda.

## Operating Modes

Mode A - first physical sheet teaches the position:

```text
Load first sheet -> Camera -> Detect Paper -> click stamp point -> Confirm Camera Position
```

The confirmed point is stored as a paper-relative coordinate, such as `0.78, 0.84`. Later sheets reuse that same relative point. Before each move/stamp, the app can detect the current sheet and convert that relative point to the current machine coordinate.

Mode A cycle automation (Target tab):

```text
Feed sheet -> capture before frame -> detect paper -> stamp -> return X0Y0
capture after frame -> detect red stamp offset -> update compensation memory
```

Available Mode A controls:

```text
Batch cycles
Comp gain
Feed before / feed after
Apply learned compensation
Run One Cycle / Run Batch
Reset Compensation
```

Mode B - uploaded A4 file teaches the position:

```text
Upload PDF/image -> click stamp point on document preview -> Confirm File Position
```

The clicked file coordinate is also stored as an A4-relative coordinate. When a real sheet is placed in the machine, the app detects the physical sheet and maps the saved file-relative coordinate to machine coordinates.

Both modes use the same fine-tuning controls:

```text
Preview Job -> Move Job Slow -> Jog X/Y/Z if needed -> Dry Stamp Job -> Live Stamp Job
```

For DOCX files, export or print them to PDF first, then upload the PDF.

## Camera Setup From Frontend

Normal users do not need to edit code or `machine.toml`.

Use the `Camera` tab:

```text
Scan Cameras
Select USB camera
Set resolution and camera-to-plane distance
Apply Camera
Camera
Click each visible anchor in the camera image
Use Clicked Pixel
Next Anchor
Save Calibration
Test Clicked Point
```

The `Advanced` tab keeps low-level machine parameters available for developers, but daily stamping should use `Target`, `Motion`, and `Camera`.

## Main Files

```text
config/machine.toml                    Machine, camera, serial, calibration config
web/                                   Frontend control panel
src/stamping_system/                   Python backend
src/stamping_system/documents.py        PDF/image upload preview support
desktop/pywebview/app.py               Desktop window entry
desktop/pywebview/AutomaticStampingApp.spec
scripts/setup_env.bat                  Create/update SD environment
scripts/run_web.bat                    Run local web controller
scripts/run_app.bat                    Run desktop app from SD environment
scripts/build_exe.bat                  Build final Windows exe
docs/system_notes.md                   Calibration and camera notes
arduino/stamping_controller.ino         Optional custom Arduino protocol
```

## Calibration Notes

Camera height is stored in config, but accurate positioning needs four-point calibration. The frontend writes these values into `config/machine.toml`:

```text
calibration.points[*].pixel
calibration.points[*].real_mm
```

Stepper correction uses:

```text
actual_mm_per_commanded_mm = measured_mm / commanded_mm
```

Example: command 100 mm, measure 98.6 mm, set `0.986`.

## Hardware Notes

- Default serial mode is dry-run: `serial.dry_run = true`.
- A fixed overhead USB camera is recommended.
- If the stamp head blocks the target, lock the target before moving, then use slow move / jog feedback before pressing.
- CNCjs can still be used for early GRBL movement debugging; this project replaces it for camera-based automatic stamping.
