#!/usr/bin/env python

import rospy
import numpy as np
import math
import cv2  # NEW: Import OpenCV

# Import required ROS message types
from geometry_msgs.msg import Pose2D, Point
from sensor_msgs.msg import Image
from nav_msgs.msg import Odometry

# The 'tf' library is used to handle quaternion rotations
import tf.transformations as tft
# NEW: Import CvBridge for image conversion
from cv_bridge import CvBridge, CvBridgeError


class PixelToWaypointNode:
    """
    This node converts a 2D pixel coordinate from an image into a 3D waypoint,
    annotates the source image with the pixel, and publishes both the waypoint
    and the annotated image.
    """
    def __init__(self):
        rospy.loginfo("Initializing Pixel to Waypoint Node...")
        
        # --- State Variables ---
        self.latest_odom = None
        self.latest_image = None # NEW: We need to store the latest image
        self.bridge = CvBridge() # NEW: Create a CvBridge instance

        # --- ROS Publishers and Subscribers ---
        self.waypoint_pub = rospy.Publisher('/way_point_with_heading', Pose2D, queue_size=10)
        # self.vln_waypoint_pub = rospy.Publisher('/way_point_vln', Pose2D, queue_size=10) # Duplicate publisher, can be removed if not needed

        # NEW: A latched publisher for the annotated image.
        # queue_size=1 and latch=True ensures the last image is always available to new subscribers.
        self.annotated_image_pub = rospy.Publisher('/image_annotated', Image, queue_size=1, latch=True)

        # Subscriber to the robot's pose
        self.odom_sub = rospy.Subscriber('/state_estimation', Odometry, self.odom_callback)
        # NEW: We now actively use the image subscriber
        self.image_sub = rospy.Subscriber('/camera/image', Image, self.image_callback)
        
        # Subscriber for the incoming pixel coordinate from the VLM
        self.pixel_sub = rospy.Subscriber('/vlm_pixel_input', Point, self.pixel_callback)

        rospy.loginfo("Node ready. Waiting for pixel input on /vlm_pixel_input")

    def odom_callback(self, msg):
        """Stores the latest odometry message."""
        self.latest_odom = msg

    def image_callback(self, msg):
        """Stores the latest raw image message."""
        self.latest_image = msg

    def draw_and_publish_annotation(self, pixel_u, pixel_v):
        """Converts, annotates, and publishes the latest image."""
        if self.latest_image is None:
            rospy.logwarn("Cannot annotate image, no image data received yet.")
            return

        try:
            # Convert the ROS Image message to an OpenCV image (in BGR format)
            cv_image = self.bridge.imgmsg_to_cv2(self.latest_image, "bgr8")
            
            # --- Draw the marker on the image ---
            # A bright green circle with a black outline for visibility
            cv2.circle(cv_image, (int(pixel_u), int(pixel_v)), radius=16, color=(0, 0, 0), thickness=10)
            cv2.circle(cv_image, (int(pixel_u), int(pixel_v)), radius=16, color=(0, 255, 0), thickness=4)

            # Convert the annotated OpenCV image back to a ROS Image message
            annotated_image_msg = self.bridge.cv2_to_imgmsg(cv_image, "bgr8")
            
            # Publish the message
            self.annotated_image_pub.publish(annotated_image_msg)
            rospy.loginfo("Published annotated image to /image_annotated")

        except CvBridgeError as e:
            rospy.logerr(f"CvBridge Error during annotation: {e}")


    def pixel_callback(self, msg):
        """
        Main logic function. Triggered by a new pixel coordinate.
        """
        # MODIFIED: Added check for image data
        if self.latest_odom is None or self.latest_image is None:
            rospy.logwarn("Cannot process pixel, full sensor data (odom/image) not yet available.")
            return

        u = msg.x
        v = msg.y
        rospy.loginfo(f"Received pixel target: u={u}, v={v}")

        # --- NEW: Call the annotation function ---
        self.draw_and_publish_annotation(u, v)

        # --- The rest of the function (waypoint calculation) is unchanged ---
        HFOV_deg = 360.0
        VFOV_deg = 120.0
        width = 1920.0
        height = 640.0
        
        cx = width / 2.0
        cy = height / 2.0

        azimuth_rad = -((u - cx) / width) * math.radians(HFOV_deg)
        elevation_rad = -((v - cy) / height) * math.radians(VFOV_deg)
        
        ray_c = np.array([
            math.cos(elevation_rad) * math.cos(azimuth_rad),
            math.cos(elevation_rad) * math.sin(azimuth_rad),
            math.sin(elevation_rad)
        ])
        
        odom_pose = self.latest_odom.pose.pose
        q = [odom_pose.orientation.x, odom_pose.orientation.y, odom_pose.orientation.z, odom_pose.orientation.w]
        rotation_matrix = tft.quaternion_matrix(q)[:3, :3]
        ray_m = rotation_matrix.dot(ray_c)
        
        if ray_m[2] >= 0:
            rospy.logwarn("Cannot calculate waypoint. Ray is pointing up or horizontal in the map frame.")
            return

        robot_pos = np.array([odom_pose.position.x, odom_pose.position.y, odom_pose.position.z])
        t = -robot_pos[2] / ray_m[2]
        waypoint_3d = robot_pos + t * ray_m
        
        delta_x = waypoint_3d[0] - robot_pos[0]
        delta_y = waypoint_3d[1] - robot_pos[1]
        heading_theta = math.atan2(delta_y, delta_x)

        waypoint_msg = Pose2D()
        waypoint_msg.x = waypoint_3d[0]
        waypoint_msg.y = waypoint_3d[1]
        waypoint_msg.theta = heading_theta

        self.waypoint_pub.publish(waypoint_msg)
        rospy.loginfo(f"Published Pose2D waypoint: x={waypoint_msg.x:.2f}, y={waypoint_msg.y:.2f}, theta={math.degrees(waypoint_msg.theta):.2f} deg")


if __name__ == '__main__':
    try:
        rospy.init_node('pixel_to_waypoint_node')
        node = PixelToWaypointNode()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass