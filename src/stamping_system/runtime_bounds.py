from __future__ import annotations

import threading
from typing import Literal


Point = tuple[float, float]
BoundPointName = Literal["origin", "xMax", "yMax"]


class RuntimeBounds:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._enabled = False
        self._points: dict[str, Point | None] = {
            "origin": None,
            "xMax": None,
            "yMax": None,
        }

    def set_point(self, name: BoundPointName, point: Point) -> dict[str, object]:
        with self._lock:
            self._points[name] = (float(point[0]), float(point[1]))
            # Any capture change requires explicit Apply before bounds take effect.
            self._enabled = False
            return self.snapshot()

    def clear(self) -> dict[str, object]:
        with self._lock:
            self._points = {"origin": None, "xMax": None, "yMax": None}
            self._enabled = False
            return self.snapshot()

    def apply(self) -> dict[str, object]:
        return self.set_enabled(True)

    def set_enabled(self, enabled: bool) -> dict[str, object]:
        with self._lock:
            if enabled:
                limits = self._effective_limits_locked()
                x = limits["x"]
                y = limits["y"]
                if not all(value is not None for value in (x["min"], x["max"], y["min"], y["max"])):
                    raise ValueError("Set X0Y0, X Max, and Y Max first")
                if float(x["max"]) <= float(x["min"]) or float(y["max"]) <= float(y["min"]):
                    raise ValueError("Invalid workspace rectangle")
                self._enabled = True
            else:
                self._enabled = False
            return self.snapshot()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            captured = {
                "origin": self._points["origin"],
                "xMax": self._points["xMax"],
                "yMax": self._points["yMax"],
            }
            effective = self._effective_limits_locked()
            return {
                "enabled": self._enabled,
                "captured": captured,
                "effective": effective,
            }

    def apply_to_raw_config(self, raw: dict[str, object]) -> dict[str, object]:
        with self._lock:
            if not self._enabled:
                return raw
            machine = raw.get("machine")
            if not isinstance(machine, dict):
                return raw
            axes = machine.get("axes")
            if not isinstance(axes, dict):
                return raw
            x_axis = axes.get("x")
            y_axis = axes.get("y")
            if not isinstance(x_axis, dict) or not isinstance(y_axis, dict):
                return raw

            limits = self._effective_limits_locked()
            x = limits["x"]
            y = limits["y"]
            if x["min"] is not None:
                x_axis["min_commanded_mm"] = float(x["min"])
            if x["max"] is not None:
                x_axis["max_commanded_mm"] = float(x["max"])
            if y["min"] is not None:
                y_axis["min_commanded_mm"] = float(y["min"])
            if y["max"] is not None:
                y_axis["max_commanded_mm"] = float(y["max"])
            return raw

    def _effective_limits_locked(self) -> dict[str, dict[str, float | None]]:
        origin = self._points["origin"]
        x_max = self._points["xMax"]
        y_max = self._points["yMax"]

        x_min = origin[0] if origin is not None else None
        x_limit = x_max[0] if x_max is not None else None
        if x_min is not None and x_limit is not None and x_min > x_limit:
            x_min, x_limit = x_limit, x_min

        y_min = origin[1] if origin is not None else None
        y_limit = y_max[1] if y_max is not None else None
        if y_min is not None and y_limit is not None and y_min > y_limit:
            y_min, y_limit = y_limit, y_min

        return {
            "x": {"min": x_min, "max": x_limit},
            "y": {"min": y_min, "max": y_limit},
        }


_RUNTIME_BOUNDS = RuntimeBounds()


def get_runtime_bounds() -> dict[str, object]:
    return _RUNTIME_BOUNDS.snapshot()


def set_runtime_bound_point(name: BoundPointName, point: Point) -> dict[str, object]:
    return _RUNTIME_BOUNDS.set_point(name, point)


def clear_runtime_bounds() -> dict[str, object]:
    return _RUNTIME_BOUNDS.clear()


def apply_runtime_bounds() -> dict[str, object]:
    return _RUNTIME_BOUNDS.apply()


def set_runtime_bounds_enabled(enabled: bool) -> dict[str, object]:
    return _RUNTIME_BOUNDS.set_enabled(enabled)


def apply_runtime_bounds_to_raw(raw: dict[str, object]) -> dict[str, object]:
    return _RUNTIME_BOUNDS.apply_to_raw_config(raw)
