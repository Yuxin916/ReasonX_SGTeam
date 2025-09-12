# vln_module/scripts/challenge_agent_node.py

import rospy
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker, MarkerArray
from vln_module.utils.vln_data_interface import VLNDataInterface
from vln_module.utils.vlm_client import VLMClient

import requests
import tempfile
import os
import ast
from PIL import Image
import re
from typing import Dict, List
import rospy
from geometry_msgs.msg import Point
from PIL import Image

import io
import base64
import math

class RoboReferClient:
    """A client to interact with the roborefer grounding server."""
    def __init__(self, server_url="http://127.0.0.1:25547/query"):
        self.server_url = server_url
        # The prompt suffix required by the roborefer API
        self.suffix = " Your answer should be formatted as a list of tuples, i.e. [(x1, y1)], where each tuple contains the x and y coordinates of a point satisfying the conditions above. The coordinates should be between 0 and 1, indicating the normalized pixel locations of the points in the image."

    def get_pixel_from_description(self, image: Image.Image, description: str):
        """
        Takes a PIL image and a text description, encodes the image to base64,
        sends a JSON request to the server, and returns the denormalized pixel coordinate.
        """
        rospy.loginfo(f"RoboRefer: Grounding description: '{description}'")

        try:
            # 1. Convert the PIL Image to a base64 string without saving to a file
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            image_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            # 2. Construct the JSON payload the server expects
            full_prompt = description + self.suffix
            payload = {
                "image_url": [image_b64],
                "depth_url": [],
                "enable_depth": 0,
                "text": full_prompt
            }

            rospy.loginfo(
                f"RoboRefer: Calling server at {self.server_url} with a {image.size[0]}x{image.size[1]} image.")

            # 3. Send the request using the `json` parameter
            # This automatically sets the Content-Type header to "application/json"
            response = requests.post(self.server_url, json=payload, timeout=20)
            response.raise_for_status()  # This will check for any HTTP errors like 415

            # 4. Parse the JSON response from the server
            # Note: The server sends back JSON, not a plain text string
            response_data = response.json()
            answer_str = response_data.get('answer', '[]')

            normalized_points = ast.literal_eval(answer_str.strip())
            if not normalized_points or not isinstance(normalized_points, list):
                rospy.logerr("RoboRefer: Did not return a valid list of points.")
                return None

            nx, ny = normalized_points[0]
            width, height = image.size
            pixel_x = int(nx * width)
            pixel_y = int(ny * height)

            rospy.loginfo(f"RoboRefer: Grounded to relative pixel ({pixel_x}, {pixel_y})")
            return Point(x=pixel_x, y=pixel_y, z=0)

        except Exception as e:
            rospy.logerr(f"RoboRefer call or parsing failed: {e}")
            return None


class ChallengeAgentNode:
    def __init__(self):
        rospy.loginfo("Initializing Challenge Agent Node...")
        self.vln_data_interface = VLNDataInterface()
        self.vlm_client = VLMClient()
        self.roborefer_client = RoboReferClient()

        self.current_question = None
        self.is_answering = False
        self.question_type = None
        # Change to support multiple objects of same type: Dict[str, List[Marker]]
        self.nearby_objects_data: Dict[str, List[Marker]] = {}

        self.pixel_pub = rospy.Publisher('/vlm_pixel_input', Point, queue_size=10)
        self.answer_pub = rospy.Publisher('/selected_object_marker', Marker, queue_size=10)
        from std_msgs.msg import Int32
        self.numerical_pub = rospy.Publisher('/numerical_response', Int32, queue_size=10)

        rospy.Subscriber('/challenge_question', String, self.question_callback)
        rospy.Subscriber('/waypoint_reached', Bool, self.waypoint_reached_callback)
        rospy.Subscriber('/object_markers', MarkerArray, self.object_markers_callback)

        rospy.loginfo("Agent is ready and waiting for a question.")

    def classify_question(self, question: str) -> str:
        question_lower = question.lower()
        if re.search(r'^\s*(find|locate|point to|what is|which is|get|bring me)\b', question_lower):
            rospy.loginfo("Question classified as: Object Reference")
            return 'object_reference'
        if 'how many' in question_lower:
            rospy.loginfo("Question classified as: Numerical")
            return 'numerical'
        rospy.loginfo("Question classified as: Instruction Following")
        return 'instruction_following'

    def question_callback(self, msg):
        if self.is_answering:
            rospy.logwarn("Received a new question while still processing the previous one. Ignoring.")
            return
        rospy.loginfo(f"New challenge started! Question: '{msg.data}'")
        self.current_question = msg.data
        self.question_type = self.classify_question(self.current_question)
        self.nearby_objects_data.clear()

        if self.vlm_client.start_new_mission(self.current_question):
            self.is_answering = True
            self.execute_reason_act_step()
        else:
            rospy.logerr("Could not start mission on VLM server. Aborting.")

    def execute_reason_act_step(self):
        rospy.loginfo("--- New Reason-Act Step ---")
        sensor_snapshot = self.vln_data_interface.get_current_snapshot()
        panoramic_image = sensor_snapshot.get('image')
        if panoramic_image is None:
            rospy.logwarn("Cannot execute step, image data is not yet available.")
            return

        action = self.vlm_client.get_vlm_response(panoramic_image, self.current_question)
        if not action:
            rospy.logerr("Failed to get a valid action from VLM. Stopping mission.")
            self.is_answering = False
            return

        action_type = action.get('type')
        reasoning = action.get('reasoning')
        rospy.loginfo(f"Reasoning: {reasoning}")
        if action_type == 'end':
            self.handle_end_action(action)
        elif action_type == 'navigation':
            self.handle_navigation_action(action, panoramic_image)
        else:
            rospy.logerr(f"VLM returned an unknown or error action type: '{action_type}'. Stopping.")
            self.is_answering = False

    def handle_end_action(self, action):
        if self.question_type == 'object_reference':
            rospy.loginfo("VLM chose to end. Verifying object presence for reference question.")
            self.handle_object_reference_end()
        elif self.question_type == 'numerical':
            rospy.loginfo("VLM chose to end. Publishing numerical answer.")
            self.handle_numerical_end(action)
        else:
            rospy.loginfo(f"VLM chose to stop: {action.get('reasoning')}. Challenge complete!")
            self.is_answering = False

    def handle_numerical_end(self, action):
        number = action.get('number')
        if number is not None:
            from std_msgs.msg import Int32
            rospy.loginfo(f"Publishing numerical answer: {number}")
            self.numerical_pub.publish(Int32(data=int(number)))
        else:
            rospy.logwarn("VLM ended mission but did not provide a numerical answer. Stopping.")
        self.is_answering = False

    def handle_navigation_action(self, action, panoramic_image):
        division = action.get('image_division')
        description = action.get('subgoal_description')
        if division and description:
            rospy.loginfo(f"VLM chose division '{division}' with description: '{description}'")
            crop_width = 640
            if division == 'left':
                offset_x = 0
                selected_crop = panoramic_image.crop((0, 0, crop_width, 640))
            elif division == 'center':
                offset_x = crop_width
                selected_crop = panoramic_image.crop((offset_x, 0, offset_x + crop_width, 640))
            elif division == 'right':
                offset_x = 2 * crop_width
                selected_crop = panoramic_image.crop((offset_x, 0, offset_x + crop_width, 640))
            else:
                rospy.logerr(f"VLM returned an invalid division: '{division}'. Stopping.")
                self.is_answering = False
                return
            relative_pixel = self.roborefer_client.get_pixel_from_description(selected_crop, description)
            if relative_pixel:
                final_x = relative_pixel.x + offset_x
                final_y = relative_pixel.y
                rospy.loginfo(f"Publishing final waypoint at panoramic coordinate ({int(final_x)}, {int(final_y)})")
                pixel_msg = Point(x=final_x, y=final_y, z=0)
                self.pixel_pub.publish(pixel_msg)
            else:
                rospy.logerr("Failed to get a valid pixel from RoboRefer. Stopping mission.")
                self.is_answering = False
        else:
            rospy.logerr(f"VLM chose to navigate but was missing division ('{division}') or description ('{description}').")
            self.is_answering = False

    def handle_object_reference_end(self):
        object_names = list(self.nearby_objects_data.keys())
        if not object_names:
            rospy.logwarn("VLM ended mission but no objects are detected nearby. Re-prompting to navigate.")
            self.reprompt_and_continue()
            return
        find_result = self.vlm_client.find_target_in_list(self.current_question, object_names)
        if find_result and find_result.get('is_present') and find_result.get('target_name') in self.nearby_objects_data:
            target_name = find_result['target_name']
            target_marker = self.nearby_objects_data[target_name]
            rospy.loginfo(f"SUCCESS: Identified target '{target_name}'. Publishing its bounding box. Reason: {find_result.get('reasoning')}")
            self.answer_pub.publish(target_marker)
            self.is_answering = False
        else:
            reason = find_result.get('reasoning') if find_result else "No valid response from VLM."
            rospy.loginfo(f"Target not found in current vicinity. Re-prompting VLM to continue navigation. Reason: {reason}")
            self.reprompt_and_continue()

    def reprompt_and_continue(self):
        sensor_snapshot = self.vln_data_interface.get_current_snapshot()
        panoramic_image = sensor_snapshot.get('image')
        if panoramic_image is None:
            rospy.logwarn("Cannot re-prompt, image data is not available.")
            return
        reprompt_msg = "You are not yet close enough to the target object. Please provide a new navigation action to get closer to the object described in the mission."
        action = self.vlm_client.get_vlm_response(panoramic_image, self.current_question, reprompt=reprompt_msg)
        if action and action.get('type') == 'navigation':
            self.handle_navigation_action(action, panoramic_image)
        else:
            rospy.logerr("VLM failed to provide a new navigation goal after re-prompting. Stopping mission.")
            self.is_answering = False

    def waypoint_reached_callback(self, msg):
        if not self.is_answering or not msg.data:
            return
        rospy.loginfo("Waypoint reached. Executing next Reason-Act step.")
        self.execute_reason_act_step()

    def classify_question(self, question: str) -> str:
        question_lower = question.lower()
        if re.search(r'^\s*(find|locate|point to|what is|which is|get|bring me)\b', question_lower):
            rospy.loginfo("Question classified as: Object Reference")
            return 'object_reference'
        if 'how many' in question_lower:
            rospy.loginfo("Question classified as: Numerical")
            return 'numerical'
        rospy.loginfo("Question classified as: Instruction Following")
        return 'instruction_following'

    def object_markers_callback(self, msg: MarkerArray):
        current_objects: Dict[str, List[Marker]] = {}
        for marker in msg.markers:
            if marker.ns:
                if marker.ns not in current_objects:
                    current_objects[marker.ns] = []
                current_objects[marker.ns].append(marker)
        self.nearby_objects_data = current_objects

    def question_callback(self, msg):
        if self.is_answering:
            rospy.logwarn("Received a new question while still processing the previous one. Ignoring.")
            return
            
        rospy.loginfo(f"New challenge started! Question: '{msg.data}'")
        self.current_question = msg.data
        self.question_type = self.classify_question(self.current_question)
        self.nearby_objects_data.clear()

        if self.vlm_client.start_new_mission(self.current_question):
            self.is_answering = True
            self.execute_reason_act_step()
        else:
            rospy.logerr("Could not start mission on VLM server. Aborting.")

    def execute_reason_act_step(self):
        rospy.loginfo("--- New Reason-Act Step ---")
        sensor_snapshot = self.vln_data_interface.get_current_snapshot()
        panoramic_image = sensor_snapshot.get('image')
        if panoramic_image is None:
            rospy.logwarn("Cannot execute step, image data is not yet available.")
            return

        action = self.vlm_client.get_vlm_response(panoramic_image, self.current_question)
        if not action:
            rospy.logerr("Failed to get a valid action from VLM. Stopping mission.")
            self.is_answering = False
            return

        action_type = action.get('type')
        rospy.loginfo(f"VLM Reasoning: {action.get('reasoning')}")
        if action_type == 'end':
            if self.question_type == 'object_reference':
                rospy.loginfo("VLM chose to end. Verifying object presence for reference question.")
                self.handle_object_reference_end()
            elif self.question_type == 'numerical':
                rospy.loginfo("VLM chose to end. Publishing numerical answer.")
                self.handle_numerical_end(action)
            else:
                rospy.loginfo(f"VLM chose to stop: {action.get('reasoning')}. Challenge complete!")
                self.is_answering = False

        elif action_type == 'navigation':
            self.handle_navigation_action(action, panoramic_image)
        else:
            rospy.logerr(f"VLM returned an unknown or error action type: '{action_type}'. Stopping.")
            self.is_answering = False

    def handle_numerical_end(self, action):
        # Expecting the VLM to return a number in the action dict, e.g. {'type': 'end', 'number': 3, ...}
        number = action.get('number')
        if number is not None:
            from std_msgs.msg import Int32
            rospy.loginfo(f"Publishing numerical answer: {number}")
            self.numerical_pub.publish(Int32(data=int(number)))
        else:
            rospy.logwarn("VLM ended mission but did not provide a numerical answer. Stopping.")
        self.is_answering = False

    def handle_navigation_action(self, action, panoramic_image):
        division = action.get('image_division')
        description = action.get('subgoal_description')
        
        if division and description:
            rospy.loginfo(f"VLM chose division '{division}' with description: '{description}'")
            
            crop_width = 640
            if division == 'left':
                offset_x = 0
                selected_crop = panoramic_image.crop((0, 0, crop_width, 640))
            elif division == 'center':
                offset_x = crop_width
                selected_crop = panoramic_image.crop((offset_x, 0, offset_x + crop_width, 640))
            elif division == 'right':
                offset_x = 2 * crop_width
                selected_crop = panoramic_image.crop((offset_x, 0, offset_x + crop_width, 640))
            else:
                rospy.logerr(f"VLM returned an invalid division: '{division}'. Stopping.")
                self.is_answering = False
                return

            relative_pixel = self.roborefer_client.get_pixel_from_description(selected_crop, description)
            
            if relative_pixel:
                final_x = relative_pixel.x + offset_x
                final_y = relative_pixel.y
                rospy.loginfo(f"Publishing final waypoint at panoramic coordinate ({int(final_x)}, {int(final_y)})")
                pixel_msg = Point(x=final_x, y=final_y, z=0)
                self.pixel_pub.publish(pixel_msg)
            else:
                rospy.logerr("Failed to get a valid pixel from RoboRefer. Stopping mission.")
                self.is_answering = False
        else:
            rospy.logerr(f"VLM chose to navigate but was missing division ('{division}') or description ('{description}').")
            self.is_answering = False

    def handle_object_reference_end(self):
        object_names = list(self.nearby_objects_data.keys())
        if not object_names:
            rospy.logwarn("VLM ended mission but no objects are detected nearby. Re-prompting to navigate.")
            self.reprompt_and_continue()
            return

        # 1. Ask VLM to find the target in the list of nearby objects
        find_result = self.vlm_client.find_target_in_list(self.current_question, object_names)
        
        # 2. Check the result dictionary
        # Use .get() for safer dictionary access
        if find_result and find_result.get('is_present') and find_result.get('target_name') in self.nearby_objects_data:
            # SUCCESS: The target was found and identified
            target_name = find_result['target_name']
            target_markers = self.nearby_objects_data[target_name]
            
            # Check if multiple objects of the same type exist
            if len(target_markers) == 1:
                # Only one object of this type, use it directly
                target_marker = target_markers[0]
                rospy.loginfo(f"SUCCESS: Identified single target '{target_name}'. Publishing its bounding box. Reason: {find_result.get('reasoning')}")
                self.answer_pub.publish(target_marker)
                self.is_answering = False
            else:
                # Multiple objects of the same type, use RoboRefer to determine which one
                rospy.loginfo(f"Multiple '{target_name}' objects found ({len(target_markers)}). Using RoboRefer to identify the specific target.")
                self.resolve_multiple_objects(target_name, target_markers, find_result.get('reasoning', ''))
        else:
            # FAILURE: The target was not found, or an error occurred.
            reason = find_result.get('reasoning') if find_result else "No valid response from VLM."
            rospy.loginfo(f"Target not found in current vicinity. Re-prompting VLM to continue navigation. Reason: {reason}")
            self.reprompt_and_continue()

    def reprompt_and_continue(self):
        sensor_snapshot = self.vln_data_interface.get_current_snapshot()
        panoramic_image = sensor_snapshot.get('image')
        if panoramic_image is None:
            rospy.logwarn("Cannot re-prompt, image data is not available.")
            return

        reprompt_msg = "You are not yet close enough to the target object. Please provide a new navigation action to get closer to the object described in the mission."
        action = self.vlm_client.get_vlm_response(panoramic_image, self.current_question, reprompt=reprompt_msg)
        
        if action and action.get('type') == 'navigation':
            self.handle_navigation_action(action, panoramic_image)
        else:
            rospy.logerr("VLM failed to provide a new navigation goal after re-prompting. Stopping mission.")
            self.is_answering = False

    def waypoint_reached_callback(self, msg):
        if not self.is_answering or not msg.data:
            return
        rospy.loginfo("Waypoint reached. Executing next Reason-Act step.")
        self.execute_reason_act_step()

    def resolve_multiple_objects(self, target_name: str, target_markers: List[Marker], reasoning: str):
        """
        When multiple objects of the same type exist, use RoboRefer to determine 
        which specific object matches the description in the question.
        """
        # Get current panoramic image
        sensor_snapshot = self.vln_data_interface.get_current_snapshot()
        panoramic_image = sensor_snapshot.get('image')
        if panoramic_image is None:
            rospy.logwarn("Cannot resolve multiple objects, image data is not available.")
            self.reprompt_and_continue()
            return

        # Use RoboRefer to get the pixel coordinate of the target object
        # Extract the description from the original question for RoboRefer
        rospy.loginfo(f"Using RoboRefer to ground the description: '{self.current_question}'")
        target_pixel = self.roborefer_client.get_pixel_from_description(panoramic_image, self.current_question)
        
        if target_pixel is None:
            rospy.logwarn("RoboRefer failed to ground the target description. Re-prompting to navigate.")
            self.reprompt_and_continue()
            return

        # Convert target pixel to comparable format
        target_x = target_pixel.x
        target_y = target_pixel.y
        
        # Find the marker closest to the RoboRefer result
        closest_marker = None
        min_distance = float('inf')
        
        for marker in target_markers:
            # Get marker's projected pixel position
            # Note: We need to project the marker's 3D position to 2D pixel coordinates
            marker_pixel = self.project_marker_to_pixel(marker)
            if marker_pixel is None:
                continue
                
            # Calculate distance between RoboRefer result and marker position
            distance = ((marker_pixel.x - target_x) ** 2 + (marker_pixel.y - target_y) ** 2) ** 0.5
            rospy.loginfo(f"Marker {marker.id} at pixel ({marker_pixel.x}, {marker_pixel.y}), distance to target: {distance:.2f}")
            
            if distance < min_distance:
                min_distance = distance
                closest_marker = marker
        
        if closest_marker is not None:
            rospy.loginfo(f"SUCCESS: Selected closest marker (ID: {closest_marker.id}) at distance {min_distance:.2f} pixels. Reason: {reasoning}")
            self.answer_pub.publish(closest_marker)
            self.is_answering = False
        else:
            rospy.logwarn("Could not project any markers to pixel coordinates. Re-prompting to navigate.")
            self.reprompt_and_continue()

    def project_marker_to_pixel(self, marker: Marker):
        """
        Project a 3D marker position to 2D pixel coordinates in the panoramic image.
        This method should mirror the logic used in marker_annotater.py
        """
        try:
            # Transform marker position to sensor frame (similar to marker_annotater.py)
            # For now, we'll assume the marker is already in the correct frame
            # In a real implementation, you might need to use tf transforms
            
            x = marker.pose.position.x
            y = marker.pose.position.y
            z = marker.pose.position.z
            
            # Use the same projection logic as in marker_annotater.py
            # Re-map sensor frame to camera frame
            x_sens, y_sens, z_sens = x, y, z
            x_cam = -y_sens     # right
            y_cam = -z_sens     # down
            z_cam = x_sens      # forward

            if x_cam == 0 and y_cam == 0 and z_cam == 0:
                return None  # Invalid point

            # Compute angles
            yaw = math.atan2(x_cam, z_cam)        # horizontal angle
            pitch = math.atan2(y_cam, math.sqrt(x_cam**2 + z_cam**2))  # vertical angle

            # Convert FOVs to radians (matching marker_annotater.py parameters)
            hfov_deg = 360.0
            vfov_deg = 120.0
            hfov_rad = math.radians(hfov_deg)
            vfov_rad = math.radians(vfov_deg)

            # Normalize yaw and pitch to [0, 1]
            u = (yaw + hfov_rad / 2) / hfov_rad
            v = (vfov_rad / 2 + pitch) / vfov_rad

            # Convert to pixel coordinates (matching marker_annotater.py image dimensions)
            image_width = 1920
            image_height = 640
            u_pixel = int(u * image_width)
            v_pixel = int(v * image_height)

            # Check if within image boundaries
            if 0 <= u_pixel < image_width and 0 <= v_pixel < image_height:
                return Point(x=u_pixel, y=v_pixel, z=0)
            else:
                return None  # Out of bounds
                
        except Exception as e:
            rospy.logwarn(f"Failed to project marker to pixel: {e}")
            return None

if __name__ == '__main__':
    rospy.init_node('challenge_agent_node')
    agent = ChallengeAgentNode()
    rospy.spin()