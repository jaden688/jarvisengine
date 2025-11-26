from __future__ import annotations

"""
Low-level GRBL bridge for a 3018/GRBL-style board on COM4.
Runs inside the Open Interpreter Python environment.
"""

import threading
import time
from queue import Empty, Queue
from typing import Callable, Optional

try:
    import serial  # type: ignore
except ImportError as exc:  # pragma: no cover - runtime dependency
    raise ImportError("pyserial is required for CNC connectivity. Install with 'pip install pyserial'.") from exc


class CNCBridge:
    """
    Minimal GRBL bridge.

    - open() / close()
    - send a G-code line and wait for 'ok' or 'error'
    - status query '?'
    - helpers for spindle and jogging
    """

    def __init__(
        self,
        port: str = "COM4",
        baudrate: int = 115200,
        read_timeout: float = 1.0,
        write_timeout: float = 1.0,
        logger: Optional[Callable[..., None]] = print,
    ):
        self.port = port
        self.baudrate = baudrate
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.log = logger or (lambda *_, **__: None)

        self.ser: Optional[serial.Serial] = None
        self._running = False
        self._rx_thread: Optional[threading.Thread] = None
        self._rx_queue: Queue[str] = Queue()

    # --- connection ----------------------------------------------------

    def open(self) -> None:
        if self.ser and self.ser.is_open:
            return

        self.log(f"[CNC] Opening {self.port} @ {self.baudrate}...")
        self.ser = serial.Serial(
            self.port,
            self.baudrate,
            timeout=self.read_timeout,
            write_timeout=self.write_timeout,
        )

        # Allow the controller to boot and clear any banner
        time.sleep(2.0)
        self.ser.reset_input_buffer()
        self.ser.write(b"\r\n")
        self.ser.flush()
        _ = self.ser.readline()

        self._running = True
        self._rx_thread = threading.Thread(target=self._reader, daemon=True)
        self._rx_thread.start()
        self.log("[CNC] Connected.")

    def close(self) -> None:
        self._running = False
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None
        self.log("[CNC] Disconnected.")

    def _reader(self) -> None:
        assert self.ser is not None
        while self._running:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                self._rx_queue.put(line)
                self.log(f"[CNC RX] {line}")
            except Exception as exc:
                self.log(f"[CNC] reader error: {exc}")
                break

    # --- core API ------------------------------------------------------

    def send_raw(self, line: str) -> None:
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("CNC not connected")
        data = (line.strip() + "\n").encode()
        self.log(f"[CNC TX] {line.strip()}")
        self.ser.write(data)
        self.ser.flush()

    def send_gcode(self, line: str, timeout: float = 5.0) -> str:
        self.send_raw(line)
        end = time.time() + timeout
        while time.time() < end:
            try:
                resp = self._rx_queue.get(timeout=0.25)
            except Empty:
                continue
            if resp.lower().startswith("ok") or resp.lower().startswith("error"):
                return resp
        raise TimeoutError(f"No GRBL response for: {line}")

    def status(self, timeout: float = 1.0) -> Optional[str]:
        self.send_raw("?")
        try:
            return self._rx_queue.get(timeout=timeout)
        except Empty:
            return None

    # --- helpers -------------------------------------------------------

    def unlock(self) -> str:
        return self.send_gcode("$X")

    def spindle_on(self, s: int = 500) -> str:
        return self.send_gcode(f"M3 S{s}")

    def spindle_off(self) -> str:
        return self.send_gcode("M5")

    def jog_relative(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, feed: float = 200.0) -> str:
        move = []
        if dx:
            move.append(f"X{dx}")
        if dy:
            move.append(f"Y{dy}")
        if dz:
            move.append(f"Z{dz}")
        if not move:
            return "no-op"

        self.send_gcode("G91")  # relative
        resp = self.send_gcode(f"G0 {' '.join(move)} F{feed}")
        self.send_gcode("G90")  # absolute
        return resp
