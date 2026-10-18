"""Low-overhead Linux/RK3588 telemetry sampler used during each model turn."""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any


def _read_number(path: Path) -> float | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None
    except (OSError, ValueError):
        return None


def _safe_name(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z_.-]+", "_", text.strip())
    return value.strip("_") or "unknown"


def _stats(values: list[float], digits: int = 3) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "avg": round(sum(values) / len(values), digits),
        "min": round(min(values), digits),
        "max": round(max(values), digits),
    }


class BoardMetricsSampler:
    """Samples only kernel-exported metrics; unavailable sensors stay unavailable."""

    def __init__(self, process_pid: int, interval_ms: int = 100):
        self.process_pid = int(process_pid)
        self.interval_seconds = max(0.02, interval_ms / 1000.0)
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.started_at = 0.0
        self.finished_at = 0.0
        self.samples: list[dict[str, Any]] = []
        self.power_paths = self._discover_power_paths()
        self.thermal_paths = self._discover_thermal_paths()
        self.devfreq_paths = self._discover_devfreq_paths()

    @staticmethod
    def _discover_power_paths() -> dict[str, tuple[Path, float]]:
        paths: dict[str, tuple[Path, float]] = {}
        for path in sorted(Path("/sys/class/hwmon").glob("hwmon*/power*_input")):
            hwmon = path.parent
            name = "hwmon"
            try:
                name = hwmon.joinpath("name").read_text(errors="ignore").strip() or name
            except OSError:
                pass
            index = re.search(r"power(\d+)_input", path.name)
            label_path = hwmon / f"power{index.group(1)}_label" if index else None
            label = path.stem
            if label_path and label_path.is_file():
                try:
                    label = label_path.read_text(errors="ignore").strip() or label
                except OSError:
                    pass
            paths[f"hwmon.{_safe_name(name)}.{_safe_name(label)}"] = (path, 1_000_000.0)
        for supply in sorted(Path("/sys/class/power_supply").glob("*")):
            voltage = supply / "voltage_now"
            current = supply / "current_now"
            if voltage.is_file() and current.is_file():
                # A negative current indicates discharge; magnitude is power use.
                paths[f"power_supply.{_safe_name(supply.name)}"] = (supply, -1.0)
        return paths

    @staticmethod
    def _discover_thermal_paths() -> dict[str, Path]:
        paths: dict[str, Path] = {}
        for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
            temp = zone / "temp"
            if not temp.is_file():
                continue
            label = zone.name
            try:
                label = zone.joinpath("type").read_text(errors="ignore").strip() or label
            except OSError:
                pass
            paths[_safe_name(label)] = temp
        return paths

    @staticmethod
    def _discover_devfreq_paths() -> dict[str, Path]:
        return {
            _safe_name(path.name): path
            for path in sorted(Path("/sys/class/devfreq").glob("*"))
            if path.is_dir()
        }

    def start(self) -> None:
        self.started_at = time.monotonic()
        self._sample_once()
        self.thread = threading.Thread(target=self._loop, name="board-metrics", daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            self._sample_once()

    def _process_memory(self) -> dict[str, float]:
        result: dict[str, float] = {}
        try:
            lines = Path(f"/proc/{self.process_pid}/status").read_text(errors="ignore").splitlines()
        except OSError:
            return result
        for line in lines:
            if line.startswith(("VmRSS:", "VmHWM:", "VmSize:")):
                key, value = line.split(":", 1)
                match = re.search(r"\d+", value)
                if match:
                    result[key.lower() + "_mb"] = float(match.group(0)) / 1024.0
        return result

    @staticmethod
    def _system_memory() -> dict[str, float]:
        result: dict[str, float] = {}
        try:
            lines = Path("/proc/meminfo").read_text(errors="ignore").splitlines()
        except OSError:
            return result
        for line in lines:
            if line.startswith(("MemTotal:", "MemAvailable:")):
                key, value = line.split(":", 1)
                match = re.search(r"\d+", value)
                if match:
                    result[key.lower() + "_mb"] = float(match.group(0)) / 1024.0
        return result

    def _read_power(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for name, (path, divisor) in self.power_paths.items():
            if divisor > 0:
                value = _read_number(path)
                if value is not None:
                    result[name] = value / divisor
            else:
                voltage = _read_number(path / "voltage_now")
                current = _read_number(path / "current_now")
                if voltage is not None and current is not None:
                    result[name] = abs(voltage * current) / 1_000_000_000_000.0
        return result

    def _read_thermal(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for name, path in self.thermal_paths.items():
            value = _read_number(path)
            if value is not None:
                result[name] = value / 1000.0 if abs(value) > 500 else value
        return result

    def _read_devfreq(self) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for name, root in self.devfreq_paths.items():
            entry: dict[str, float] = {}
            frequency = _read_number(root / "cur_freq")
            load = _read_number(root / "load")
            if frequency is not None:
                entry["frequency_mhz"] = frequency / 1_000_000.0
            if load is not None:
                entry["load_percent"] = load
            if entry:
                result[name] = entry
        return result

    def _sample_once(self) -> None:
        self.samples.append({
            "time": time.monotonic(),
            "process": self._process_memory(),
            "system": self._system_memory(),
            "power": self._read_power(),
            "thermal": self._read_thermal(),
            "devfreq": self._read_devfreq(),
        })

    def stop(self) -> dict[str, Any]:
        if self.finished_at:
            return self.summary()
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=max(1.0, self.interval_seconds * 3))
        self._sample_once()
        self.finished_at = time.monotonic()
        return self.summary()

    def summary(self) -> dict[str, Any]:
        duration = max(0.0, (self.finished_at or time.monotonic()) - self.started_at)
        result: dict[str, Any] = {
            "sample_count": len(self.samples),
            "sample_interval_ms": round(self.interval_seconds * 1000.0, 3),
            "sampled_duration_seconds": round(duration, 6),
            "power_sensor_available": bool(self.power_paths),
        }
        for group, output_name in (("process", "process_memory_mb"), ("system", "system_memory_mb")):
            keys = sorted({key for sample in self.samples for key in sample[group]})
            result[output_name] = {
                key: _stats([sample[group][key] for sample in self.samples if key in sample[group]])
                for key in keys
            }
        power_names = sorted({key for sample in self.samples for key in sample["power"]})
        power: dict[str, Any] = {}
        for name in power_names:
            values = [sample["power"][name] for sample in self.samples if name in sample["power"]]
            entry = _stats(values, 6) or {}
            entry["energy_joules_estimate"] = round((entry.get("avg", 0.0) * duration), 6)
            power[name] = entry
        result["power_w"] = power
        result["power_sensor_available"] = bool(power)
        thermal_names = sorted({key for sample in self.samples for key in sample["thermal"]})
        result["temperature_c"] = {
            name: _stats([sample["thermal"][name] for sample in self.samples if name in sample["thermal"]])
            for name in thermal_names
        }
        devfreq_names = sorted({key for sample in self.samples for key in sample["devfreq"]})
        devfreq: dict[str, Any] = {}
        for name in devfreq_names:
            metric_names = sorted({key for sample in self.samples for key in sample["devfreq"].get(name, {})})
            devfreq[name] = {
                metric: _stats([
                    sample["devfreq"][name][metric]
                    for sample in self.samples
                    if name in sample["devfreq"] and metric in sample["devfreq"][name]
                ])
                for metric in metric_names
            }
        result["devfreq"] = devfreq
        return result
