import os
import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image
from ament_index_python.packages import get_package_share_directory


class CameraFeed(Node):
    """Publish camera frames, or a placeholder image when no camera is available."""

    def __init__(self):
        super().__init__('camera_feed')

        self.declare_parameter('device_index', 0)
        self.declare_parameter('source', '')
        self.declare_parameter('width', 640)
        self.declare_parameter('height', 480)
        self.declare_parameter('fps', 15)
        self.declare_parameter('topic', '/camera/image_raw')
        self.declare_parameter('frame_id', 'camera_link')
        self.declare_parameter('retry_period_s', 2)
        default_image = os.path.join(
            get_package_share_directory('rover_camera'), 'assets', 'fallback.jpg')
        self.declare_parameter('fallback_image', default_image)
        self.declare_parameter('reliable', True)
        self.declare_parameter('fourcc', 'MJPG')

        self.device_index = self.get_parameter('device_index').value
        self.source = self.get_parameter('source').value
        self.width = self.get_parameter('width').value
        self.height = self.get_parameter('height').value
        self.fps = max(1, self.get_parameter('fps').value)
        self.frame_id = self.get_parameter('frame_id').value
        self.retry_period = self.get_parameter('retry_period_s').value
        topic = self.get_parameter('topic').value

        if self.get_parameter('reliable').value:
            reliability = ReliabilityPolicy.RELIABLE
        else:
            reliability = ReliabilityPolicy.BEST_EFFORT
        qos = QoSProfile(depth=5, reliability=reliability)
        self.image_pub = self.create_publisher(Image, topic, qos)
        self.bridge = CvBridge()
        self.fallback = self.load_fallback(self.get_parameter('fallback_image').value)

        self.tick = 0
        self.fallback_every = max(1, self.fps // 2)
        self.cap = self.open_camera()
        self.last_retry = self.get_clock().now()
        if self.cap is None:
            self.get_logger().warning('No camera found, publishing placeholder image.')
        else:
            self.get_logger().info('Camera opened, publishing live frames.')

        self.timer = self.create_timer(1.0 / self.fps, self.timer_callback)
        self.published = 0
        self.stats_start = self.get_clock().now()
        self.stats_timer = self.create_timer(5.0, self.report_stats)
        self.get_logger().info(f"The '{self.get_name()}' node is initialised.")

    def open_camera(self):
        src = self.source if self.source else self.device_index
        is_v4l2 = isinstance(src, int) or str(src).startswith('/dev/video')
        if is_v4l2:
            cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
        else:
            cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            cap.release()
            return None
        fourcc = self.get_parameter('fourcc').value
        if is_v4l2 and fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        return cap

    def load_fallback(self, path):
        img = cv2.imread(path) if path else None
        if img is None:
            if path:
                self.get_logger().warning(f"Could not read '{path}', using a plain grey frame.")
            img = np.full((self.height, self.width, 3), 40, dtype=np.uint8)
        return cv2.resize(img, (self.width, self.height))

    def publish_frame(self, frame):
        msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        self.image_pub.publish(msg)
        self.published += 1

    def timer_callback(self):
        self.tick += 1
        if self.cap is not None:
            ok, frame = self.cap.read()
            if ok:
                self.publish_frame(frame)
                return
            self.get_logger().warning('Camera stopped delivering frames.')
            self.cap.release()
            self.cap = None
            self.last_retry = self.get_clock().now()

        now = self.get_clock().now()
        if (now - self.last_retry).nanoseconds * 1e-9 >= self.retry_period:
            self.last_retry = now
            self.cap = self.open_camera()
            if self.cap is not None:
                self.get_logger().info('Camera connected, publishing live frames.')
                return
        if self.tick % self.fallback_every == 0:
            self.publish_frame(self.fallback)
            self.get_logger().warning('No camera: publishing placeholder image.',
                                      throttle_duration_sec=10.0)

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def report_stats(self):
        now = self.get_clock().now()
        secs = max(1e-6, (now - self.stats_start).nanoseconds * 1e-9)
        self.get_logger().debug(f'Node published {self.published / secs:.1f} frames/s')
        self.published = 0
        self.stats_start = now


def main(args=None):
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = CameraFeed()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print(f'{node.get_name()} received a shutdown request (Ctrl+C).')
    finally:
        node.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
