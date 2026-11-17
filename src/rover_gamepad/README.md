# rover_gamepad

Reads a gamepad and publishes its state as a ROS 2 `sensor_msgs/msg/Joy` message on `/joy`.
Nothing in the rover consumes `/joy` from this package yet. Driving the rover from it is a later task.

This README is the specification for the package: it describes everything the node takes in, everything it puts out, and how it behaves, including edge cases, timings and log messages.

---

## 1. Why it works this way

The software team develops on Windows + WSL2 (Ubuntu 22.04). WSL can't read USB gamepads:
- In **X (XInput) mode** the gamepad needs the Linux `xpad` driver, which the WSL kernel doesn't include.
- In **D (DirectInput) mode** the gamepad can be passed into WSL with `usbipd`, but no button or stick data arrives (tested with a Logitech F310).

So the gamepad is read on **Windows**, where its drivers work, and streamed to a ROS node in **WSL**:

```
Gamepad (F310, switch on X)
   │ USB
   ▼
windows_gamepad_sender.py      (Windows, plain Python 3)
   │ TCP, newline-separated JSON, default 127.0.0.1:5005
   ▼
gamepad_bridge node            (WSL, ROS 2 Humble)
   │ publishes
   ▼
/joy   sensor_msgs/msg/Joy
```

On native Linux, use the standard driver `ros2 run joy joy_node` instead. It publishes the same `/joy` layout.

---

## 2. Package contents

| File | Runs on | Purpose |
|---|---|---|
| `rover_gamepad/gamepad_bridge.py` | WSL / Linux | The ROS 2 node. A TCP server that receives gamepad states, converts them, and publishes `/joy`. |
| `tools/windows_gamepad_sender.py` | Windows | Reads the gamepad through Windows' XInput API and sends its state to the node. Uses only the Python standard library. Not installed by colcon; you run it directly from Windows. |
| `package.xml` | build | Package metadata and dependencies (`rclpy`, `sensor_msgs`, `joy`). |
| `setup.py`, `setup.cfg` | build | Installs the `gamepad_bridge` executable so `ros2 run rover_gamepad gamepad_bridge` works. |
| `resource/rover_gamepad` | build | Empty marker file that registers the package with ROS. |
| `rover_gamepad/__init__.py` | build | Empty; makes the folder a Python package. |

---

## 3. Setup

### One-time
1. **Windows:** Python 3 must be installed (`python --version` in PowerShell). No extra packages are needed.
2. **WSL:** build the package.
   ```bash
   cd ~/marsworks/DeimosRover-2025-2026-
   source /opt/ros/humble/setup.bash
   colcon build --symlink-install --packages-select rover_gamepad
   ```
3. **Gamepad:** the Logitech F310/F710 switch must be on **X**. In X mode Windows lists it as USB `046d:c21d`; in D mode it's `046d:c216` and can't be read.
4. If the gamepad was ever bound to `usbipd`, give it back to Windows. In an **Administrator** PowerShell, run `usbipd unbind --busid <id>` (find the id with `usbipd list`), then replug the gamepad.

### Every time (three terminals)
```bash
# Terminal 1 (WSL): start the node
cd ~/marsworks/DeimosRover-2025-2026- && . install/setup.bash
ros2 run rover_gamepad gamepad_bridge
```
```powershell
# Terminal 2 (Windows PowerShell): start the sender. Replace <user> with your WSL username.
python \\wsl.localhost\Ubuntu-22.04\home\<user>\marsworks\DeimosRover-2025-2026-\src\rover_gamepad\tools\windows_gamepad_sender.py
```
```bash
# Terminal 3 (WSL): watch the output
cd ~/marsworks/DeimosRover-2025-2026- && . install/setup.bash
ros2 topic echo /joy
```
You can start the node and the sender in either order; the sender retries until the node is up. Stop everything with Ctrl+C.

---

## 4. Node: `gamepad_bridge`

| | |
|---|---|
| Package / executable | `rover_gamepad` / `gamepad_bridge` |
| Node name | `gamepad_bridge` |
| Publishes | `/joy` (`sensor_msgs/msg/Joy`) |
| Subscribes | nothing |
| Services / actions | none |
| Other input | TCP server (see §6) |

### 4.1 Parameters
They're read **once at startup**; changing them later with `ros2 param set` has no effect. Set them with `--ros-args -p name:=value`.

| Name | Type | Default | Valid range | Meaning |
|---|---|---|---|---|
| `host` | string | `127.0.0.1` | any local address | Address the TCP server listens on |
| `port` | int | `5005` | free TCP port | Port the TCP server listens on |
| `deadzone` | double | `0.05` | `0 <= deadzone < 1` | Stick deadzone (see §5.2). Doesn't apply to triggers or the D-pad. |
| `timeout` | double | `0.5` | `> 0` | Seconds without valid gamepad data before the node publishes the neutral message (see §7) |

The topic name can be remapped like any ROS topic, e.g. `--ros-args -r joy:=/controller/joy`.

### 4.2 Startup failures
The node exits with a non-zero exit code and an error message if:
- `deadzone` is outside `0 <= deadzone < 1`. Message: `deadzone must be >= 0 and < 1, got <value>`
- `timeout` is `<= 0`. Message: `timeout must be > 0, got <value>`
- the port is already in use, e.g. another `gamepad_bridge` is running. Message: `OSError: [Errno 98] Address already in use`

---

## 5. Output: `/joy`

- **Type:** `sensor_msgs/msg/Joy`
- **QoS:** ROS 2 default (reliable, volatile, keep last 10)
- **`header.frame_id`:** always `"joy"`. This is a label only; `/joy` isn't part of the TF tree.
- **`header.stamp`:** the node's clock at the moment of publishing (system time, or sim time if `use_sim_time` is true)
- **`axes`:** always exactly 8 floats
- **`buttons`:** always exactly 11 ints, each 0 or 1

The layout matches `joy_node` with an Xbox-style controller on Linux.

### 5.1 Layout

| `axes` index | Control | Value range |
|---|---|---|
| 0 | Left stick, horizontal | +1.0 full left … -1.0 full right |
| 1 | Left stick, vertical | +1.0 full up … -1.0 full down |
| 2 | Left trigger (LT) | +1.0 released … -1.0 fully pressed |
| 3 | Right stick, horizontal | +1.0 full left … -1.0 full right |
| 4 | Right stick, vertical | +1.0 full up … -1.0 full down |
| 5 | Right trigger (RT) | +1.0 released … -1.0 fully pressed |
| 6 | D-pad horizontal | +1.0 left, -1.0 right, 0.0 neither or both |
| 7 | D-pad vertical | +1.0 up, -1.0 down, 0.0 neither or both |

| `buttons` index | Button |
|---|---|
| 0 | A |
| 1 | B |
| 2 | X |
| 3 | Y |
| 4 | LB (left bumper) |
| 5 | RB (right bumper) |
| 6 | Back |
| 7 | Start |
| 8 | Guide. **Always 0**, because XInput doesn't report it. |
| 9 | Left stick click |
| 10 | Right stick click |

**Neutral message** (nothing pressed, sticks centred, triggers released):
`axes = [0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0]`, `buttons = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]`

### 5.2 Conversion from the raw input
The raw input fields are described in §6.2. The functions used below are:

```
stick(raw)   = clamp(raw / 32767, -1.0, 1.0)
trigger(raw) = 1.0 - 2.0 * clamp(raw, 0, 255) / 255
dz(v)        = 0.0                                   if |v| < deadzone
             = sign(v) * (|v| - deadzone) / (1 - deadzone)   otherwise
```

| Output | Formula |
|---|---|
| `axes[0]` | `dz(-stick(lx))` |
| `axes[1]` | `dz(stick(ly))` |
| `axes[2]` | `trigger(lt)` |
| `axes[3]` | `dz(-stick(rx))` |
| `axes[4]` | `dz(stick(ry))` |
| `axes[5]` | `trigger(rt)` |
| `axes[6]` | `(1 if DPAD_LEFT bit set else 0) - (1 if DPAD_RIGHT bit set else 0)` |
| `axes[7]` | `(1 if DPAD_UP bit set else 0) - (1 if DPAD_DOWN bit set else 0)` |
| `buttons[i]` | `1` if that button's bit is set in `buttons`, else `0` (bit table in §6.2) |

Consequences:
- After the deadzone, a full stick still reaches exactly ±1.0, and the output is continuous: there's no jump at the deadzone edge.
- Out-of-range raw values are clamped. A stick beyond ±32767 gives ±1.0; a trigger below 0 gives 1.0, and above 255 gives -1.0.
- Triggers and the D-pad have no deadzone.

### 5.3 Worked examples (default deadzone 0.05)

| Raw input | Output |
|---|---|
| all zero, `buttons: 0` | neutral message |
| `ly: 32767` | `axes[1] = 1.0` |
| `ly: -32768` | `axes[1] = -1.0` |
| `ly: 16384` | `axes[1] ≈ 0.4737` |
| `lx: -32768` (full right) | `axes[0] = 1.0` |
| `lx: 32767` (full left) | `axes[0] = -1.0` |
| `lx: 1000` (≈0.031, inside deadzone) | `axes[0] = 0.0` |
| `lx: 1638` (≈0.04999) | `axes[0] = 0.0` |
| `lx: 99999` (out of range) | `axes[0] = -1.0` |
| `lt: 255` | `axes[2] = -1.0` |
| `lt: 128` | `axes[2] ≈ -0.00392` |
| `lt: 999` (out of range) | `axes[2] = -1.0` |
| `rt: -5` (out of range) | `axes[5] = 1.0` |
| `buttons: 4096` (A) | `buttons[0] = 1`, the rest 0 |
| `buttons: 4608` (A + RB) | `buttons[0] = 1`, `buttons[5] = 1` |
| `buttons: 4` (D-pad left) | `axes[6] = 1.0` |
| `buttons: 12` (D-pad left + right) | `axes[6] = 0.0` |
| `buttons: 3` (D-pad up + down) | `axes[7] = 0.0` |

---

## 6. Input: the TCP connection

### 6.1 Connection rules
- The node is a TCP server on `host:port` (default `127.0.0.1:5005`).
- It serves **one sender at a time**. While one is connected, the operating system queues further connections, and their data is processed only after the current sender disconnects.
- Each message is one **JSON object followed by a newline (`\n`)**, UTF-8 encoded. A trailing `\r` is tolerated.
- Messages may be split across TCP packets, and several may arrive in one packet. Either way, each complete line is handled once, in order.
- If the sender disconnects, any partial line after the last `\n` is discarded.
- Once a sender disconnects, the node accepts the next one; it never needs restarting.

### 6.2 Message format
```json
{"connected": true, "packet": 1234, "buttons": 4096, "lt": 0, "rt": 0, "lx": 0, "ly": 0, "rx": 0, "ry": 0}
```
```json
{"connected": false}
```

| Field | Type | Range | Meaning |
|---|---|---|---|
| `connected` | bool | | `true`: the message carries gamepad data. Missing, `false`, `null` or `0` means no gamepad is connected on Windows (see §7). |
| `buttons` | integer | 0–65535 | XInput button bitmask (table below). Required when `connected` is true. |
| `lt`, `rt` | number | 0–255 | Left/right trigger, 0 = released. Required when `connected` is true. |
| `lx`, `ly`, `rx`, `ry` | number | -32768–32767 | Stick positions. X is positive to the right; Y is positive **up**. Required when `connected` is true. |
| `packet` | integer | | XInput packet counter. Optional; the node ignores it. |
| anything else | | | ignored |

XInput `buttons` bits:

| Bit (hex) | Decimal | Button |
|---|---|---|
| `0x0001` | 1 | D-pad up |
| `0x0002` | 2 | D-pad down |
| `0x0004` | 4 | D-pad left |
| `0x0008` | 8 | D-pad right |
| `0x0010` | 16 | Start |
| `0x0020` | 32 | Back |
| `0x0040` | 64 | Left stick click |
| `0x0080` | 128 | Right stick click |
| `0x0100` | 256 | LB |
| `0x0200` | 512 | RB |
| `0x1000` | 4096 | A |
| `0x2000` | 8192 | B |
| `0x4000` | 16384 | X |
| `0x8000` | 32768 | Y |

Other bits are ignored.

### 6.3 Invalid messages
Invalid messages are **ignored with a warning**. Nothing is published for them, the node keeps running, and later valid messages are processed normally.

| Message | Result |
|---|---|
| Not valid JSON, including an empty line | warning `Ignoring malformed message: ...` |
| Valid JSON but not an object, e.g. `[1,2,3]`, `5` or `"hi"` | warning `Ignoring malformed message: ...` |
| `connected` true, but a required field is missing, not a number, a bool, `NaN` or infinite, or `buttons` isn't an integer | warning `Ignoring message with missing or invalid fields: ...` |

Ignored messages **don't count as gamepad data** for the timeout in §7.

---

## 7. States and timing

The node is either **active** (publishing live gamepad data) or **inactive**.

- **At startup** it's inactive and publishes **nothing**, so `/joy` exists but has no messages.
- **Each valid `connected: true` message** publishes exactly one `/joy` message and makes the node active. Nothing is rate-limited or de-duplicated: identical repeated inputs are each republished.
- **Going inactive publishes the neutral message (§5.1) exactly once.** It's triggered by whichever happens first:
  1. a `connected: false` message, which takes effect immediately;
  2. the sender disconnecting, which also takes effect immediately;
  3. no valid gamepad message for longer than `timeout` seconds. This is checked every 0.1 s, so the neutral message appears between `timeout` and about `timeout + 0.1` s after the last valid message.
- **While inactive, nothing is published**, however many `connected: false` or invalid messages arrive, and no further neutral messages are sent.
- **The next valid `connected: true` message** makes the node active again.
- **Stopping the node** (Ctrl+C) does **not** publish a neutral message.

With the Windows sender running, the node receives a message at least every ~50–65 ms even when nothing changes (a keepalive), so the timeout never triggers in normal use. While inputs are changing, the sender sends up to one message per poll, roughly 60–100 Hz depending on Windows timer resolution. Exact rates vary, so avoid tight timing assertions.

### 7.1 Log messages
| Level | Text | When |
|---|---|---|
| INFO | `Waiting for windows_gamepad_sender.py on <host>:<port>, publishing on /joy` | startup. It always says `/joy`, even if the topic is remapped. |
| INFO | `Windows sender connected (<ip>)` | a sender connects |
| INFO | `Controller connected` | first valid gamepad message after startup, after a sender reconnects, or after `connected: false` |
| WARN | `Sender is running but no controller is connected on Windows` | first `connected: false` after the node was in any other state; not repeated for consecutive ones |
| WARN | `Ignoring malformed message: <first 80 bytes>` | see §6.3 |
| WARN | `Ignoring message with missing or invalid fields: <first 80 bytes>` | see §6.3 |
| WARN | `No controller data for <timeout>s, publishing neutral state` | timeout case in §7 |
| WARN | `Windows sender disconnected` | the sender closes the connection |

---

## 8. Windows sender: `tools/windows_gamepad_sender.py`

```
python windows_gamepad_sender.py [--host 127.0.0.1] [--port 5005] [--player 0] [--rate 100]
```

| Option | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Node address. From Windows, `127.0.0.1` reaches WSL. |
| `--port` | `5005` | Node port |
| `--player` | `0` | XInput controller slot, 0–3 |
| `--rate` | `100` | Polling rate in Hz (in practice limited by Windows timer resolution) |

Behaviour:
- **Platform:** Windows only, because it uses the XInput DLL. The gamepad must be in XInput mode (switch on **X**).
- **Polling:** it reads the gamepad every poll. It sends a message when the XInput packet number changes (an input changed), or when 50 ms have passed since the last send.
- **No gamepad in the slot:** it sends `{"connected": false}` on the same 50 ms keepalive.
- **Connection:** if the connection is refused or lost, it prints a message and retries every 2 s, forever.
- **Stopping:** Ctrl+C exits.
- **Console messages:**
  - `Connecting to gamepad_bridge at <host>:<port> ...`
  - `Connected. Streaming controller state (Ctrl+C to stop).`
  - `Controller connected.`
  - `No controller in XInput slot <n> (is the switch set to X?)`
  - `Connection lost/refused (<error>). Is gamepad_bridge running in WSL? Retrying in 2 s.`

---

## 9. Testing without a gamepad
The node only sees TCP messages, so any program can stand in for the Windows sender. Use a spare port and topic so you don't clash with a real session:

```bash
# Terminal 1
ros2 run rover_gamepad gamepad_bridge --ros-args -p port:=5099 -r joy:=/test_joy
# Terminal 2
ros2 topic echo /test_joy
# Terminal 3: type one JSON message per line and press Enter after each
nc 127.0.0.1 5099
{"connected": true, "buttons": 4096, "lt": 0, "rt": 0, "lx": 0, "ly": 32767, "rx": 0, "ry": 0}
```

The same can be scripted in Python:
```python
import json, socket, time
s = socket.create_connection(("127.0.0.1", 5099))
s.sendall((json.dumps({"connected": True, "buttons": 4096, "lt": 0, "rt": 0,
                       "lx": 0, "ly": 32767, "rx": 0, "ry": 0}) + "\n").encode())
time.sleep(1)
s.close()
```

---

## 10. Known limitations
- The Guide button is always 0 (XInput doesn't expose it).
- Only one sender is served at a time.
- Stopping the node doesn't publish a neutral message.
- Parameters can't be changed while the node is running.
- The startup log always says `/joy`, even when the topic is remapped.
- The TCP connection has no authentication. It's intended for `127.0.0.1` only.
