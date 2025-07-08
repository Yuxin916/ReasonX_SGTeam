#!/usr/bin/env python3

import rospy
import math
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__)))

from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image
from geometry_msgs.msg import Pose2D
from visualization_msgs.msg import Marker
from std_msgs.msg import String, Int32

# === Internal Utilities ===
from utils.decide import decide_numerical_answer_random, decide_traj_follow
from utils.publish import (
    pub_numerical_answer,
    pub_path_waypoints,
    pub_object_waypoint,
    pub_object_marker,
    del_object_marker
)
from utils.read_in import read_object_list_file
from utils.handler import (
    camera_handler,
    pose_handler,
    question_handler,
    get_question,
    reset_question,
    get_pose
)

"""
Read a question as a ROS String message on the `/challenge_question` topic. 
The dummy model will then:
    either publish an integer as an Int32 message, 
    send bounding box visualization markers for object reference, 
    or waypoints to guide vehicle navigation. 
    
The three types of messages are listed below. To integrate the a model with the system, please modify the system startup script.
- Numerical response: ROS Int32 message on topic `/numerical_response`, containing an integer answering a numerical question.
- Visualization marker: ROS Marker message on topic `/selected_object_marker`, containing object label and bounding box of the selected object.
- Waypoint: ROS Pose2D message on topic `/way_point_with_heading` (neglect the heading for this year’s challenge).
"""

# === Globals ===
waypoint_file_dir = ""
object_list_file_dir = ""
waypointReachDis = 1.0

# Dummy object info for marker and navigation
objID = 0
objMidX, objMidY, objMidZ = 0.0, 0.0, 0.0
objL, objW, objH, objHeading = 0.0, 0.0, 0.0, 0.0
objLabel = ""

def main():
    # Initializes the ROS node
    rospy.init_node("dummyVLM", anonymous=False)
    rospy.loginfo(">>> dummyVLM node started")

    global waypoint_file_dir, object_list_file_dir, waypointReachDis
    global objID, objMidX, objMidY, objMidZ, objL, objW, objH, objHeading, objLabel

    # === Load Params ===
    waypoint_file_dir = rospy.get_param("~waypoint_file_dir")
    object_list_file_dir = rospy.get_param("~object_list_file_dir")
    waypointReachDis = rospy.get_param("~waypointReachDis", 1.0)

    rospy.loginfo(f"[PARAM] waypoint_file_dir = {waypoint_file_dir}")
    rospy.loginfo(f"[PARAM] object_list_file_dir = {object_list_file_dir}")
    rospy.loginfo(f"[PARAM] waypointReachDis = {waypointReachDis}")

    # === Check files exist ===
    if not os.path.exists(waypoint_file_dir):
        rospy.logfatal(f"Waypoint file not found: {waypoint_file_dir}")
        rospy.signal_shutdown("Missing waypoint file")
        return

    if not os.path.exists(object_list_file_dir):
        rospy.logfatal(f"Object list file not found: {object_list_file_dir}")
        rospy.signal_shutdown("Missing object list file")
        return

    # === ROS Subscribers ===
    rospy.Subscriber("/camera/image", Image, camera_handler)
    # rospy.Subscriber("/registered_scan", PointCloud2, registered_scan_handler)
    # rospy.Subscriber("/sensor_scan", PointCloud2, sensor_scan_handler)
    # rospy.Subscriber("/traversable_area", PointCloud2, traversable_area_handler)
    rospy.Subscriber("/state_estimation", Odometry, pose_handler)
    rospy.Subscriber("/challenge_question", String, question_handler)

    # === ROS Publishers ===
    waypoint_pub = rospy.Publisher("/way_point_with_heading", Pose2D, queue_size=5)
    marker_pub = rospy.Publisher("selected_object_marker", Marker, queue_size=5)
    numerical_pub = rospy.Publisher("/numerical_response", Int32, queue_size=5)


    # === Main Loop ===
    rospy.loginfo("Awaiting question...")
    rate = rospy.Rate(10)
    while not rospy.is_shutdown():
        q = get_question()
        if not q:
            rospy.logdebug("No question received yet...")
            rate.sleep()
            continue

        q_lower = q.lower()

        if "find" in q_lower:
            rospy.loginfo("Received -> OBJECT question...")

            obj_data = read_object_list_file(object_list_file_dir)
            objID, objMidX, objMidY, objMidZ, objL, objW, objH, objHeading, objLabel = obj_data
            rospy.loginfo(f"Loaded object: {objLabel} at ({objMidX}, {objMidY})")

            obj_info = {
                'id': objID,
                'mid_x': objMidX,
                'mid_y': objMidY,
                'mid_z': objMidZ,
                'l': objL,
                'w': objW,
                'h': objH,
                'heading': objHeading,
                'label': objLabel,
            }

            vehicleX, vehicleY = get_pose()
            rospy.loginfo(f"Using current vehicle pose: x={vehicleX:.2f}, y={vehicleY:.2f}")

            pub_object_marker(marker_pub, obj_info)
            pub_object_waypoint(waypoint_pub, objMidX, objMidY, waypointReachDis)

        elif "how many" in q_lower:
            rospy.loginfo("Received -> HOW MANY question...")
            del_object_marker(marker_pub, objID, objLabel)
            number = decide_numerical_answer_random()
            pub_numerical_answer(numerical_pub, number)

        else:
            rospy.loginfo("Received -> INSTRUCTION following question...")
            del_object_marker(marker_pub, objID, objLabel)
            waypointX, waypointY, waypointHeading = decide_traj_follow(waypoint_file_dir)
            vehicleX, vehicleY = get_pose()
            rospy.loginfo(f"Using current vehicle pose: x={vehicleX:.2f}, y={vehicleY:.2f}")
            pub_path_waypoints(waypoint_pub, waypointX, waypointY, waypointHeading, waypointReachDis)

        reset_question()
        rospy.loginfo("Awaiting question...")


if __name__ == "__main__":
    main()
