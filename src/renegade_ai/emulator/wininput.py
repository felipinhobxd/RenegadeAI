from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
INPUT_KEYBOARD = 1

_NAMED_VK: dict[str, int] = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "escape": 0x1B,
    "space": 0x20,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "delete": 0x2E,
}

_EXTENDED = {"left", "up", "right", "down", "delete"}

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]


def _virtual_key(key: str) -> int:
    normalized = key.strip().lower()
    if normalized in _NAMED_VK:
        return _NAMED_VK[normalized]
    if len(normalized) == 1:
        if "a" <= normalized <= "z":
            return ord(normalized.upper())
        if "0" <= normalized <= "9":
            return ord(normalized)
    raise ValueError(
        f"Unsupported Windows input key {key!r}. Use letters, digits, arrows, "
        "enter, backspace, tab, space, escape, shift, ctrl, alt or delete."
    )


def _send_scan(scan_code: int, *, key_up: bool, extended: bool) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Native Windows input is only available on Windows")

    flags = KEYEVENTF_SCANCODE
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    if key_up:
        flags |= KEYEVENTF_KEYUP

    packet = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=0,
            wScan=scan_code,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        ),
    )
    user32 = ctypes.windll.user32
    sent = user32.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT))
    if sent != 1:
        raise OSError(ctypes.get_last_error(), "Windows SendInput failed")


def press_key(key: str, seconds: float) -> None:
    """Send one keyboard press with Windows scan codes."""
    if sys.platform != "win32":
        raise RuntimeError("Native Windows input is only available on Windows")

    normalized = key.strip().lower()
    vk = _virtual_key(normalized)
    scan = int(ctypes.windll.user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC))
    if scan == 0:
        raise RuntimeError(f"Could not resolve a scan code for {key!r}")

    extended = normalized in _EXTENDED
    _send_scan(scan, key_up=False, extended=extended)
    try:
        time.sleep(max(0.01, seconds))
    finally:
        _send_scan(scan, key_up=True, extended=extended)
