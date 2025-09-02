#!/usr/bin/env python
import rospy
import tf
from geometry_msgs.msg import PoseStamped
from visualization_msgs.msg import Marker, MarkerArray
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image
import numpy as np
from cv_bridge import CvBridge
import cv2
import math

from tf.transformations import quaternion_matrix

def get_bbox_corners(scale):
    dx, dy, dz = scale.x / 2.0, scale.y / 2.0, scale.z / 2.0
    return [
        [ dx,  dy,  dz],
        [ dx,  dy, -dz],
        [ dx, -dy,  dz],
        [ dx, -dy, -dz],
        [-dx,  dy,  dz],
        [-dx,  dy, -dz],
        [-dx, -dy,  dz],
        [-dx, -dy, -dz]
    ]

def transform_corner(pose, local_pt):
    q = pose.orientation
    t = pose.position
    rot = quaternion_matrix([q.x, q.y, q.z, q.w])[:3, :3]
    pt_local = np.array(local_pt).reshape((3, 1))
    pt_world = np.dot(rot, pt_local).flatten() + np.array([t.x, t.y, t.z])
    return pt_world


def project_to_image(pt3d_sensor, image_width, image_height, hfov_deg, vfov_deg):
    # Re-map sensor frame to camera frame
    x_sens, y_sens, z_sens = pt3d_sensor
    x = -y_sens     # right
    y = -z_sens     # down
    z = x_sens      # forward

    if x == 0 and y == 0 and z == 0:
        return None  # Invalid point

    # Compute angles
    yaw = math.atan2(x, z)        # horizontal angle
    pitch = math.atan2(y, math.sqrt(x**2 + z**2))  # vertical angle

    # Convert FOVs to radians
    hfov_rad = math.radians(hfov_deg)
    vfov_rad = math.radians(vfov_deg)

    # Normalize yaw and pitch to [0, 1]
    u = (yaw + hfov_rad / 2) / hfov_rad
    v = (vfov_rad / 2 + pitch) / vfov_rad

    # Convert to pixel coordinates
    u_pixel = int(u * image_width)
    v_pixel = int(v * image_height)

    # Clamp to image boundaries
    if 0 <= u_pixel < image_width and 0 <= v_pixel < image_height:
        return (u_pixel, v_pixel)
    else:
        return None  # Out of bounds


class MarkerAnnotater:
    def __init__(self):
        rospy.init_node('marker_annotater', anonymous=True)

        self.marker_sub = rospy.Subscriber('/object_markers', MarkerArray, self.marker_callback)
        self.state_sub = rospy.Subscriber('/state_estimation', Odometry, self.state_callback)
        self.image_sub = rospy.Subscriber('/camera/image', Image, self.image_callback)
        self.marker_pub = rospy.Publisher('/projected_markers', MarkerArray, queue_size=10)
        self.image_pub = rospy.Publisher('/camera/projected_image', Image, queue_size=1)

        self.listener = tf.TransformListener()
        self.latest_state = None
        self.latest_image = None
        self.bridge = CvBridge()

        # Panoramic camera parameters
        self.image_width = 1920
        self.image_height = 640
        self.hfov = 360.0
        self.vfov = 120.0

    def image_callback(self, msg):
        self.latest_image = msg

    def state_callback(self, msg):
        self.latest_state = msg

    def marker_callback(self, marker_array_msg):
        if self.latest_state is None or self.latest_image is None:
            rospy.logwarn("Missing state or image.")
            return

        try:
            cv_image = self.bridge.imgmsg_to_cv2(self.latest_image, desired_encoding='bgr8')
        except Exception as e:
            rospy.logerr(f"Image conversion failed: {e}")
            return

        output_markers = MarkerArray()

        for i, marker_msg in enumerate(marker_array_msg.markers):
            marker_pose = PoseStamped()
            marker_pose.header = marker_msg.header
            marker_pose.pose = marker_msg.pose

            try:
                self.listener.waitForTransform("sensor", marker_msg.header.frame_id, rospy.Time(0), rospy.Duration(1.0))
                marker_pose_camera = self.listener.transformPose("sensor", marker_pose)

                x = marker_pose_camera.pose.position.x
                y = marker_pose_camera.pose.position.y
                z = marker_pose_camera.pose.position.z

                rospy.loginfo("Marker '%s' in sensor frame: (%.2f, %.2f, %.2f)", marker_msg.ns, x, y, z)

                # === Project center ===
                projected = project_to_image((x, y, z), self.image_width, self.image_height, self.hfov, self.vfov)
                if projected:
                    u, v = projected
                    cv2.circle(cv_image, (u, v), 8, (0, 0, 255), -1)

                # === Project bounding box ===
                # projected_corners = []
                # for corner_local in get_bbox_corners(marker_msg.scale):
                #     corner_world = transform_corner(marker_pose.pose, corner_local)

                #     corner_ps = PoseStamped()
                #     corner_ps.header = marker_msg.header
                #     corner_ps.pose.position.x = corner_world[0]
                #     corner_ps.pose.position.y = corner_world[1]
                #     corner_ps.pose.position.z = corner_world[2]
                #     corner_ps.pose.orientation.w = 1.0  # identity

                #     try:
                #         corner_sens = self.listener.transformPose("sensor", corner_ps)
                #         x_c = corner_sens.pose.position.x
                #         y_c = corner_sens.pose.position.y
                #         z_c = corner_sens.pose.position.z

                #         uv = project_to_image((x_c, y_c, z_c), self.image_width, self.image_height, self.hfov, self.vfov)
                #         if uv:
                #             projected_corners.append(uv)
                #     except Exception as e:
                #         rospy.logwarn("Corner transform failed: %s", e)

                # Draw bounding box if we have enough corners
                # if len(projected_corners) >= 4:
                #     us = [u for u, v in projected_corners]
                #     vs = [v for u, v in projected_corners]
                #     umin, umax = min(us), max(us)
                #     vmin, vmax = min(vs), max(vs)
                #     cv2.rectangle(cv_image, (umin, vmin), (umax, vmax), (0, 255, 0), 2)

                # === RViz Marker ===
                viz_marker = Marker()
                viz_marker.header.frame_id = "sensor"
                viz_marker.header.stamp = rospy.Time.now()
                viz_marker.id = i
                viz_marker.type = Marker.SPHERE
                viz_marker.action = Marker.ADD
                viz_marker.pose = marker_pose_camera.pose
                viz_marker.scale.x = viz_marker.scale.y = viz_marker.scale.z = 0.2
                viz_marker.color.r = 1.0
                viz_marker.color.g = 0.0
                viz_marker.color.b = 0.0
                viz_marker.color.a = 1.0
                viz_marker.ns = marker_msg.ns
                output_markers.markers.append(viz_marker)

            except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException) as e:
                rospy.logwarn("Transform to camera frame failed: %s", e)

        self.marker_pub.publish(output_markers)

        try:
            image_msg = self.bridge.cv2_to_imgmsg(cv_image, encoding='bgr8')
            self.image_pub.publish(image_msg)
        except Exception as e:
            rospy.logerr(f"Failed to publish image: {e}")


if __name__ == '__main__':
    try:
        annotater = MarkerAnnotater()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
