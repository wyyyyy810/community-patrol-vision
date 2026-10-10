#!/bin/bash
export LIBGL_ALWAYS_SOFTWARE=1
export QT_QPA_PLATFORM=xcb
source /opt/ros/jazzy/setup.bash
ros2 run rqt_image_view rqt_image_view
