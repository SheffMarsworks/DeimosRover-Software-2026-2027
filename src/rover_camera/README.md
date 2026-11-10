# rover_camera

Publishes `sensor_msgs/Image` on `/camera/image_raw`.
Uses a USB camera when available, otherwise publishes a placeholder image
and reconnects automatically when a camera appears.

Run:
    ros2 run rover_camera camera_feed
    ros2 launch rover_camera camera_feed.launch.py

Parameters: device_index, source, width, height, fps, topic, frame_id,
retry_period_s, fourcc (default MJPG), reliable (default true).

Note: on WSL2, 640x480 images are delivered slowly through DDS. Use
-p width:=320 -p height:=240 for development there.