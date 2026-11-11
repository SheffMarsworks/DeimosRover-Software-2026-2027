import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'rover_camera'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        (os.path.join('share', package_name), ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        (os.path.join('share', package_name, 'assets'), glob('assets/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Khizar Ali Khan',
    maintainer_email='omairalik0@gmail.com',
    description='Publishes camera frames, or a placeholder image if no camera is available.',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'camera_feed = rover_camera.camera_feed:main'
        ],
    },
)
