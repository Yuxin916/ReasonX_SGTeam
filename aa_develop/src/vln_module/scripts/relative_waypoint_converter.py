#!/usr/bin/env python

import rospy
import math
from geometry_msgs.msg import Pose2D
from nav_msgs.msg import Odometry
from tf.transformations import euler_from_quaternion

class RelativeWaypointConverter:
    def __init__(self):
        """
        Initializes the ROS node, subscribers, and publishers.
        """
        # Initialize the ROS node
        rospy.init_node('relative_waypoint_converter', anonymous=True)
        
        # --- Parameters ---
        # The topic to listen to for the robot's current pose
        self.state_topic = "/state_estimation"
        # The new topic to listen to for your relative commands
        self.relative_waypoint_topic = "/relative_waypoint"
        # The existing topic to publish the absolute waypoint to
        self.absolute_waypoint_topic = "/way_point_with_heading"
        
        # --- State Variables ---
        self.current_pose = None
        self.current_yaw = 0.0

        # --- Subscribers and Publishers ---
        # Create a publisher for the absolute waypoint
        self.absolute_waypoint_pub = rospy.Publisher(self.absolute_waypoint_topic, Pose2D, queue_size=10)
        
        # Subscribe to the robot's state to get its current position
        rospy.Subscriber(self.state_topic, Odometry, self._state_callback)
        
        # Subscribe to the new relative waypoint topic
        rospy.Subscriber(self.relative_waypoint_topic, Pose2D, self._relative_waypoint_callback)
        
        rospy.loginfo("Relative Waypoint Converter node started.")
        rospy.loginfo(f"Listening for robot pose on: {self.state_topic}")
        rospy.loginfo(f"Listening for relative waypoints on: {self.relative_waypoint_topic}")
        rospy.loginfo(f"Publishing absolute waypoints to: {self.absolute_waypoint_topic}")

    def _state_callback(self, msg):
        """
        Callback function to store the robot's current pose from the /state_estimation topic.
        """
        self.current_pose = msg.pose.pose
        
        # Extract the yaw angle from the quaternion
        orientation_q = self.current_pose.orientation
        orientation_list = [orientation_q.x, orientation_q.y, orientation_q.z, orientation_q.w]
        (_, _, yaw) = euler_from_quaternion(orientation_list)
        self.current_yaw = yaw

    def _relative_waypoint_callback(self, msg):
        """
        Callback function to convert a relative waypoint to an absolute one and publish it.
        """
        if self.current_pose is None:
            rospy.logwarn("Waiting for the first robot pose message from /state_estimation...")
            return
            
        rospy.loginfo("Received relative waypoint: x=%.2f, y=%.2f, theta=%.2f", msg.x, msg.y, msg.theta)

        # Current robot pose
        robot_x = self.current_pose.position.x
        robot_y = self.current_pose.position.y
        robot_theta = self.current_yaw

        # Relative waypoint to be transformed
        relative_x = msg.x
        relative_y = msg.y
        relative_theta = msg.theta

        # --- Transformation Math ---
        # Rotate the relative coordinates by the robot's current orientation
        abs_x_rotated = relative_x * math.cos(robot_theta) - relative_y * math.sin(robot_theta)
        abs_y_rotated = relative_x * math.sin(robot_theta) + relative_y * math.cos(robot_theta)
        
        # Translate the rotated coordinates by the robot's current position
        absolute_x = robot_x + abs_x_rotated
        absolute_y = robot_y + abs_y_rotated
        
        # Calculate the final absolute orientation
        absolute_theta = robot_theta + relative_theta
        # Normalize the angle to be within [-pi, pi]
        absolute_theta = math.atan2(math.sin(absolute_theta), math.cos(absolute_theta))

        # --- Create and Publish the Absolute Waypoint ---
        absolute_waypoint = Pose2D()
        absolute_waypoint.x = absolute_x
        absolute_waypoint.y = absolute_y
        absolute_waypoint.theta = absolute_theta
        
        self.absolute_waypoint_pub.publish(absolute_waypoint)
        rospy.loginfo("Published absolute waypoint: x=%.2f, y=%.2f, theta=%.2f", absolute_x, absolute_y, absolute_theta)


if __name__ == '__main__':
    try:
        RelativeWaypointConverter()
        # Keep the node running until it's shut down
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
