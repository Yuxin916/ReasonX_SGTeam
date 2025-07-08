#!/usr/bin/env python3

import rospy
import math
import random
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Pose2D
from visualization_msgs.msg import Marker
from std_msgs.msg import String, Int32
import tf
import os


waypoint_file_dir = ""
object_list_file_dir = ""
waypointReachDis = 1.0

waypointX, waypointY, waypointHeading = [], [], []

objID = 0
objMidX, objMidY, objMidZ = 0.0, 0.0, 0.0
objL, objW, objH, objHeading = 0.0, 0.0, 0.0, 0.0
objLabel = ""

vehicleX, vehicleY = 0.0, 0.0
question = ""


def read_waypoint_file():
    global waypointX, waypointY, waypointHeading
    with open(waypoint_file_dir, 'r') as f:
        while True:
            line = f.readline().strip()
            if line == "end_header":
                break
            if line.startswith("element vertex"):
                pointNum = int(line.split()[-1])

        for _ in range(pointNum):
            line = f.readline().strip().split()
            if len(line) < 3:
                rospy.logerr("Invalid waypoint format.")
                exit(1)
            x, y, heading = map(float, line)
            waypointX.append(x)
            waypointY.append(y)
            waypointHeading.append(heading)


def read_object_list_file():
    global objID, objMidX, objMidY, objMidZ, objL, objW, objH, objHeading, objLabel
    with open(object_list_file_dir, 'r') as f:
        parts = []
        while len(parts) < 9:
            parts += f.readline().strip().split()

        objID = int(parts[0])
        objMidX = float(parts[1])
        objMidY = float(parts[2])
        objMidZ = float(parts[3])
        objL = float(parts[4])
        objW = float(parts[5])
        objH = float(parts[6])
        objHeading = float(parts[7])
        objLabel = parts[8].strip('"')  # remove outer quotes if any

        # Join remaining parts as label if label has spaces
        if objLabel[-1] != '"':
            rest = []
            while True:
                word = f.readline().strip()
                rest.append(word)
                if word.endswith('"'):
                    break
            objLabel += ' ' + ' '.join(rest).strip('"')


def pose_handler(msg):
    global vehicleX, vehicleY
    vehicleX = msg.pose.pose.position.x
    vehicleY = msg.pose.pose.position.y


def question_handler(msg):
    global question
    question = msg.data
    rospy.loginfo("Received question: %s", question)


def pub_path_waypoints(waypoint_pub):
    if not waypointX:
        rospy.logerr("No waypoint available, exiting.")
        exit(1)

    waypoint_id = 0
    waypoint_msg = Pose2D(x=waypointX[waypoint_id], y=waypointY[waypoint_id], theta=waypointHeading[waypoint_id])
    waypoint_pub.publish(waypoint_msg)

    rate = rospy.Rate(100)
    while not rospy.is_shutdown():
        dx = vehicleX - waypointX[waypoint_id]
        dy = vehicleY - waypointY[waypoint_id]
        if math.hypot(dx, dy) < waypointReachDis:
            if waypoint_id == len(waypointX) - 1:
                break
            waypoint_id += 1
            waypoint_msg = Pose2D(x=waypointX[waypoint_id], y=waypointY[waypoint_id], theta=waypointHeading[waypoint_id])
            waypoint_pub.publish(waypoint_msg)
        rate.sleep()


def pub_object_waypoint(waypoint_pub):
    waypoint_msg = Pose2D(x=objMidX, y=objMidY, theta=0)
    waypoint_pub.publish(waypoint_msg)


def pub_object_marker(marker_pub):
    marker = Marker()
    marker.header.frame_id = "map"
    marker.header.stamp = rospy.Time.now()
    marker.ns = objLabel
    marker.id = objID
    marker.action = Marker.ADD
    marker.type = Marker.CUBE
    marker.pose.position.x = objMidX
    marker.pose.position.y = objMidY
    marker.pose.position.z = objMidZ
    quaternion = tf.transformations.quaternion_from_euler(0, 0, objHeading)
    marker.pose.orientation.x = quaternion[0]
    marker.pose.orientation.y = quaternion[1]
    marker.pose.orientation.z = quaternion[2]
    marker.pose.orientation.w = quaternion[3]
    marker.scale.x = objL
    marker.scale.y = objW
    marker.scale.z = objH
    marker.color.a = 0.5
    marker.color.r = 0.0
    marker.color.g = 0.0
    marker.color.b = 1.0
    marker_pub.publish(marker)


def del_object_marker(marker_pub):
    marker = Marker()
    marker.header.frame_id = "map"
    marker.header.stamp = rospy.Time.now()
    marker.ns = objLabel
    marker.id = objID
    marker.action = Marker.DELETE
    marker_pub.publish(marker)


def pub_numerical_answer(numerical_pub):
    number = random.randint(1, 10)
    rospy.loginfo("Answer: %d", number)
    numerical_msg = Int32(data=number)
    numerical_pub.publish(numerical_msg)


def main():
    rospy.init_node("dummyVLM", anonymous=False)
    rospy.loginfo(">>> dummyVLM node started")

    global waypoint_file_dir, object_list_file_dir, waypointReachDis

    waypoint_file_dir = rospy.get_param("~waypoint_file_dir")
    object_list_file_dir = rospy.get_param("~object_list_file_dir")
    waypointReachDis = rospy.get_param("~waypointReachDis", 1.0)

    rospy.Subscriber("/state_estimation", Odometry, pose_handler)
    rospy.Subscriber("/challenge_question", String, question_handler)

    waypoint_pub = rospy.Publisher("/way_point_with_heading", Pose2D, queue_size=5)
    marker_pub = rospy.Publisher("selected_object_marker", Marker, queue_size=5)
    numerical_pub = rospy.Publisher("/numerical_response", Int32, queue_size=5)

    read_waypoint_file()
    read_object_list_file()

    rospy.loginfo("Awaiting question...")
    rate = rospy.Rate(10)

    while not rospy.is_shutdown():
        rospy.spin_once()
        if not question:
            rate.sleep()
            continue

        if question.lower().startswith("find"):
            rospy.loginfo("Navigating to object...")
            pub_object_marker(marker_pub)
            pub_object_waypoint(waypoint_pub)
        elif question.lower().startswith("how many"):
            del_object_marker(marker_pub)
            pub_numerical_answer(numerical_pub)
        else:
            del_object_marker(marker_pub)
            rospy.loginfo("Following path...")
            pub_path_waypoints(waypoint_pub)
            rospy.loginfo("Navigation ends.")

        question = ""
        rospy.loginfo("Awaiting question...")


if __name__ == "__main__":
    main()
