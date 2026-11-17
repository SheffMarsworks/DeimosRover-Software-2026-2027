#!/usr/bin/env python3
"""Publish gamepad state streamed from Windows as sensor_msgs/Joy on /joy.

WSL can't read USB gamepads, so tools/windows_gamepad_sender.py reads the controller on Windows
and streams it here over TCP. The /joy layout matches joy_node with an Xbox-style (XInput)
controller on Linux, so config written for joy_node (e.g. rover_controller/config/joy_teleop.yaml)
works unchanged:

axes:    0 left stick X (left = +1)    1 left stick Y (up = +1)    2 LT (1 released, -1 fully pressed)
         3 right stick X (left = +1)   4 right stick Y (up = +1)   5 RT (1 released, -1 fully pressed)
         6 D-pad X (left = +1)         7 D-pad Y (up = +1)
buttons: 0 A  1 B  2 X  3 Y  4 LB  5 RB  6 Back  7 Start  8 Guide (always 0)  9 L-stick click  10 R-stick click

Usage:
    ros2 run rover_gamepad gamepad_bridge
    ros2 run rover_gamepad gamepad_bridge --ros-args -p port:=5005 -p deadzone:=0.1
"""

import json
import math
import socket
import threading
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Joy

# XInput button bit flags
DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT = 0x0001, 0x0002, 0x0004, 0x0008
START, BACK, LEFT_THUMB, RIGHT_THUMB = 0x0010, 0x0020, 0x0040, 0x0080
LEFT_SHOULDER, RIGHT_SHOULDER = 0x0100, 0x0200
A, B, X, Y = 0x1000, 0x2000, 0x4000, 0x8000

# XInput flag for each index of Joy.buttons (None = not available through XInput)
BUTTON_ORDER = [A, B, X, Y, LEFT_SHOULDER, RIGHT_SHOULDER, BACK, START, None, LEFT_THUMB, RIGHT_THUMB]

# Sticks centred, triggers released, nothing pressed
NEUTRAL_AXES = [0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
NEUTRAL_BUTTONS = [0] * len(BUTTON_ORDER)


def apply_deadzone(value, deadzone):
    """Zero small stick values (drift), rescaling the rest so full tilt still gives +/-1."""
    if abs(value) < deadzone:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)


def stick(raw):
    """XInput stick (-32768..32767) -> -1..1, clamped."""
    return max(-1.0, min(1.0, raw / 32767.0))


def trigger(raw):
    """XInput trigger (0..255, clamped) -> 1 (released) .. -1 (fully pressed), like joy_node."""
    raw = max(0, min(255, raw))
    return 1.0 - 2.0 * raw / 255.0


def parse_state(state):
    """Return the raw controller fields, or None if any is missing or not a finite number."""
    values = {}
    for key in ("buttons", "lt", "rt", "lx", "ly", "rx", "ry"):
        v = state.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
        values[key] = v
    if not isinstance(values["buttons"], int):
        return None
    return values


def to_joy_lists(state, deadzone):
    """Convert one raw XInput state dict into (axes, buttons) lists for sensor_msgs/Joy."""
    b = state["buttons"]
    axes = [
        apply_deadzone(-stick(state["lx"]), deadzone),
        apply_deadzone(stick(state["ly"]), deadzone),
        trigger(state["lt"]),
        apply_deadzone(-stick(state["rx"]), deadzone),
        apply_deadzone(stick(state["ry"]), deadzone),
        trigger(state["rt"]),
        float(bool(b & DPAD_LEFT)) - float(bool(b & DPAD_RIGHT)),
        float(bool(b & DPAD_UP)) - float(bool(b & DPAD_DOWN)),
    ]
    buttons = [int(bool(b & flag)) if flag else 0 for flag in BUTTON_ORDER]
    return axes, buttons


class GamepadBridge(Node):
    def __init__(self):
        super().__init__("gamepad_bridge")

        self.declare_parameter("host", "127.0.0.1")
        self.declare_parameter("port", 5005)
        self.declare_parameter("deadzone", 0.05)
        self.declare_parameter("timeout", 0.5)  # seconds without data before going neutral
        host = self.get_parameter("host").value
        port = self.get_parameter("port").value
        self.deadzone = self.get_parameter("deadzone").value
        self.timeout = self.get_parameter("timeout").value
        if not 0.0 <= self.deadzone < 1.0:
            raise ValueError(f"deadzone must be >= 0 and < 1, got {self.deadzone}")
        if self.timeout <= 0.0:
            raise ValueError(f"timeout must be > 0, got {self.timeout}")

        self.joy_pub = self.create_publisher(Joy, "joy", 10)

        # Shared between the socket thread and the timeout timer
        self.lock = threading.Lock()
        self.active = False  # True while we're publishing live controller data
        self.last_rx = 0.0
        self.controller_connected = None

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(1)
        self.server.settimeout(0.5)
        threading.Thread(target=self.serve, daemon=True).start()

        self.create_timer(0.1, self.check_timeout)
        self.get_logger().info(
            f"Waiting for windows_gamepad_sender.py on {host}:{port}, publishing on /joy"
        )

    def serve(self):
        """Accept one sender at a time and handle its newline-separated JSON messages."""
        while rclpy.ok():
            try:
                conn, addr = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                return  # server socket closed during shutdown

            self.get_logger().info(f"Windows sender connected ({addr[0]})")
            with conn:
                conn.settimeout(0.5)
                buf = b""
                while rclpy.ok():
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    *lines, buf = buf.split(b"\n")
                    for line in lines:
                        self.handle_line(line)

            self.get_logger().warn("Windows sender disconnected")
            self.controller_connected = None
            self.go_neutral()

    def handle_line(self, line):
        try:
            state = json.loads(line)
        except ValueError:
            state = None
        if not isinstance(state, dict):
            self.get_logger().warn(f"Ignoring malformed message: {line[:80]!r}")
            return

        if not state.get("connected"):
            if self.controller_connected is not False:
                self.get_logger().warn("Sender is running but no controller is connected on Windows")
            self.controller_connected = False
            self.go_neutral()
            return

        values = parse_state(state)
        if values is None:
            self.get_logger().warn(f"Ignoring message with missing or invalid fields: {line[:80]!r}")
            return

        if not self.controller_connected:
            self.get_logger().info("Controller connected")
        self.controller_connected = True

        axes, buttons = to_joy_lists(values, self.deadzone)
        with self.lock:
            self.last_rx = time.monotonic()
            self.active = True
            self.publish(axes, buttons)

    def check_timeout(self):
        with self.lock:
            stale = self.active and time.monotonic() - self.last_rx > self.timeout
        if stale:
            self.get_logger().warn(f"No controller data for {self.timeout}s, publishing neutral state")
            self.go_neutral()

    def go_neutral(self):
        """Publish one 'nothing pressed' message so anything driving from /joy stops."""
        with self.lock:
            if self.active:
                self.publish(NEUTRAL_AXES, NEUTRAL_BUTTONS)
                self.active = False

    def publish(self, axes, buttons):
        msg = Joy()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "joy"
        msg.axes = axes
        msg.buttons = buttons
        self.joy_pub.publish(msg)


def main():
    rclpy.init()
    node = GamepadBridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.server.close()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
