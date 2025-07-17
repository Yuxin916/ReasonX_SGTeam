cmake_minimum_required(VERSION 2.8.3)
project(occupancy_map_generator)

find_package(catkin REQUIRED)

catkin_package(
  INCLUDE_DIRS include
  LIBRARIES occupancy_map_generator
  CATKIN_DEPENDS rospy std_msgs
  DEPENDS system_lib
)

include_directories(include)

install(PROGRAMS
  src/occupancy_map_generator.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY launch
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/launch
)

install(DIRECTORY include
  DESTINATION ${CATKIN_PACKAGE_INCLUDE_DESTINATION}
)