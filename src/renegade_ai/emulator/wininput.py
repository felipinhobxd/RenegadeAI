from __future__ import annotations

import ctypes
import sys
import time


KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0

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

    user32 = ctypes.windll.user32

    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", ctypes.c_ulong), ("union", INPUTUNION)]

    flags = KEYEVENTF_SCANCODE
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    if key_up:
        flags |= KEYEVENTF_KEYUP

    packet = INPUT(type=1, ki=KEYBDINPUT(0, scan_code, flags, 0, 0))
    sent = user32.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT))
    if sent != 1:
        raise OSError(ctypes.get_last_error(), "Windows SendInput failed")


def press_key(key: str, seconds: float) -> None:
    """Send one physical-looking keyboard press using Windows scan codes.

    melonDS is a desktop application, but directional input can be less reliable
    through high-level automation libraries. Scan-code input is closer to a real
    keyboard event and is therefore preferred on Windows.
    """

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
