# System Notes

## Why Four-Point Calibration Is Still Needed

Camera-to-plane distance is useful for recording the mechanical setup, but it is not enough to map image pixels to machine millimeters.

The real transform also depends on:

- Camera lens distortion.
- Camera tilt.
- Camera horizontal offset.
- Paper plane not being perfectly parallel to the image sensor.
- The actual machine coordinate origin.

The app therefore uses four reference marks and a homography transform:

```text
image pixel (u, v) -> real machine coordinate (X, Y) in mm
```

Recommended four marks:

```text
mark_top_left      real_mm = [0, 0]
mark_top_right     real_mm = [machine_width, 0]
mark_bottom_right  real_mm = [machine_width, machine_height]
mark_bottom_left   real_mm = [0, machine_height]
```

The frontend lets you click each mark in the camera view and store its pixel coordinate.

## Camera Occlusion By The Stamp Head

With only one fixed overhead camera, the stamp axis/head may cover the target when it moves above the stamping point.

This does not prevent accurate positioning if the workflow is staged:

1. Capture the paper while the head is away from the target.
2. Detect the paper or target area.
3. Lock the target machine coordinate.
4. Move XY to that coordinate.
5. Press Z.

For fine tuning, use:

- `Move Slow` to approach the target at low speed.
- Jog buttons to correct X/Y/Z.
- Refresh the camera after each jog.
- Keep Z lifted during visual feedback.

If you need visual feedback exactly at the stamping contact moment, use a second side camera or an offset camera that is not blocked by the stamp head.

## GRBL / CNCjs Compatibility

The writing robot package contains GRBL and CNCjs. This project keeps the same GRBL-style command flow:

```text
G21
G90
G0 X... Y... F...
G1 Z... F...
G4 P...
```

CNCjs can still be used for early manual movement debugging. This app replaces CNCjs for the automatic workflow because it adds:

- Camera snapshot.
- Paper/target detection.
- Pixel-to-machine calibration.
- Frontend editable machine config.
- Low-speed visual feedback.
- Stamping and paper-feed sequence.

For GRBL, `ok` means the line was parsed/accepted, so the backend can optionally poll `?` until GRBL reports `<Idle...>`.

## Serial Connection Flow

The frontend now follows the same first step as CNCjs: establish a controller connection before manual motion.

```text
Motion tab
Scan Ports
Select the GRBL COM port
Set baudrate, usually 115200
Uncheck Dry run for live motion
Connect
Unlock $X if needed
Status ? should show Idle before jogging
```

Internally the backend keeps the serial port open after `Connect`, so jog, slow move, and stamp commands reuse the same GRBL session. If the port is not connected and live motion is requested, the backend reports:

```text
Serial is not connected. Use Motion -> Connect first.
```

This is intentional; it avoids the confusing behavior where a command appears to run but GRBL was never put into a CNCjs-style connected/unlocked state.

Manual jog has two frontend behaviors:

```text
Short click -> normal relative G91 fixed-distance jog
Press and hold -> GRBL $J=G91 continuous jog segment
Release -> GRBL realtime jog cancel, byte 0x85
```

The continuous jog command is sent in bounded segments and refreshed while the button remains pressed. This gives CNCjs-style hold movement while keeping the explicit release-to-stop behavior.

The paper roller is still independent from XYZ motion logic even when it is driven by the same Uno board:

```text
Forward command defaults to M100
Reverse command defaults to M101
```

The Motion tab exposes both commands directly for paper in/out testing.

## Firmware Flash

Advanced includes a firmware flash panel for development and recovery:

```text
Select COM port
Board preset (Uno or Mega)
HEX path
Flash via avrdude
```

Default profile targets Uno (ATmega328P) and points to a project-local hex:

```text
firmware/grbl3axis.hex
```

You can also upload a custom `.hex` from the frontend and flash that uploaded file.

## Stepper Calibration

For a 42 stepper motor:

```text
theoretical_steps_per_mm =
  motor_steps_per_rev * microsteps / (pulley_teeth * belt_pitch_mm)
```

Example:

```text
200 * 16 / (20 * 2) = 80 steps/mm
```

This theoretical number is a starting point. The frontend has an Axis Scale tool:

```text
actual_mm_per_commanded_mm = measured_mm / commanded_mm
```

Example:

```text
Commanded 100 mm, measured 98.6 mm
actual_mm_per_commanded_mm = 0.986
```

The backend uses this ratio when generating corrected G-code.

## USB Camera Before Purchase

The config assumes a generic external USB camera:

```toml
[camera]
index = 0
width_px = 1920
height_px = 1080
height_mm = 420.0
mount = "fixed_overhead_usb"
```

When the camera is not connected, the backend returns a placeholder image so the frontend workflow can still be tested.

## Mode A And Mode B

Mode A is for many identical physical sheets:

```text
First sheet enters the machine
Camera captures it
User clicks the stamp point
Confirm Camera Position stores rx, ry
Every later sheet uses the same rx, ry
```

Mode B is for file-based teaching:

```text
User uploads an A4 PDF/image
User clicks the stamp point on the document preview
Confirm File Position stores rx, ry
Every physical sheet maps that rx, ry to the current detected paper
```

Both modes reduce to the same target representation:

```text
paper-relative coordinate: rx, ry in [0, 1]
```

Before a job is previewed, moved, or stamped, the frontend asks the backend to detect the current physical paper. If detection succeeds, the current paper quadrilateral is used. If detection fails, the static paper origin from `config/machine.toml` is used as a fallback.

## Frontend-Only Camera Setup

The operator should not need to edit code or config files for normal camera setup.

Use the Camera tab:

```text
Scan Cameras
Select camera index
Set width / height / camera-to-plane distance
Apply Camera
Capture frame
Click each anchor
Use Clicked Pixel
Save Calibration
Test Clicked Point
```

The saved values are written to:

```text
[camera]
index
width_px
height_px
height_mm

[[calibration.points]]
pixel
real_mm
```

For the first implementation, anchor clicking is manual because it is the most predictable. Later, ArUco/AprilTag auto-detection can be added as an assistive button, but manual clicking should remain as a fallback.
