from __future__ import annotations

"""
High-level CNC tool wrapper invoked via the Open Interpreter bridge.
"""

from typing import Any, Dict, Optional

from .cnc_bridge import CNCBridge

# Safety clamps for simple jogs
MAX_JOG_MM = 50.0
MAX_FEED = 1000.0
MAX_SPINDLE = 1000
ALLOWED_GCODE_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.+-*/ ()[]%$#_;:,")

_cnc_instance: Optional[CNCBridge] = None
_cnc_unlocked = False


def _clamp(val: float, lo: float, hi: float) -> float:
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val


def _get_cnc() -> CNCBridge:
    global _cnc_instance, _cnc_unlocked
    if _cnc_instance is None:
        _cnc_instance = CNCBridge(port="COM4", baudrate=115200)
        _cnc_instance.open()
        if not _cnc_unlocked:
            try:
                print("[CNC] unlocking once ($X)")
                _cnc_instance.unlock()
                _cnc_unlocked = True
            except Exception:
                pass
    return _cnc_instance


def shutdown() -> None:
    """Close the CNC connection, if open."""
    global _cnc_instance
    if _cnc_instance is None:
        return
    try:
        _cnc_instance.close()
    finally:
        _cnc_instance = None


def cnc_send_line(line: str) -> str:
    """
    Shared sender for all CNC commands (jog buttons + raw G-code).
    Logs the line and routes through the same serial connection.
    """
    line = (line or "").strip()
    if not line:
        return "no-op"
    cnc = _get_cnc()
    print(f"[CNC] -> {line}")
    if line == "?":
        return cnc.status() or "no-status"
    return cnc.send_gcode(line)


def send_cnc_gcode(gcode: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Send raw G-code lines to the CNC using the existing bridge.
    """
    if not isinstance(gcode, str):
        raise ValueError("gcode must be a string")

    # Normalize and split
    lines = [ln.strip() for ln in gcode.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [ln for ln in lines if ln]

    # Light validation
    for ln in lines:
        if not set(ln.upper()) <= ALLOWED_GCODE_CHARS:
            raise ValueError(f"Line contains disallowed characters: {ln!r}")

    if dry_run:
        print("[CNC DRY RUN] Would send G-code:")
        for ln in lines:
            print("  ", ln)
        return {"status": "dry_run", "lines": lines}

    sent = []
    for ln in lines:
        cnc_send_line(ln)
        sent.append(ln)
    return {"status": "ok", "sent": sent}


def cnc_status() -> Dict[str, Any]:
    """Query controller status via shared sender."""
    resp = cnc_send_line("?")
    return {"status": "sent", "response": resp}


def cnc(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Main CNC tool entrypoint.

    payload:
      {
        "mode": "status" | "raw",
        "gcode": "<string>",  # for raw
        "dry_run": bool       # optional
      }
    """
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_payload"}

    mode = payload.get("mode", "raw")
    try:
        if mode == "status":
            result = cnc_status()
            return {"ok": True, **result}
        if mode == "raw":
            gcode = payload.get("gcode", "")
            dry_run = bool(payload.get("dry_run", False))
            result = send_cnc_gcode(gcode, dry_run=dry_run)
            return {"ok": True, **result}
        return {"ok": False, "error": f"Unknown CNC mode: {mode}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


TOOL_FUNCTIONS = {
    "send_cnc_gcode": send_cnc_gcode,
    "cnc": cnc,
}
