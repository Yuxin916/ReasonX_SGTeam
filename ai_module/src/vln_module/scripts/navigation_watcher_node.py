#!/usr/bin/env python

# navigation_watcher_node.py
import rospy
import math
from std_msgs.msg import Bool
from geometry_msgs.msg import Pose2D
from nav_msgs.msg import Odometry

class NavigationWatcherNode:
    def __init__(self):
        rospy.loginfo("Initializing Robust Navigation Watcher (v3)...")

        # --- Configuration Parameters ---
        self.goal_zone_distance = 0.5  # meters
        self.stationary_speed_threshold = 0.05  # meters per second
        
        # NEW: Threshold for rotational speed (yaw) in radians per second
        self.stationary_angular_threshold = 0.1  # radians per second (approx. 5.7 deg/s)
        
        self.stationary_time_threshold = rospy.Duration(3.0)  # 1 second

        # --- State Variables ---
        self.target_waypoint = None
        self.current_pose = None
        self.stationary_start_time = None

        # --- ROS Publishers and Subscribers ---
        self.waypoint_reached_pub = rospy.Publisher('/waypoint_reached', Bool, queue_size=10)
        rospy.Subscriber('/way_point_with_heading', Pose2D, self.waypoint_callback)
        rospy.Subscriber('/state_estimation', Odometry, self.odom_callback)
        
        rospy.loginfo("Navigation Watcher is running.")

    def waypoint_callback(self, msg):
        """Receives a new target waypoint and resets the state."""
        rospy.loginfo(f"Navigation Watcher: Received new target waypoint {msg.x:.2f}, {msg.y:.2f}")
        self.target_waypoint = msg
        self.stationary_start_time = None

    def odom_callback(self, msg):
        """The main logic loop, triggered by every odometry update."""
        if self.target_waypoint is None:
            return

        dist_to_target = "N/A"
        # current_position = msg.pose.pose.position
        
        # # Step 1: Check if we are inside the "goal zone"
        # dist_to_target = math.sqrt((self.target_waypoint.x - current_position.x)**2 +
        #                            (self.target_waypoint.y - current_position.y)**2)

        # if dist_to_target > self.goal_zone_distance:
        #     self.stationary_start_time = None
        #     return

        # Step 2: If we are near the goal, check if we are stationary (both linearly and angularly)
        linear_velocity = msg.twist.twist.linear
        angular_velocity = msg.twist.twist.angular # NEW: Get angular velocity

        linear_speed = math.sqrt(linear_velocity.x**2 + linear_velocity.y**2)
        angular_speed = abs(angular_velocity.z) # NEW: Get yaw speed

        # --- UPDATED CONDITION ---
        # The robot is considered stationary only if BOTH linear and angular speeds are below their thresholds.
        if linear_speed < self.stationary_speed_threshold and angular_speed < self.stationary_angular_threshold:
            # The robot is fully stopped. Let's check for how long.
            if self.stationary_start_time is None:
                self.stationary_start_time = rospy.Time.now()
            
            if rospy.Time.now() - self.stationary_start_time > self.stationary_time_threshold:
                # --- Success Condition Met! ---
                rospy.loginfo(f"Waypoint reached! (distance: {dist_to_target}m and stationary for >1s). Publishing completion.")
                self.waypoint_reached_pub.publish(Bool(data=True))
                self.target_waypoint = None
                self.stationary_start_time = None
        else:
            # The robot is close but still moving or rotating. Reset the timer.
            self.stationary_start_time = None

if __name__ == '__main__':
    rospy.init_node('navigation_watcher_node')
    watcher = NavigationWatcherNode()
    rospy.spin()