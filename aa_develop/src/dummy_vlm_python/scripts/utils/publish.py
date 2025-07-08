import rospy
import random
import math
import tf
from std_msgs.msg import String, Int32
from geometry_msgs.msg import Pose2D
from visualization_msgs.msg import Marker


def pub_numerical_answer(numerical_pub, number):
    """
    Publishes a random numerical answer to the numerical answer topic.
    """
    number = random.randint(1, 10)
    rospy.loginfo("Answer: %d", number)
    numerical_msg = Int32(data=number)
    numerical_pub.publish(numerical_msg)


def pub_path_waypoints(waypoint_pub, waypointX, waypointY, waypointHeading):
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