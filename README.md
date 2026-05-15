# Automatic Stamping System

Automatic stamping controller for the modified writing robot / GRBL frame.

Main pipeline:

```text
Frontend selects/teaches stamp target
Camera or simulation image provides the current paper view
Document / camera position is mapped to a stamp target
Python generates G-code
Serial sends G-code to Arduino / GRBL
XY move -> Z press -> Z reset -> paper feed
```

## Quick Start

Run these commands from the project root:

```cmd
cd /d D:\Personal\Desktop\SD\Automatic-stamping-system
```

Create or update the `SD` conda environment:

```cmd
scripts\setup_env.bat
```

Start the desktop app:

```cmd
scripts\run_app.bat
```

For browser debugging:

```cmd
scripts\run_web.bat
```

Open:

```text
http://127.0.0.1:8000
```

Build a Windows exe:

```cmd
scripts\build_exe.bat
```

Output:

```text
desktop\pywebview\dist\AutomaticStampingSystem.exe
```

## Main Modes

### Mode A - Manual Teach

Use Motion to move the stamp head to the desired physical position, then confirm and repeat.

```text
Move with Motion -> Confirm Current Position -> Run
```

### Mode B - Camera Teach

Use the live camera or camera simulation image. Click the target on the camera view, confirm, then repeat.

```text
Feed first sheet -> click camera target -> Confirm Camera Position -> Run
```

### Mode C - A4 File Teach

Upload an A4 PDF/image. The file preview is shown on the main screen automatically. Click the file target, then confirm.

```text
Choose A4 file -> click file target -> Confirm File Position
Camera/simulation view returns -> Debug Run or Run
```

`Debug Run` matches the uploaded document preview against the current camera/simulation image with OpenCV, maps the selected file point into the camera image, and draws a red target dot. If the target is outside the Stamp Region, the UI shows a warning.

## Camera And Simulation

Use `Camera On` for a USB camera.

Use `Camera Simulation` to upload a photo as a fake camera frame. Simulation supports rotation before confirmation. When simulation is active, all modes use the simulation image instead of the live camera.

## Setup Workflow

Developer setup is done from the frontend:

```text
Camera:
  Set camera source/resolution
  Set Stamp/Detect Region

Motion:
  Connect GRBL controller
  Set Workspace Bounds
  Set Stamp Region XY Alignment
  Set Paper Roller A4 Alignment

Advanced:
  Serial settings
  Motion distance calibration
  Camera calibration fallback
  Firmware flashing
```

Daily operation should mainly use the `Target` tab after setup is saved.

## Key Calibration Concepts

`Stamp/Detect Region` is the usable camera region for recognition and stamping. It is drawn as a red rectangle on the camera image and saved to `config/machine.toml`.

`Stamp Region XY Alignment` maps the camera region corners to machine XY coordinates. Move the stamp head to each matching region corner and click `Align Machine Corner`.

`Paper Roller A4 Alignment` is reserved for the fourth-axis paper feed. Set `A0`, feed one A4 sheet length, set `A1`, then save. The measured A0-A1 distance becomes the default feed length.

## Hardware Notes

- The current GRBL board handles XYZ.
- The paper roller interface is reserved through the frontend and backend.
- A separate controller for the independent roller is recommended if UNO/GRBL does not expose a clean fourth-axis interface.
- Use a powered USB hub if the camera, GRBL board, and roller controller need to share one PC USB port.
- A spring-loaded stamp head is recommended so Z can press against a compliant mechanism instead of hard-stalling the motor.

## Main Files

```text
config/machine.toml                    Machine, camera, serial, region config
web/                                   Frontend control panel
src/stamping_system/                   Python backend
src/stamping_system/document_matching.py Mode C document-camera matching
src/stamping_system/documents.py        PDF/image upload preview
desktop/pywebview/app.py               Desktop window entry
scripts/setup_env.bat                  Create/update SD environment
scripts/run_app.bat                    Run desktop app
scripts/run_web.bat                    Run browser debug server
scripts/build_exe.bat                  Build Windows exe
docs/run_instructions.md               Short run instructions
```

## Notes

For DOCX files, export to PDF first, then upload the PDF.

CNCjs can still be used for low-level GRBL debugging. This project replaces CNCjs for camera-based automatic stamping workflows.
