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
    rospy.loginfo("Answer: %d", number)
    numerical_msg = Int32(data=number)
    numerical_pub.publish(numerical_msg)


def pub_path_waypoints(waypoint_pub, waypointX, waypointY, waypointHeading, vehicleX, vehicleY, waypointReachDis):
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


def pub_object_waypoint(waypoint_pub, obj_mid_x, obj_mid_y):
    waypoint_msg = Pose2D(x=obj_mid_x, y=obj_mid_y, theta=0)
    waypoint_pub.publish(waypoint_msg)


def pub_object_marker(marker_pub, obj_info):
    """
    obj_info should be a dict or namedtuple with:
        id, mid_x, mid_y, mid_z, l, w, h, heading, label
    """
    marker = Marker()
    marker.header.frame_id = "map"
    marker.header.stamp = rospy.Time.now()
    marker.ns = obj_info['label']
    marker.id = obj_info['id']
    marker.action = Marker.ADD
    marker.type = Marker.CUBE
    marker.pose.position.x = obj_info['mid_x']
    marker.pose.position.y = obj_info['mid_y']
    marker.pose.position.z = obj_info['mid_z']
    q = tf.transformations.quaternion_from_euler(0, 0, obj_info['heading'])
    marker.pose.orientation.x = q[0]
    marker.pose.orientation.y = q[1]
    marker.pose.orientation.z = q[2]
    marker.pose.orientation.w = q[3]
    marker.scale.x = obj_info['l']
    marker.scale.y = obj_info['w']
    marker.scale.z = obj_info['h']
    marker.color.a = 0.5
    marker.color.r = 0.0
    marker.color.g = 0.0
    marker.color.b = 1.0
    marker_pub.publish(marker)



def del_object_marker(marker_pub, obj_id, obj_label):
    marker = Marker()
    marker.header.frame_id = "map"
    marker.header.stamp = rospy.Time.now()
    marker.ns = obj_label
    marker.id = obj_id
    marker.action = Marker.DELETE
    marker_pub.publish(marker)