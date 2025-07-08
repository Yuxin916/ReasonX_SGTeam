# utils/handler.py

import rospy
from cv_bridge import CvBridge
import cv2

# Shared global state (optional: better to encapsulate in a class later)
vehicleX, vehicleY = 0.0, 0.0
question = ""

bridge = CvBridge()

def camera_handler(msg):
    try:
        cv_image = bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        rospy.loginfo(f"Received image with shape: {cv_image.shape}")
        # Optional visualization
        # cv2.imshow("Camera", cv_image)
        # cv2.waitKey(1)
    except Exception as e:
        rospy.logerr(f"Failed to convert image: {e}")


def pose_handler(msg):
    global vehicleX, vehicleY
    vehicleX = msg.pose.pose.position.x
    vehicleY = msg.pose.pose.position.y
    rospy.loginfo(f"Received pose: x={vehicleX:.2f}, y={vehicleY:.2f}")

def question_handler(msg):
    global question
    question = msg.data
    rospy.loginfo(f"Received question: {question}")

def get_pose():
    return vehicleX, vehicleY

def get_question():
    return question

def reset_question():
    global question
    question = ""
