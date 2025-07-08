import rospy
import random
import math
import tf
from std_msgs.msg import String, Int32
from geometry_msgs.msg import Pose2D
from visualization_msgs.msg import Marker

from utils.handler import get_pose

def pub_numerical_answer(numerical_pub, number):
    """
    Publishes a random numerical answer to the numerical answer topic.
    """
    rospy.loginfo("Answer: %d", number)
    numerical_msg = Int32(data=number)
    numerical_pub.publish(numerical_msg)


def pub_path_waypoints(waypoint_pub, waypointX, waypointY, waypointHeading, waypointReachDis):
    """
    Publishes a series of waypoints to the waypoint topic.
    logs the vehicle's position and the distance to the current waypoint.
    """
    if not waypointX:
        rospy.logerr("No waypoint available, exiting.")
        return

    waypoint_id = 0
    waypoint_msg = Pose2D(
        x=waypointX[waypoint_id],
        y=waypointY[waypoint_id],
        theta=waypointHeading[waypoint_id]
    )
    waypoint_pub.publish(waypoint_msg)
    rospy.loginfo(f"[NAV] Sent initial waypoint: ({waypoint_msg.x:.2f}, {waypoint_msg.y:.2f})")

    rate = rospy.Rate(10)
    while not rospy.is_shutdown():
        vehicleX, vehicleY = get_pose()
        dx = vehicleX - waypointX[waypoint_id]
        dy = vehicleY - waypointY[waypoint_id]
        dist = math.hypot(dx, dy)

        rospy.loginfo(f"[NAV] Vehicle: ({vehicleX:.2f}, {vehicleY:.2f}), "
                      f"Target: ({waypointX[waypoint_id]:.2f}, {waypointY[waypoint_id]:.2f}), "
                      f"Distance: {dist:.2f}")

        if dist < waypointReachDis:
            if waypoint_id == len(waypointX) - 1:
                rospy.loginfo(f"[NAV] Final waypoint reached at ({vehicleX:.2f}, {vehicleY:.2f})")
                break
            waypoint_id += 1
            waypoint_msg = Pose2D(
                x=waypointX[waypoint_id],
                y=waypointY[waypoint_id],
                theta=waypointHeading[waypoint_id]
            )
            waypoint_pub.publish(waypoint_msg)
            rospy.loginfo(f"[NAV] Advancing to waypoint {waypoint_id}: "
                          f"({waypoint_msg.x:.2f}, {waypoint_msg.y:.2f})")

        rate.sleep()


def pub_object_waypoint(waypoint_pub, obj_mid_x, obj_mid_y, waypointReachDis):
    """
    Publishes a single object waypoint (center of the object) and logs vehicle position
    until the robot gets within `waypointReachDis` to the object.
    """
    waypoint_msg = Pose2D(x=obj_mid_x, y=obj_mid_y, theta=0)
    waypoint_pub.publish(waypoint_msg)
    rospy.loginfo(f"[NAV] Sent object waypoint: ({obj_mid_x:.2f}, {obj_mid_y:.2f})")

    rate = rospy.Rate(10)
    while not rospy.is_shutdown():
        vehicleX, vehicleY = get_pose()
        dx = vehicleX - obj_mid_x
        dy = vehicleY - obj_mid_y
        dist = math.hypot(dx, dy)

        rospy.loginfo(f"[NAV] Vehicle: ({vehicleX:.2f}, {vehicleY:.2f}), "
                      f"Target: ({obj_mid_x:.2f}, {obj_mid_y:.2f}), "
                      f"Distance: {dist:.2f}")

        if dist < waypointReachDis:
            rospy.loginfo(f"[NAV] Reached object at ({vehicleX:.2f}, {vehicleY:.2f})")
            break

        rate.sleep()

def pub_object_marker(marker_pub, obj_info):
    """
    publishes a 3D marker (usually visualized in RViz) to highlight where the object is in the environment

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