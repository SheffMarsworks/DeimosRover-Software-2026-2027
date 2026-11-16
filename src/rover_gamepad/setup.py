import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'rover_gamepad'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        (os.path.join('share', package_name), ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='adam',
    maintainer_email='adam.mohamed.shafik@gmail.com',
    description='Reads a gamepad and publishes it as sensor_msgs/Joy on /joy.',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'gamepad_bridge = rover_gamepad.gamepad_bridge:main',
        ],
    },
)
