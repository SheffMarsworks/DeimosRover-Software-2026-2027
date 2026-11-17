#!/usr/bin/env python3
"""Read an XInput gamepad on Windows and stream it to the gamepad_bridge node in WSL.

WSL can't read USB gamepads directly, so this runs on the Windows side.
Uses only the Python standard library (XInput via ctypes).

The controller must be in XInput mode (Logitech F310/F710: switch on the back set to "X").

Usage (Windows PowerShell, after `ros2 run rover_gamepad gamepad_bridge` is running in WSL):
    python windows_gamepad_sender.py [--host 127.0.0.1] [--port 5005] [--player 0]
"""

import argparse
import ctypes
import json
import socket
import time


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_uint),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


def load_xinput():
    for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return getattr(ctypes.windll, dll)
        except OSError:
            continue
    raise RuntimeError("No XInput DLL found")


def read_state(xinput, player):
    """Return the raw controller state as a dict, or None if no controller is connected."""
    state = XINPUT_STATE()
    if xinput.XInputGetState(player, ctypes.byref(state)) != 0:
        return None
    pad = state.Gamepad
    return {
        "packet": state.dwPacketNumber,
        "buttons": pad.wButtons,
        "lt": pad.bLeftTrigger,
        "rt": pad.bRightTrigger,
        "lx": pad.sThumbLX,
        "ly": pad.sThumbLY,
        "rx": pad.sThumbRX,
        "ry": pad.sThumbRY,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--player", type=int, default=0, help="XInput slot 0-3")
    parser.add_argument("--rate", type=float, default=100.0, help="polling rate in Hz")
    args = parser.parse_args()

    xinput = load_xinput()
    period = 1.0 / args.rate
    keepalive = 0.05  # resend unchanged state every 50 ms so the bridge knows we're alive

    while True:
        try:
            print(f"Connecting to gamepad_bridge at {args.host}:{args.port} ...")
            with socket.create_connection((args.host, args.port), timeout=3) as sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                print("Connected. Streaming controller state (Ctrl+C to stop).")
                last_packet, last_sent, was_connected = None, 0.0, None
                while True:
                    state = read_state(xinput, args.player)
                    if (state is not None) != was_connected:
                        was_connected = state is not None
                        print("Controller connected." if was_connected
                              else "No controller in XInput slot "
                                   f"{args.player} (is the switch set to X?)")

                    now = time.monotonic()
                    packet = state["packet"] if state else None
                    if packet != last_packet or now - last_sent >= keepalive:
                        msg = {"connected": state is not None}
                        if state:
                            msg.update(state)
                        sock.sendall((json.dumps(msg) + "\n").encode())
                        last_packet, last_sent = packet, now
                    time.sleep(period)
        except (ConnectionError, socket.timeout, OSError) as e:
            print(f"Connection lost/refused ({e}). Is gamepad_bridge running in WSL? Retrying in 2 s.")
            time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
