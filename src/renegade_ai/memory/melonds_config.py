from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MelonDSDebugConfigResult:
    paths: tuple[Path, ...]
    changed: tuple[Path, ...]
    restart_required: bool
    deferred: tuple[Path, ...] = ()

    @property
    def configured(self) -> bool:
        return bool(self.paths)


def _running_melonds_executable() -> Path | None:
    if sys.platform != "win32":
        return None
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        (
            "$p=Get-CimInstance Win32_Process -Filter \"Name='melonDS.exe'\" "
            "| Select-Object -First 1 -ExpandProperty ExecutablePath; "
            "if($p){[Console]::Write($p)}"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3.0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return Path(value) if value else None


def discover_melonds_toml() -> list[Path]:
    candidates: list[Path] = []
    running = _running_melonds_executable()
    if running is not None:
        candidates.append(running.parent / "melonDS.toml")

    for variable in ("APPDATA", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "melonDS" / "melonDS.toml")

    candidates.extend([Path.cwd() / "melonDS.toml", Path.home() / "melonDS.toml"])
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve(strict=False)).lower()
        if key not in seen and path.exists():
            seen.add(key)
            unique.append(path)
    return unique


def _upsert_table(text: str, table: str, values: dict[str, str]) -> str:
    lines = text.splitlines()
    header = f"[{table}]"
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(header)
        lines.extend(f"{key} = {value}" for key, value in values.items())
        return "\n".join(lines) + "\n"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break

    for key, value in values.items():
        replacement = f"{key} = {value}"
        found = False
        prefixes = (f"{key} ", f"{key}=")
        for index in range(start + 1, end):
            stripped = lines[index].strip()
            if stripped.startswith(prefixes):
                lines[index] = replacement
                found = True
                break
        if not found:
            lines.insert(end, replacement)
            end += 1
    return "\n".join(lines) + "\n"


def _desired_debugger_text(original: str) -> str:
    updated = _upsert_table(original, "JIT", {"Enable": "false"})
    for prefix in ("Gdb", "Instance0.Gdb"):
        updated = _upsert_table(updated, prefix, {"Enabled": "true"})
        updated = _upsert_table(
            updated,
            f"{prefix}.ARM9",
            {"Port": "3333", "BreakOnStartup": "false"},
        )
        updated = _upsert_table(
            updated,
            f"{prefix}.ARM7",
            {"Port": "3334", "BreakOnStartup": "false"},
        )
    return updated


def debugger_patch_needed(path: str | Path) -> bool:
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    return _desired_debugger_text(original) != original


def patch_melonds_toml(path: str | Path) -> bool:
    """Enable read-only ARM9 GDB access and disable JIT (required by melonDS)."""
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    updated = _desired_debugger_text(original)
    if updated == original:
        return False

    backup = path.with_suffix(path.suffix + ".renegadeai.bak")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
    temp = path.with_suffix(path.suffix + ".renegadeai.tmp")
    temp.write_text(updated, encoding="utf-8")
    temp.replace(path)
    return True


def configure_melonds_debugger() -> MelonDSDebugConfigResult:
    paths = tuple(discover_melonds_toml())

    # Never rewrite the emulator's configuration underneath a live game. On a
    # first-time setup performed while melonDS is already open, defer the patch
    # until the process has closed. If the file is already configured, attaching
    # to the existing GDB endpoint is still fine and no restart is requested.
    if _running_melonds_executable() is not None:
        deferred: list[Path] = []
        for path in paths:
            try:
                if debugger_patch_needed(path):
                    deferred.append(path)
            except OSError:
                continue
        return MelonDSDebugConfigResult(
            paths=paths,
            changed=(),
            restart_required=False,
            deferred=tuple(deferred),
        )

    changed: list[Path] = []
    for path in paths:
        try:
            if patch_melonds_toml(path):
                changed.append(path)
        except OSError:
            continue
    return MelonDSDebugConfigResult(
        paths=paths,
        changed=tuple(changed),
        restart_required=bool(changed),
        deferred=(),
    )
