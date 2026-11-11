rover_camera

Publishes `sensor_msgs/Image` on `/camera/image_raw`.
Uses a camera when available, otherwise publishes a placeholder image
and reconnects automatically when a camera appears.

Node and executable : `camera_feed`
Output topic : `/camera/image_raw`
Message type : `sensor_msgs/msg/Image`, encoding `bgr8`
QoS : Reliable, depth 5 (`reliable:=false` gives best-effort)
Header : `stamp` is the time of publishing, `frame_id` is `camera_link`
Inputs : None. The node subscribes to no topics and is configured with parameters

Behaviour: 
  - With a camera, the node publishes live frames at `fps`.
  - With no camera, or if frames stop, it publishes the placeholder at about
    2 Hz (fps / (fps // 2)) and retries the camera every `retry_period_s` seconds.
  - Starting without a camera is not an error, and unplugging and re-plugging
    works without a restart.
  - Ctrl+C releases the camera and exits cleanly.

Build:
    colcon build --symlink-install --packages-select rover_camera
. install/setup.bash

Run:
    ros2 run rover_camera camera_feed
    ros2 launch rover_camera camera_feed.launch.py

Examples:
    ros2 run rover_camera camera_feed --ros-args -p width:=320 -p height:=240
    ros2 run rover_camera camera_feed --ros-args -p device_index:=2 -p fps:=10
    ros2 run rover_camera camera_feed --ros-args -p source:=/path/to/video.mp4
    ros2 run rover_camera camera_feed --ros-args -p device_index:=9

The last example uses a camera number that does not exist, so it publishes the
placeholder.

Check output:
    ros2 topic hz /camera/image_raw
    ros2 topic echo --once /camera/image_raw --field width
    ros2 run rqt_image_view rqt_image_view /camera/image_raw



| Parameter | Type | Default | Meaning |

| `device_index` | integer | `0` | Camera number (`/dev/video0` is 0) |
| `source` | string | `""` | Video file, `/dev/video*` path or stream URL. Overrides `device_index` |
| `width` | integer | `640` | Requested frame width |
| `height` | integer | `480` | Requested frame height |
| `fps` | integer | `15` | Publishing rate, and frame rate requested from the camera |
| `fourcc` | string | `MJPG` | Pixel format requested from the camera. Empty turns it off |
| `reliable` | boolean | `true` | Reliable QoS, or best-effort when false |
| `topic` | string | `/camera/image_raw` | Output topic |
| `frame_id` | string | `camera_link` | Header frame name |
| `retry_period_s` | integer | `2` | Seconds between attempts to reopen a missing camera |
| `fallback_image` | string | packaged `assets/fallback.jpg` | Image published when no camera is available |





