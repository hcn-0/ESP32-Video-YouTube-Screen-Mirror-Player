"""Serial link to the ESP32: packet building, ACK flow control, button commands, auto-reconnect."""
import binascii
import queue
import struct
import threading
import time

import serial
from serial.tools import list_ports

SYNC = b"\xAA\x55"
TYPE_FRAME = 0x01
TYPE_HEARTBEAT = 0x02


def build_packet(ptype: int, payload: bytes = b"") -> bytes:
    """AA 55 | type | len(LE16) | payload | CRC16-CCITT-FALSE over (type,len,payload)."""
    body = struct.pack("<BH", ptype, len(payload)) + payload
    return SYNC + body + struct.pack("<H", binascii.crc_hqx(body, 0xFFFF))


def find_port():
    ports = list_ports.comports()
    for p in ports:
        text = ((p.description or "") + (p.manufacturer or "")).lower()
        if any(k in text for k in ("cp210", "ch340", "ch341", "silicon labs", "usb serial", "ftdi")):
            return p.device
    return ports[0].device if ports else None


class ESP32Link:
    def __init__(self, port, baud, ack_timeout=0.25, reconnect_interval=2.0):
        self.port_setting, self.baud = port, baud
        self.ack_timeout, self.reconnect_interval = ack_timeout, reconnect_interval
        self.commands = queue.Queue()      # "PLAY", "LEFT", "RIGHT"
        self.connected = False
        self.port_name = None
        self.awaiting_ack = False
        self.last_acked = True             # False if the last frame was not confirmed
        self.sent_at = 0.0
        self.last_tx = 0.0
        self.frames_sent = self.acks = self.errors = 0
        self._ser = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last_msg = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    # ---------- public API ----------
    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._drop("closed")

    @property
    def status(self):
        return f"connected ({self.port_name})" if self.connected else "NOT connected"

    def drain_commands(self):
        out = []
        while True:
            try:
                out.append(self.commands.get_nowait())
            except queue.Empty:
                return out

    def ready_for_frame(self):
        return self.connected and (not self.awaiting_ack or
                                   time.perf_counter() - self.sent_at > self.ack_timeout)

    def send_frame(self, bits: bytes, progress: int, paused: bool):
        assert len(bits) == 1024
        payload = bytes((progress & 0xFF, 1 if paused else 0)) + bits
        # set flags BEFORE writing so a very fast ACK is not lost
        self.awaiting_ack, self.last_acked = True, False
        self.sent_at = time.perf_counter()
        if self._write(build_packet(TYPE_FRAME, payload)):
            self.frames_sent += 1

    def send_heartbeat(self):
        self._write(build_packet(TYPE_HEARTBEAT))

    # ---------- internals ----------
    def _log(self, msg):
        if msg != self._last_msg:       # avoid spamming the same message
            print("[link]", msg)
            self._last_msg = msg

    def _write(self, data: bytes) -> bool:
        ser = self._ser
        if ser is None:
            return False
        try:
            with self._lock:
                ser.write(data)
            self.last_tx = time.perf_counter()
            return True
        except (serial.SerialException, OSError) as e:
            self._drop(f"write error: {e}")
            return False

    def _drop(self, reason):
        ser, self._ser = self._ser, None
        self.connected = False
        self.awaiting_ack = False
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
            self._log(f"disconnected ({reason}); will retry")

    def _try_open(self):
        port = find_port() if str(self.port_setting).upper() == "AUTO" else self.port_setting
        if not port:
            self._log("no serial port found - plug in the ESP32")
            return
        try:
            ser = serial.Serial(port, self.baud, timeout=0.1, write_timeout=1.0)
        except (serial.SerialException, OSError) as e:
            self._log(f"cannot open {port}: {e}")
            return
        time.sleep(2.0)                 # ESP32 usually resets when the port opens
        ser.reset_input_buffer()
        self.port_name, self._ser, self.connected = port, ser, True
        self.awaiting_ack, self.last_acked = False, True
        self._last_msg = None
        self._log(f"connected on {port} @ {self.baud}")

    def _handle_line(self, line):
        if line == "K":
            self.acks += 1
            self.awaiting_ack, self.last_acked = False, True
        elif line == "E":
            self.errors += 1
            self.awaiting_ack, self.last_acked = False, False
        elif line.startswith("B:"):
            self.commands.put(line[2:])
        elif line == "READY":
            print("[link] ESP32 ready")
        # anything else (boot noise) is ignored

    def _run(self):
        rx = bytearray()
        last_try = float("-inf")
        while not self._stop.is_set():
            if self._ser is None:
                if time.monotonic() - last_try < self.reconnect_interval:
                    time.sleep(0.1)
                    continue
                last_try = time.monotonic()
                self._try_open()
                rx.clear()
                continue
            try:
                data = self._ser.read(max(1, self._ser.in_waiting))
            except (serial.SerialException, OSError, AttributeError) as e:
                self._drop(f"read error: {e}")
                continue
            if not data:
                continue
            rx.extend(data)
            while True:
                i = rx.find(b"\n")
                if i < 0:
                    break
                line = bytes(rx[:i]).decode("ascii", errors="ignore").strip()
                del rx[:i + 1]
                self._handle_line(line)
            if len(rx) > 256:           # garbage protection
                rx.clear()
