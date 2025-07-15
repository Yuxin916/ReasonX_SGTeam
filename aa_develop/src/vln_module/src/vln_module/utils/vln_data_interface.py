#!/usr/bin/env python

import rospy
from sensor_msgs.msg import Image, PointCloud2
from nav_msgs.msg import Odometry
from visualization_msgs.msg import MarkerArray

# NEW: Import libraries for image conversion
from PIL import Image as PILImage
from cv_bridge import CvBridge, CvBridgeError
import cv2 # OpenCV is used for color conversion

class VLNDataInterface:
    """
    A class that subscribes to all necessary topics for the CMU VLA Challenge.
    It automatically converts the ROS Image message into a PIL Image.
    """
    def __init__(self):
        # Initialize all state variables to None
        self.latest_image_360 = None # This will now store a PIL Image
        self.latest_registered_scan = None
        self.latest_sensor_scan = None
        self.latest_terrain_map_local = None
        self.latest_terrain_map_ext = None
        self.latest_sensor_pose = None
        self.latest_traversable_area = None
        self.latest_object_markers = None

        # NEW: Instantiate the CvBridge
        self.bridge = CvBridge()

        # --- ROS Subscribers ---
        rospy.Subscriber('/camera/image', Image, self._image_callback)
        rospy.Subscriber('/registered_scan', PointCloud2, self._registered_scan_callback)
        rospy.Subscriber('/sensor_scan', PointCloud2, self._sensor_scan_callback)
        rospy.Subscriber('/terrain_map', PointCloud2, self._terrain_map_local_callback)
        rospy.Subscriber('/terrain_map_ext', PointCloud2, self._terrain_map_ext_callback)
        rospy.Subscriber('/state_estimation', Odometry, self._sensor_pose_callback)
        rospy.Subscriber('/traversable_area', PointCloud2, self._traversable_area_callback)
        rospy.Subscriber('/object_markers', MarkerArray, self._object_markers_callback)

        rospy.loginfo("VLNDataInterface (Sensor Manager) initialized and collecting data.")

    def get_current_snapshot(self):
        """
        Returns a dictionary containing the most recent sensor data.
        The 'image' key will contain a PIL Image object.
        """
        return {
            'image': self.latest_image_360,
            'pose': self.latest_sensor_pose,
            'registered_scan': self.latest_registered_scan,
            'sensor_scan': self.latest_sensor_scan,
            'terrain_local': self.latest_terrain_map_local,
            'terrain_ext': self.latest_terrain_map_ext,
            'traversable': self.latest_traversable_area,
            'objects': self.latest_object_markers,
        }

    # --- MODIFIED Image Callback ---
    def _image_callback(self, msg):
        """
        Receives a ROS Image message, converts it to a PIL Image,
        and stores it.
        """
        rospy.loginfo_once("Receiving and converting camera image data...")
        try:
            # Step 1: Convert ROS Image message to OpenCV image (NumPy array)
            # "bgr8" is a standard encoding for color images in ROS
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            
            # Step 2: Convert from BGR color (used by OpenCV) to RGB color
            rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
            
            # Step 3: Convert the RGB NumPy array to a PIL Image
            pil_image = PILImage.fromarray(rgb_image)
            
            # Step 4: Store the final PIL Image
            self.latest_image_360 = pil_image

        except CvBridgeError as e:
            rospy.logerr(f"CvBridge Error: {e}")


    # --- Other Callbacks (Unchanged) ---
    def _registered_scan_callback(self, msg): self.latest_registered_scan = msg
    def _sensor_scan_callback(self, msg): self.latest_sensor_scan = msg
    def _terrain_map_local_callback(self, msg): self.latest_terrain_map_local = msg
    def _terrain_map_ext_callback(self, msg): self.latest_terrain_map_ext = msg
    def _sensor_pose_callback(self, msg): self.latest_sensor_pose = msg
    def _traversable_area_callback(self, msg): self.latest_traversable_area = msg
    def _object_markers_callback(self, msg): self.latest_object_markers = msg