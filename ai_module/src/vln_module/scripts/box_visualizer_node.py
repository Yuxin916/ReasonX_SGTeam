#!/usr/bin/env python3

import rospy
import numpy as np
import cv2
from sensor_msgs.msg import Image
from visualization_msgs.msg import MarkerArray, Marker
from nav_msgs.msg import Odometry
from cv_bridge import CvBridge
# import tf2_ros
# import tf2_geometry_msgs
from geometry_msgs.msg import Point, Quaternion
from scipy.spatial.transform import Rotation as R

class PanoramicBoxVisualizer:
    def __init__(self):
        rospy.init_node('panoramic_box_visualizer', anonymous=True)
        
        # Camera parameters for panoramic camera
        self.image_width = 1920
        self.image_height = 640
        self.hfov = 360.0  # degrees
        self.vfov = 120.0  # degrees
        
        # Initialize variables
        self.current_image = None
        self.current_markers = []
        self.camera_pose = None
        
        # CV Bridge for image conversion
        self.bridge = CvBridge()
        
        # Publishers and Subscribers
        self.annotated_image_pub = rospy.Publisher('/image_with_3d_boxes', Image, queue_size=1, latch=True)
        rospy.Subscriber('/camera/image', Image, self.image_callback)
        rospy.Subscriber('/object_markers', MarkerArray, self.marker_callback)
        rospy.Subscriber('/state_estimation', Odometry, self.odom_callback)
        
        rospy.loginfo("Panoramic Box Visualizer Node initialized")
    
    def image_callback(self, msg):
        """Handle incoming panoramic images"""
        try:
            self.current_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            self.visualize_boxes()
        except Exception as e:
            rospy.logerr(f"Error processing image: {e}")
    
    def marker_callback(self, msg):
        """Handle incoming 3D bounding box markers"""
        self.current_markers = msg.markers
        if self.current_image is not None:
            self.visualize_boxes()
    
    def odom_callback(self, msg):
        """Handle camera pose updates from state estimation"""
        self.camera_pose = msg.pose.pose
    
    def world_to_camera_transform(self, world_points):
        """Transform world coordinates to camera coordinates"""
        if self.camera_pose is None:
            return None
            
        # Extract position and orientation from odometry
        pos = self.camera_pose.position
        ori = self.camera_pose.orientation
        
        # Convert quaternion to rotation matrix
        quat = [ori.x, ori.y, ori.z, ori.w]
        rotation = R.from_quat(quat)
        
        # Create transformation matrix (world to camera)
        # Note: We need the inverse transformation (camera pose in world -> world to camera)
        R_world_to_cam = rotation.inv().as_matrix()
        t_world_to_cam = -R_world_to_cam @ np.array([pos.x, pos.y, pos.z])
        
        # Transform points
        camera_points = []
        for point in world_points:
            world_point = np.array([point[0], point[1], point[2]])
            cam_point = R_world_to_cam @ world_point + t_world_to_cam
            camera_points.append(cam_point)
        
        return np.array(camera_points)
    
    def camera_to_panoramic_projection(self, camera_points):
        """Project 3D camera coordinates to panoramic image coordinates"""
        projected_points = []
        
        for point in camera_points:
            x, y, z = point
            
            # Skip points behind the camera
            if z <= 0:
                projected_points.append(None)
                continue
            
            # Convert to spherical coordinates
            # Azimuth angle (horizontal)
            azimuth = np.arctan2(x, z)  # atan2(x, z) for panoramic convention
            
            # Elevation angle (vertical) 
            elevation = np.arctan2(y, np.sqrt(x*x + z*z))
            
            # Convert to image coordinates
            # Horizontal: azimuth ranges from -π to π, map to 0 to image_width
            u = (azimuth + np.pi) / (2 * np.pi) * self.image_width
            
            # Vertical: elevation ranges from -vfov/2 to +vfov/2, map to image_height to 0
            v_range = np.radians(self.vfov)
            v = (v_range/2 - elevation) / v_range * self.image_height
            
            # Clamp to image bounds
            u = np.clip(u, 0, self.image_width - 1)
            v = np.clip(v, 0, self.image_height - 1)
            
            projected_points.append((int(u), int(v)))
        
        return projected_points
    
    def get_box_corners(self, marker):
        """Extract 8 corners of a 3D bounding box from marker"""
        if marker.type != Marker.CUBE:
            return None
        
        # Get box center, size, and orientation
        center = np.array([marker.pose.position.x, marker.pose.position.y, marker.pose.position.z])
        size = np.array([marker.scale.x, marker.scale.y, marker.scale.z])
        
        # Convert quaternion to rotation matrix
        quat = [marker.pose.orientation.x, marker.pose.orientation.y, 
                marker.pose.orientation.z, marker.pose.orientation.w]
        rotation = R.from_quat(quat).as_matrix()
        
        # Define 8 corners of unit cube
        corners = np.array([
            [-0.5, -0.5, -0.5],  # 0: bottom-back-left
            [ 0.5, -0.5, -0.5],  # 1: bottom-back-right
            [ 0.5,  0.5, -0.5],  # 2: bottom-front-right
            [-0.5,  0.5, -0.5],  # 3: bottom-front-left
            [-0.5, -0.5,  0.5],  # 4: top-back-left
            [ 0.5, -0.5,  0.5],  # 5: top-back-right
            [ 0.5,  0.5,  0.5],  # 6: top-front-right
            [-0.5,  0.5,  0.5]   # 7: top-front-left
        ])
        
        # Scale and rotate corners
        corners = corners * size
        corners = corners @ rotation.T
        
        # Translate to world position
        world_corners = corners + center
        
        return world_corners
    
    def draw_3d_box(self, image, projected_corners, color):
        """Draw 3D bounding box on image"""
        if any(corner is None for corner in projected_corners):
            return  # Skip if any corner is not visible
        
        corners = np.array(projected_corners)
        
        # Define the 12 edges of a cube
        edges = [
            # Bottom face
            (0, 1), (1, 2), (2, 3), (3, 0),
            # Top face  
            (4, 5), (5, 6), (6, 7), (7, 4),
            # Vertical edges
            (0, 4), (1, 5), (2, 6), (3, 7)
        ]
        
        # Draw edges
        thickness = 2
        for start_idx, end_idx in edges:
            start_point = tuple(corners[start_idx])
            end_point = tuple(corners[end_idx])
            cv2.line(image, start_point, end_point, color, thickness)
        
        # Draw corner points
        for corner in corners:
            cv2.circle(image, tuple(corner), 3, color, -1)
    
    def visualize_boxes(self):
        """Main visualization function"""
        if self.current_image is None or len(self.current_markers) == 0 or self.camera_pose is None:
            return
        
        # Create a copy of the image for annotation
        annotated_image = self.current_image.copy()
        
        # Process each marker
        for marker in self.current_markers:
            if marker.type != Marker.CUBE:
                continue
            
            # Get 3D corners of the bounding box
            world_corners = self.get_box_corners(marker)
            if world_corners is None:
                continue
            
            # Transform to camera coordinates
            camera_corners = self.world_to_camera_transform(world_corners)
            if camera_corners is None:
                continue
            
            # Project to panoramic image
            projected_corners = self.camera_to_panoramic_projection(camera_corners)
            
            # Get color from marker (convert from RGBA to BGR)
            color = (
                int(marker.color.b * 255),
                int(marker.color.g * 255), 
                int(marker.color.r * 255)
            )
            
            # Draw the 3D box
            self.draw_3d_box(annotated_image, projected_corners, color)
            
            # Add label if available
            if marker.text:
                # Find the center of visible corners for label placement
                visible_corners = [c for c in projected_corners if c is not None]
                if visible_corners:
                    center_u = int(np.mean([c[0] for c in visible_corners]))
                    center_v = int(np.mean([c[1] for c in visible_corners]))
                    
                    # Draw text background
                    text_size = cv2.getTextSize(marker.text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                    cv2.rectangle(annotated_image, 
                                (center_u - text_size[0]//2 - 5, center_v - text_size[1] - 5),
                                (center_u + text_size[0]//2 + 5, center_v + 5),
                                (0, 0, 0), -1)
                    
                    # Draw text
                    cv2.putText(annotated_image, marker.text,
                              (center_u - text_size[0]//2, center_v),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Add info overlay
        info_text = f"Boxes: {len(self.current_markers)} | Resolution: {self.image_width}x{self.image_height}"
        cv2.putText(annotated_image, info_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Publish annotated image
        try:
            annotated_msg = self.bridge.cv2_to_imgmsg(annotated_image, "bgr8")
            annotated_msg.header.stamp = rospy.Time.now()
            self.annotated_image_pub.publish(annotated_msg)
        except Exception as e:
            rospy.logerr(f"Error publishing annotated image: {e}")

def main():
    try:
        visualizer = PanoramicBoxVisualizer()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
    except Exception as e:
        rospy.logerr(f"Error in main: {e}")

if __name__ == '__main__':
    main()