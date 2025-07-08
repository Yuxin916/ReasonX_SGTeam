cmake_minimum_required(VERSION 2.8.3)
project(dummy_vlm_python)

find_package(catkin REQUIRED COMPONENTS
  rospy
  std_msgs
  sensor_msgs
  nav_msgs
  geometry_msgs
  visualization_msgs
  tf
)

catkin_package()

catkin_install_python(PROGRAMS
  scripts/dummyVLM.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY launch/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/launch
)
install(DIRECTORY data/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/data
)
