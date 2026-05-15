from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .config import AppConfig
from .runtime_bounds import get_runtime_bounds


@dataclass
class SerialResult:
    dry_run: bool
    sent_lines: list[str]
    responses: list[str] = field(default_factory=list)
    port: str | None = None


def list_serial_ports() -> list[dict[str, object]]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []

    ports: list[dict[str, object]] = []
    for item in list_ports.comports():
        ports.append(
            {
                "device": item.device,
                "name": item.name,
                "description": item.description,
                "hwid": item.hwid,
                "manufacturer": getattr(item, "manufacturer", None),
                "serial_number": getattr(item, "serial_number", None),
                "vid": getattr(item, "vid", None),
                "pid": getattr(item, "pid", None),
            }
        )
    return ports


class SerialConnectionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._port: Any | None = None
        self._config: AppConfig | None = None
        self._last_status = "disconnected"
        self._last_responses: list[str] = []
        self._last_report: str | None = None
        self._last_position: dict[str, object] = {}

    def status(self, config: AppConfig | None = None) -> dict[str, object]:
        cfg = config or self._config
        with self._lock:
            connected = self._is_open()
            port_name = cfg.serial.port if cfg else None
            baudrate = cfg.serial.baudrate if cfg else None
            dry_run = cfg.serial.dry_run if cfg else False
            if connected and self._port is not None:
                port_name = getattr(self._port, "port", port_name)
                baudrate = getattr(self._port, "baudrate", baudrate)
            state = "connected" if connected else self._last_status
            if dry_run and not connected:
                state = "dry-run"
            return {
                "connected": connected,
                "state": state,
                "port": port_name,
                "baudrate": baudrate,
                "dry_run": dry_run,
                "last_responses": self._last_responses[-8:],
                "status_report": self._last_report,
                "position": self._last_position,
            }

    def connect(self, config: AppConfig) -> SerialResult:
        with self._lock:
            self._close_open_port()
            self._config = config

            if config.serial.dry_run:
                return self._remember(
                    SerialResult(
                        dry_run=True,
                        sent_lines=[],
                        responses=["dry-run: serial connection skipped"],
                        port=config.serial.port,
                    ),
                    "dry-run",
                )

            try:
                import serial
            except ImportError as exc:
                raise RuntimeError("pyserial is required for serial execution") from exc

            self._port = serial.Serial(
                config.serial.port,
                config.serial.baudrate,
                timeout=config.serial.timeout_s,
            )
            responses: list[str] = []
            if config.controller.type == "grbl":
                self._port.write(b"\r\n\r\n")
                time.sleep(2.0)
                responses.extend(_read_available(self._port))
                self._port.reset_input_buffer()

            if not responses:
                responses.append("serial connected")

            return self._remember(
                SerialResult(
                    dry_run=False,
                    sent_lines=[],
                    responses=responses,
                    port=config.serial.port,
                ),
                "connected",
            )

    def disconnect(self) -> SerialResult:
        with self._lock:
            port_name = self._current_port_name()
            self._close_open_port()
            self._last_status = "disconnected"
            result = SerialResult(
                dry_run=False,
                sent_lines=[],
                responses=["serial disconnected"],
                port=port_name,
            )
            self._last_responses = result.responses
            return result

    def execute(self, lines: list[str], config: AppConfig | None = None) -> SerialResult:
        cfg = config or self._config
        if cfg is None:
            raise RuntimeError("Serial is not configured")

        with self._lock:
            if cfg.serial.dry_run:
                return self._remember(
                    SerialResult(
                        dry_run=True,
                        sent_lines=lines,
                        responses=["dry-run: serial disabled"],
                        port=cfg.serial.port,
                    ),
                    "dry-run",
                )
            if not self._is_open() or self._port is None:
                raise RuntimeError("Serial is not connected. Use Motion -> Connect first.")

            responses: list[str] = []
            for line in lines:
                responses.extend(_send_line(self._port, line, cfg))
                if (
                    cfg.controller.type == "grbl"
                    and cfg.controller.wait_for_idle
                    and _is_motion_command(line)
                ):
                    responses.extend(_wait_until_idle(self._port, cfg))

            return self._remember(
                SerialResult(
                    dry_run=False,
                    sent_lines=lines,
                    responses=responses,
                    port=self._current_port_name(),
                ),
                "connected",
            )

    def unlock(self, config: AppConfig | None = None) -> SerialResult:
        cfg = config or self._config
        if cfg is None:
            raise RuntimeError("Serial is not configured")
        return self.execute(["$X"], cfg)

    def query_status(self, config: AppConfig | None = None) -> SerialResult:
        cfg = config or self._config
        if cfg is None:
            raise RuntimeError("Serial is not configured")

        with self._lock:
            if cfg.serial.dry_run:
                return self._remember(
                    SerialResult(
                        dry_run=True,
                        sent_lines=["?"],
                        responses=["dry-run: status query skipped"],
                        port=cfg.serial.port,
                    ),
                    "dry-run",
                )
            if not self._is_open() or self._port is None:
                raise RuntimeError("Serial is not connected. Use Motion -> Connect first.")

            # Drop stale buffered lines quickly (for example trailing "ok") before requesting fresh status.
            _drain_available(self._port)
            self._port.write(b"?")
            query_timeout = min(float(cfg.serial.timeout_s), 0.35)
            responses = _read_until_status_response(self._port, query_timeout)
            return self._remember(
                SerialResult(
                    dry_run=False,
                    sent_lines=["?"],
                    responses=responses,
                    port=self._current_port_name(),
                ),
                "connected",
            )

    def reset(self, config: AppConfig | None = None) -> SerialResult:
        cfg = config or self._config
        if cfg is None:
            raise RuntimeError("Serial is not configured")

        with self._lock:
            if cfg.serial.dry_run:
                return self._remember(
                    SerialResult(
                        dry_run=True,
                        sent_lines=["soft-reset"],
                        responses=["dry-run: reset skipped"],
                        port=cfg.serial.port,
                    ),
                    "dry-run",
                )
            if not self._is_open() or self._port is None:
                raise RuntimeError("Serial is not connected. Use Motion -> Connect first.")

            self._port.write(b"\x18")
            time.sleep(2.0)
            responses = _read_available(self._port) or ["soft reset sent"]
            self._port.reset_input_buffer()
            return self._remember(
                SerialResult(
                    dry_run=False,
                    sent_lines=["soft-reset"],
                    responses=responses,
                    port=self._current_port_name(),
                ),
                "connected",
            )

    def start_continuous_jog(
        self,
        axis: str,
        direction: float,
        config: AppConfig | None = None,
    ) -> SerialResult:
        cfg = config or self._config
        if cfg is None:
            raise RuntimeError("Serial is not configured")

        with self._lock:
            if not cfg.serial.dry_run:
                if not self._is_open() or self._port is None:
                    raise RuntimeError("Serial is not connected. Use Motion -> Connect first.")
                self._refresh_position_for_continuous_jog_locked(cfg)
            line = _build_clipped_continuous_jog_line(
                axis=axis,
                direction=direction,
                config=cfg,
                last_position=self._last_position,
            )
            if cfg.serial.dry_run:
                return self._remember(
                    SerialResult(
                        dry_run=True,
                        sent_lines=[line],
                        responses=["dry-run: continuous jog skipped"],
                        port=cfg.serial.port,
                    ),
                    "dry-run",
                )
            responses = _send_line(self._port, line, cfg)
            return self._remember(
                SerialResult(
                    dry_run=False,
                    sent_lines=[line],
                    responses=responses,
                    port=self._current_port_name(),
                ),
                "jogging",
            )

    def start_continuous_vector_jog(
        self,
        dx_sign: float = 0.0,
        dy_sign: float = 0.0,
        dz_sign: float = 0.0,
        config: AppConfig | None = None,
    ) -> SerialResult:
        cfg = config or self._config
        if cfg is None:
            raise RuntimeError("Serial is not configured")

        with self._lock:
            if not cfg.serial.dry_run:
                if not self._is_open() or self._port is None:
                    raise RuntimeError("Serial is not connected. Use Motion -> Connect first.")
                self._refresh_position_for_continuous_jog_locked(cfg)
            line = _build_clipped_continuous_vector_jog_line(
                dx_sign=dx_sign,
                dy_sign=dy_sign,
                dz_sign=dz_sign,
                config=cfg,
                last_position=self._last_position,
            )
            if cfg.serial.dry_run:
                return self._remember(
                    SerialResult(
                        dry_run=True,
                        sent_lines=[line],
                        responses=["dry-run: continuous vector jog skipped"],
                        port=cfg.serial.port,
                    ),
                    "dry-run",
                )
            responses = _send_line(self._port, line, cfg)
            return self._remember(
                SerialResult(
                    dry_run=False,
                    sent_lines=[line],
                    responses=responses,
                    port=self._current_port_name(),
                ),
                "jogging",
            )

    def cancel_jog(self, config: AppConfig | None = None) -> SerialResult:
        cfg = config or self._config
        if cfg is None:
            raise RuntimeError("Serial is not configured")

        with self._lock:
            if cfg.serial.dry_run:
                return self._remember(
                    SerialResult(
                        dry_run=True,
                        sent_lines=["jog-cancel"],
                        responses=["dry-run: jog cancel skipped"],
                        port=cfg.serial.port,
                    ),
                    "dry-run",
                )
            if not self._is_open() or self._port is None:
                raise RuntimeError("Serial is not connected. Use Motion -> Connect first.")

            self._port.write(b"\x85")
            time.sleep(0.05)
            responses = _read_available(self._port) or ["jog cancel sent"]
            return self._remember(
                SerialResult(
                    dry_run=False,
                    sent_lines=["jog-cancel"],
                    responses=responses,
                    port=self._current_port_name(),
                ),
                "connected",
            )

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_open()

    def _current_port_name(self) -> str | None:
        if self._port is not None:
            return getattr(self._port, "port", None)
        if self._config is not None:
            return self._config.serial.port
        return None

    def _is_open(self) -> bool:
        return bool(self._port is not None and getattr(self._port, "is_open", False))

    def _close_open_port(self) -> None:
        if self._port is not None:
            try:
                if getattr(self._port, "is_open", False):
                    self._port.close()
            finally:
                self._port = None

    def _remember(self, result: SerialResult, status: str) -> SerialResult:
        self._last_status = status
        self._last_responses = result.responses
        for line in reversed(result.responses):
            parsed = parse_grbl_status_line(line)
            if parsed is not None:
                self._last_report = line
                self._last_position = _merge_status_position(self._last_position, parsed)
                break
        return result

    def _refresh_position_for_continuous_jog_locked(self, cfg: AppConfig) -> None:
        if cfg.controller.type != "grbl":
            return
        if self._port is None:
            return
        try:
            _drain_available(self._port)
            self._port.write(b"?")
            responses = _read_until_status_response(self._port, min(float(cfg.serial.timeout_s), 0.20))
        except Exception:
            return
        for line in reversed(responses):
            parsed = parse_grbl_status_line(line)
            if parsed is not None:
                self._last_report = line
                self._last_position = _merge_status_position(self._last_position, parsed)
                break


class SerialTransport:
    def __init__(self, config: AppConfig, force_dry_run: bool | None = None) -> None:
        self.config = config
        self.dry_run = config.serial.dry_run if force_dry_run is None else force_dry_run

    def execute(self, lines: list[str]) -> SerialResult:
        if self.dry_run:
            return SerialResult(
                dry_run=True,
                sent_lines=lines,
                responses=["dry-run: serial disabled"],
                port=self.config.serial.port,
            )

        manager = get_serial_manager()
        if manager.is_connected:
            return manager.execute(lines, self.config)
        raise RuntimeError("Serial is not connected. Use Motion -> Connect first.")


def get_serial_manager() -> SerialConnectionManager:
    return _SERIAL_MANAGER


def _send_line(port: object, line: str, config: AppConfig) -> list[str]:
    payload = line.strip().encode("ascii") + config.controller.line_ending.encode("ascii")
    port.write(payload)
    responses = _read_until_response(port, config.serial.timeout_s, expect_ok=True)
    lowered = [item.lower() for item in responses]
    if any(item == "ok" or item.startswith("error") for item in lowered):
        return responses
    raise TimeoutError(f"Timed out waiting for ok after: {line}")


def _build_grbl_jog_line(axis: str, direction: float, config: AppConfig) -> str:
    normalized = axis.lower()
    if normalized not in config.machine.axes:
        raise ValueError("axis must be X, Y, or Z")
    sign = 1.0 if direction >= 0 else -1.0
    feed = config.machine.z_feed_mm_min if normalized == "z" else config.machine.jog_feed_mm_min
    segment_seconds = 1.6
    segment_real_mm = feed * segment_seconds / 60.0
    if normalized == "z":
        segment_real_mm = min(8.0, max(1.0, segment_real_mm))
    else:
        segment_real_mm = min(25.0, max(3.0, segment_real_mm))
    commanded_delta = config.machine.axes[normalized].real_delta_to_commanded(
        sign * segment_real_mm
    )
    letter = normalized.upper()
    return (
        f"$J=G91 G21 {letter}{_format_float(commanded_delta)} "
        f"F{_format_float(feed)}"
    )


def _build_grbl_jog_line_with_delta(axis: str, commanded_delta: float, feed_mm_min: float) -> str:
    letter = axis.upper()
    return (
        f"$J=G91 G21 {letter}{_format_float(commanded_delta)} "
        f"F{_format_float(feed_mm_min)}"
    )


def _build_grbl_jog_vector_line(
    dx_sign: float,
    dy_sign: float,
    dz_sign: float,
    config: AppConfig,
) -> str:
    deltas = _continuous_vector_segment_commanded_deltas(dx_sign, dy_sign, dz_sign, config)
    terms: list[str] = []
    if abs(deltas["x"]) > 1e-9:
        terms.append(f"X{_format_float(deltas['x'])}")
    if abs(deltas["y"]) > 1e-9:
        terms.append(f"Y{_format_float(deltas['y'])}")
    if abs(deltas["z"]) > 1e-9:
        terms.append(f"Z{_format_float(deltas['z'])}")
    if not terms:
        raise ValueError("At least one jog direction must be non-zero")
    feed = deltas["feed"]
    return f"$J=G91 G21 {' '.join(terms)} F{_format_float(feed)}"


def _format_float(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _continuous_segment_commanded_delta(axis: str, direction: float, config: AppConfig) -> float:
    normalized = axis.lower()
    sign = 1.0 if direction >= 0 else -1.0
    feed = config.machine.z_feed_mm_min if normalized == "z" else config.machine.jog_feed_mm_min
    segment_seconds = 1.6
    segment_real_mm = feed * segment_seconds / 60.0
    if normalized == "z":
        segment_real_mm = min(8.0, max(1.0, segment_real_mm))
    else:
        segment_real_mm = min(25.0, max(3.0, segment_real_mm))
    return config.machine.axes[normalized].real_delta_to_commanded(sign * segment_real_mm)


def _continuous_jog_tuning(config: AppConfig, axis: str) -> tuple[float, float, float]:
    raw_machine = config.raw.get("machine")
    raw_tuning: dict[str, object] = {}
    if isinstance(raw_machine, dict):
        maybe_tuning = raw_machine.get("continuous_jog")
        if isinstance(maybe_tuning, dict):
            raw_tuning = maybe_tuning

    normalized = axis.lower()
    if normalized in ("x", "y"):
        default_stop_margin_mm = 10.0
        default_slow_zone_mm = 20.0
        default_min_feed_scale = 0.20
    else:
        default_stop_margin_mm = 0.6
        default_slow_zone_mm = 2.0
        default_min_feed_scale = 0.45

    try:
        stop_margin_mm = float(raw_tuning.get("stop_margin_mm", raw_tuning.get("boundary_margin_mm", default_stop_margin_mm)))
    except Exception:
        stop_margin_mm = default_stop_margin_mm
    try:
        slow_zone_mm = float(raw_tuning.get("slow_zone_mm", default_slow_zone_mm))
    except Exception:
        slow_zone_mm = default_slow_zone_mm
    try:
        min_feed_scale = float(raw_tuning.get("min_feed_scale", default_min_feed_scale))
    except Exception:
        min_feed_scale = default_min_feed_scale

    stop_margin_mm = max(0.0, stop_margin_mm)
    slow_zone_mm = max(0.0, slow_zone_mm)
    min_feed_scale = min(1.0, max(0.05, min_feed_scale))
    return stop_margin_mm, slow_zone_mm, min_feed_scale


def _continuous_vector_segment_commanded_deltas(
    dx_sign: float,
    dy_sign: float,
    dz_sign: float,
    config: AppConfig,
) -> dict[str, float]:
    feed_xy = config.machine.jog_feed_mm_min
    feed_z = config.machine.z_feed_mm_min

    has_xy = abs(dx_sign) > 1e-9 or abs(dy_sign) > 1e-9
    has_z = abs(dz_sign) > 1e-9
    if not has_xy and not has_z:
        raise ValueError("At least one jog direction must be non-zero")
    if has_xy and has_z:
        feed = min(feed_xy, feed_z)
    elif has_xy:
        feed = feed_xy
    else:
        feed = feed_z

    segment_seconds = 1.6
    segment_real_mm = feed * segment_seconds / 60.0
    if has_xy and not has_z:
        segment_real_mm = min(25.0, max(3.0, segment_real_mm))
    elif has_z and not has_xy:
        segment_real_mm = min(8.0, max(1.0, segment_real_mm))
    else:
        segment_real_mm = min(8.0, max(1.0, segment_real_mm))

    normalized_dx = 0.0 if abs(dx_sign) <= 1e-9 else (1.0 if dx_sign > 0 else -1.0)
    normalized_dy = 0.0 if abs(dy_sign) <= 1e-9 else (1.0 if dy_sign > 0 else -1.0)
    normalized_dz = 0.0 if abs(dz_sign) <= 1e-9 else (1.0 if dz_sign > 0 else -1.0)

    return {
        "x": config.machine.axes["x"].real_delta_to_commanded(normalized_dx * segment_real_mm),
        "y": config.machine.axes["y"].real_delta_to_commanded(normalized_dy * segment_real_mm),
        "z": config.machine.axes["z"].real_delta_to_commanded(normalized_dz * segment_real_mm),
        "feed": float(feed),
    }


def _extract_work_position(last_position: dict[str, object]) -> tuple[float, float, float] | None:
    wpos_raw = last_position.get("wpos")
    if isinstance(wpos_raw, list) and len(wpos_raw) >= 3:
        try:
            return (float(wpos_raw[0]), float(wpos_raw[1]), float(wpos_raw[2]))
        except Exception:
            return None

    mpos_raw = last_position.get("mpos")
    wco_raw = last_position.get("wco")
    if isinstance(mpos_raw, list) and len(mpos_raw) >= 3 and isinstance(wco_raw, list) and len(wco_raw) >= 3:
        try:
            return (
                float(mpos_raw[0]) - float(wco_raw[0]),
                float(mpos_raw[1]) - float(wco_raw[1]),
                float(mpos_raw[2]) - float(wco_raw[2]),
            )
        except Exception:
            return None

    if not isinstance(mpos_raw, list) or len(mpos_raw) < 3:
        return None
    try:
        return (float(mpos_raw[0]), float(mpos_raw[1]), float(mpos_raw[2]))
    except Exception:
        return None


def _clip_axis_delta_to_limit(
    *,
    axis: str,
    current: float,
    requested_delta: float,
    config: AppConfig,
) -> tuple[float, float]:
    if abs(requested_delta) <= 1e-9:
        return 0.0, 1.0
    axis_cfg = config.machine.axes[axis]
    sign = 1.0 if requested_delta > 0 else -1.0
    limit_value = axis_cfg.max_commanded_mm if sign > 0 else axis_cfg.min_commanded_mm
    remaining = (limit_value - current) if sign > 0 else (current - limit_value)
    if remaining <= 0:
        return 0.0, 0.0
    stop_margin_mm, slow_zone_mm, _ = _continuous_jog_tuning(config, axis)
    span_cmd = abs(float(axis_cfg.max_commanded_mm) - float(axis_cfg.min_commanded_mm))
    span_mm = abs(axis_cfg.commanded_delta_to_real(span_cmd))

    # Keep user-facing XY buffer near 1-2cm on normal workspaces,
    # but adapt only when the captured workspace is extremely small.
    if axis in ("x", "y") and span_mm > 1e-6:
        if span_mm < (stop_margin_mm * 2.2):
            adaptive_stop = max(0.5, span_mm * 0.18)
            adaptive_slow = max(adaptive_stop + 0.8, span_mm * 0.45)
            stop_margin_mm = min(stop_margin_mm, adaptive_stop)
            slow_zone_mm = min(slow_zone_mm, adaptive_slow)

    stop_margin_cmd = abs(axis_cfg.real_delta_to_commanded(stop_margin_mm))
    slow_zone_cmd = abs(axis_cfg.real_delta_to_commanded(slow_zone_mm))

    safe_remaining = max(0.0, remaining - stop_margin_cmd)
    if safe_remaining <= 0:
        return 0.0, 0.0
    clipped_abs = min(abs(requested_delta), safe_remaining)
    if clipped_abs <= 1e-9:
        return 0.0, 0.0
    clipped = clipped_abs if sign > 0 else -clipped_abs
    distance_scale = clipped_abs / abs(requested_delta)
    if slow_zone_cmd <= 1e-9:
        slowdown_scale = 1.0
    else:
        slowdown_scale = min(1.0, max(0.0, safe_remaining / slow_zone_cmd))
    scale = min(distance_scale, slowdown_scale)
    return clipped, scale


def _build_clipped_continuous_jog_line(
    *,
    axis: str,
    direction: float,
    config: AppConfig,
    last_position: dict[str, object],
) -> str:
    normalized = axis.lower()
    if normalized not in config.machine.axes:
        raise ValueError("axis must be X, Y, or Z")
    nominal_delta = _continuous_segment_commanded_delta(normalized, direction, config)
    nominal_feed = config.machine.z_feed_mm_min if normalized == "z" else config.machine.jog_feed_mm_min
    if normalized in ("x", "y") and not _runtime_xy_bounds_active(config):
        return _build_grbl_jog_line_with_delta(normalized, nominal_delta, nominal_feed)
    clipped_delta = nominal_delta
    scale = 1.0
    pos = _extract_work_position(last_position)
    if pos is not None:
        current = pos[{"x": 0, "y": 1, "z": 2}[normalized]]
        clipped_delta, scale = _clip_axis_delta_to_limit(
            axis=normalized,
            current=current,
            requested_delta=nominal_delta,
            config=config,
        )
    if abs(clipped_delta) <= 1e-9:
        raise ValueError(f"{normalized.upper()} boundary reached")
    _, _, min_feed_scale = _continuous_jog_tuning(config, normalized)
    feed = max(20.0, nominal_feed * max(min_feed_scale, min(1.0, scale)))
    return _build_grbl_jog_line_with_delta(normalized, clipped_delta, feed)


def _build_clipped_continuous_vector_jog_line(
    *,
    dx_sign: float,
    dy_sign: float,
    dz_sign: float,
    config: AppConfig,
    last_position: dict[str, object],
) -> str:
    deltas = _continuous_vector_segment_commanded_deltas(dx_sign, dy_sign, dz_sign, config)
    nominal_feed = float(deltas["feed"])
    enforce_xy = _runtime_xy_bounds_active(config)
    clipped_x = deltas["x"]
    clipped_y = deltas["y"]
    clipped_z = deltas["z"]
    scales: list[float] = []
    pos = _extract_work_position(last_position)
    if pos is not None:
        if enforce_xy:
            clipped_x, scale_x = _clip_axis_delta_to_limit(
                axis="x",
                current=pos[0],
                requested_delta=deltas["x"],
                config=config,
            )
            clipped_y, scale_y = _clip_axis_delta_to_limit(
                axis="y",
                current=pos[1],
                requested_delta=deltas["y"],
                config=config,
            )
        else:
            scale_x = 1.0
            scale_y = 1.0
        clipped_z, scale_z = _clip_axis_delta_to_limit(
            axis="z",
            current=pos[2],
            requested_delta=deltas["z"],
            config=config,
        )
        if abs(deltas["x"]) > 1e-9:
            scales.append(scale_x)
        if abs(deltas["y"]) > 1e-9:
            scales.append(scale_y)
        if abs(deltas["z"]) > 1e-9:
            scales.append(scale_z)

    terms: list[str] = []
    if abs(clipped_x) > 1e-9:
        terms.append(f"X{_format_float(clipped_x)}")
    if abs(clipped_y) > 1e-9:
        terms.append(f"Y{_format_float(clipped_y)}")
    if abs(clipped_z) > 1e-9:
        terms.append(f"Z{_format_float(clipped_z)}")
    if not terms:
        raise ValueError("Boundary reached")

    min_scale = min(scales) if scales else 1.0
    _, _, min_feed_scale = _continuous_jog_tuning(config, "x")
    feed = max(20.0, nominal_feed * max(min_feed_scale, min(1.0, min_scale)))
    return f"$J=G91 G21 {' '.join(terms)} F{_format_float(feed)}"


def _runtime_xy_bounds_active(config: AppConfig | None = None) -> bool:
    snapshot = get_runtime_bounds()
    if not isinstance(snapshot, dict):
        return False
    return bool(snapshot.get("enabled"))


def _parse_xyz_triplet(raw: str) -> list[float] | None:
    chunks = [item.strip() for item in raw.split(",")]
    if len(chunks) < 3:
        return None
    try:
        return [float(item) for item in chunks]
    except ValueError:
        return None


def parse_grbl_status_line(line: str) -> dict[str, object] | None:
    text = line.strip()
    if not (text.startswith("<") and text.endswith(">")):
        return None

    body = text[1:-1]
    fields = body.split("|")
    if not fields:
        return None

    result: dict[str, object] = {
        "state": fields[0].strip(),
    }
    mpos: list[float] | None = None
    wpos: list[float] | None = None
    wco: list[float] | None = None

    for field in fields[1:]:
        if ":" not in field:
            continue
        key, value = field.split(":", 1)
        name = key.strip().upper()
        parsed = _parse_xyz_triplet(value)
        if parsed is None:
            continue
        if name == "MPOS":
            mpos = parsed
        elif name == "WPOS":
            wpos = parsed
        elif name == "WCO":
            wco = parsed

    if wpos is None and mpos is not None and wco is not None:
        size = min(len(mpos), len(wco))
        wpos = [mpos[index] - wco[index] for index in range(size)]
    if mpos is None and wpos is not None and wco is not None:
        size = min(len(wpos), len(wco))
        mpos = [wpos[index] + wco[index] for index in range(size)]

    if mpos is not None:
        result["mpos"] = mpos
    if wpos is not None:
        result["wpos"] = wpos
    if wco is not None:
        result["wco"] = wco
    return result


def _merge_status_position(
    previous: dict[str, object] | None,
    current: dict[str, object],
) -> dict[str, object]:
    merged: dict[str, object] = dict(previous or {})
    merged.update(current)

    prev_wco = previous.get("wco") if isinstance(previous, dict) else None
    if "wco" not in current and isinstance(prev_wco, list) and len(prev_wco) >= 3:
        merged["wco"] = prev_wco

    mpos = merged.get("mpos")
    wpos = merged.get("wpos")
    wco = merged.get("wco")

    if isinstance(mpos, list) and len(mpos) >= 3 and isinstance(wco, list) and len(wco) >= 3:
        merged["wpos"] = [float(mpos[i]) - float(wco[i]) for i in range(3)]
    if isinstance(wpos, list) and len(wpos) >= 3 and isinstance(wco, list) and len(wco) >= 3:
        if not (isinstance(mpos, list) and len(mpos) >= 3):
            merged["mpos"] = [float(wpos[i]) + float(wco[i]) for i in range(3)]
    return merged


def _read_until_response(port: object, timeout_s: float, expect_ok: bool) -> list[str]:
    responses: list[str] = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        raw = port.readline()
        if not raw:
            continue
        text = raw.decode("ascii", errors="replace").strip()
        if not text:
            continue
        responses.append(text)
        lowered = text.lower()
        if expect_ok and (lowered == "ok" or lowered.startswith("error")):
            return responses
        if not expect_ok:
            return responses
    if responses:
        return responses
    raise TimeoutError("Timed out waiting for serial response")


def _read_until_status_response(port: object, timeout_s: float) -> list[str]:
    responses: list[str] = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        raw = port.readline()
        if not raw:
            continue
        text = raw.decode("ascii", errors="replace").strip()
        if not text:
            continue
        responses.append(text)
        if parse_grbl_status_line(text) is not None:
            return responses
    if responses:
        raise TimeoutError(
            "Timed out waiting for controller status report "
            f"(received non-status lines: {responses[-3:]})"
        )
    raise TimeoutError("Timed out waiting for controller status report")


def _read_available(port: object) -> list[str]:
    responses: list[str] = []
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        waiting = getattr(port, "in_waiting", 0)
        if not waiting:
            time.sleep(0.05)
            continue
        raw = port.readline()
        if not raw:
            continue
        text = raw.decode("ascii", errors="replace").strip()
        if text:
            responses.append(text)
    return responses


def _drain_available(port: object, max_lines: int = 32) -> list[str]:
    responses: list[str] = []
    for _ in range(max_lines):
        waiting = getattr(port, "in_waiting", 0)
        if not waiting:
            break
        raw = port.readline()
        if not raw:
            break
        text = raw.decode("ascii", errors="replace").strip()
        if text:
            responses.append(text)
    return responses


def _wait_until_idle(port: object, config: AppConfig) -> list[str]:
    responses: list[str] = []
    deadline = time.monotonic() + config.controller.idle_timeout_s
    while time.monotonic() < deadline:
        port.write(b"?")
        raw = port.readline()
        if raw:
            text = raw.decode("ascii", errors="replace").strip()
            if text:
                responses.append(text)
                if text.startswith("<Idle"):
                    return responses
        time.sleep(0.1)
    raise TimeoutError("Timed out waiting for GRBL Idle state")


def _is_motion_command(line: str) -> bool:
    stripped = line.strip().upper()
    return stripped.startswith(("G0", "G1", "G2", "G3", "G28", "G38"))


_SERIAL_MANAGER = SerialConnectionManager()
