import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('rover_camera'), 'config', 'camera_feed.yaml')
    return LaunchDescription([
        Node(
            package='rover_camera',
            executable='camera_feed',
            name='camera_feed',
            output='screen',
            parameters=[config],
        ),
    ])
