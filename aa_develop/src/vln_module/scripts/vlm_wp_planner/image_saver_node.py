#!/usr/bin/env python

import rospy
import cv2
import os
import math

# Import the ROS message types we'll need
from sensor_msgs.msg import Image
from nav_msgs.msg import Odometry
# cv_bridge is the package that converts between ROS Image messages and OpenCV images
from cv_bridge import CvBridge, CvBridgeError

class ImageSaverNode:
    """
    A ROS node that saves images from a camera topic based on time and distance triggers.
    - It saves an image at most once per second.
    - It only saves an image if the robot has moved at least 0.3 meters since the
      last image was saved.
    """
    def __init__(self):
        """
        Initializes the node, subscribers, and state variables.
        """
        rospy.loginfo("Initializing Image Saver Node...")

        # --- Parameters and Configuration ---
        self.distance_threshold = 0.3  # meters
        self.time_interval = 1.0       # seconds
        self.output_directory = "saved_360_images"

        # --- State Variables ---
        self.bridge = CvBridge()
        self.last_saved_position = None
        self.latest_image_msg = None
        self.latest_odom_msg = None

        # --- Create Output Directory ---
        # Get the absolute path to ensure it's created in the correct location
        # relative to where the script is run.
        if not os.path.isabs(self.output_directory):
            # If using roslaunch, this will be relative to ~/.ros
            # It's often better to specify an absolute path.
            script_path = os.path.dirname(os.path.realpath(__file__))
            self.output_directory = os.path.join(script_path, self.output_directory)

        if not os.path.exists(self.output_directory):
            os.makedirs(self.output_directory)
            rospy.loginfo(f"Created output directory: {self.output_directory}")

        # --- ROS Subscribers ---
        # These callbacks just store the latest message. The main logic is in the timer.
        self.image_sub = rospy.Subscriber("/camera/image", Image, self.image_callback)
        self.odom_sub = rospy.Subscriber("/state_estimation", Odometry, self.odom_callback)

        # --- ROS Timer ---
        # This timer will call the 'save_image_if_needed' method every 'time_interval' seconds.
        # This is a cleaner approach than using rospy.Rate in a while loop.
        self.timer = rospy.Timer(rospy.Duration(self.time_interval), self.save_image_if_needed)

        rospy.loginfo("Image Saver Node is ready and listening.")

    def image_callback(self, msg):
        """Stores the most recent image message."""
        self.latest_image_msg = msg

    def odom_callback(self, msg):
        """Stores the most recent odometry message."""
        self.latest_odom_msg = msg

    def calculate_distance(self, pos1, pos2):
        """Calculates the Euclidean distance between two position points."""
        dx = pos1.x - pos2.x
        dy = pos1.y - pos2.y
        dz = pos1.z - pos2.z
        return math.sqrt(dx**2 + dy**2 + dz**2)

    def save_image_if_needed(self, event):
        """
        The core logic of the node, called by the rospy.Timer.
        Checks if conditions are met and saves an image if they are.
        """
        # Do nothing if we haven't received both an image and odom message yet
        if self.latest_image_msg is None or self.latest_odom_msg is None:
            rospy.loginfo_once("Waiting for initial image and odometry data...")
            return

        current_position = self.latest_odom_msg.pose.pose.position

        # Condition 1: Is this the very first image to be saved?
        if self.last_saved_position is None:
            rospy.loginfo("Saving the first image.")
            self.save_current_image(current_position)
            return

        # Condition 2: Has the robot moved enough since the last save?
        distance_moved = self.calculate_distance(current_position, self.last_saved_position)
        if distance_moved >= self.distance_threshold:
            rospy.loginfo(f"Moved {distance_moved:.2f}m. Saving new image.")
            self.save_current_image(current_position)
        else:
            rospy.loginfo_throttle(10, f"Skipping save. Moved only {distance_moved:.2f}m (threshold is {self.distance_threshold}m).")


    def save_current_image(self, current_position):
        """
        Converts the latest ROS Image message to an OpenCV image and saves it to a file.
        """
        try:
            # Convert the ROS Image message to an OpenCV image. "bgr8" is a standard encoding.
            cv_image = self.bridge.imgmsg_to_cv2(self.latest_image_msg, "bgr8")
        except CvBridgeError as e:
            rospy.logerr(f"CvBridge Error: {e}")
            return

        # Create a unique filename based on the current ROS time
        timestamp = rospy.Time.now().to_sec()
        filename = f"image_{timestamp:.2f}.png"
        filepath = os.path.join(self.output_directory, filename)

        # Save the OpenCV image to a file
        try:
            cv2.imwrite(filepath, cv_image)
            rospy.loginfo(f"Successfully saved image as {filepath}")
            # IMPORTANT: Update the last saved position to the current position
            self.last_saved_position = current_position
        except Exception as e:
            rospy.logerr(f"Failed to save image: {e}")


if __name__ == '__main__':
    try:
        # Initialize the ROS node
        rospy.init_node('image_saver_node', anonymous=True)
        # Create an instance of our class
        image_saver = ImageSaverNode()
        # rospy.spin() keeps the node from exiting until it's shut down
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
