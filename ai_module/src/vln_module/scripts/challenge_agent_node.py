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
from PIL import Image as PILImage
import re
from typing import Dict, List
import rospy
from geometry_msgs.msg import Point

import io
import base64
import math
import cv2
import numpy as np
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image as ROSImage

class RoboReferClient:
    """A client to interact with the roborefer grounding server."""
    def __init__(self, server_url="http://127.0.0.1:25547/query"):
        self.server_url = server_url
        # The prompt suffix required by the roborefer API
        self.suffix = " Your answer should be formatted as a list of tuples, i.e. [(x1, y1)], where each tuple contains the x and y coordinates of a point satisfying the conditions above. The coordinates should be between 0 and 1, indicating the normalized pixel locations of the points in the image."

    def get_pixel_from_description(self, image: PILImage.Image, description: str):
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
        self.bridge = CvBridge()  # For image annotation

        self.current_question = None
        self.is_answering = False
        self.question_type = None
        # Change to support multiple objects of same type: Dict[str, List[Marker]]
        self.nearby_objects_data: Dict[str, List[Marker]] = {}
        self.reprompt_count = 0  # Track number of reprompts to prevent infinite loops
        self.max_reprompts = 100   # Maximum number of reprompts before giving up

        self.pixel_pub = rospy.Publisher('/vlm_pixel_input', Point, queue_size=10)
        self.answer_pub = rospy.Publisher('/selected_object_marker', Marker, queue_size=10)
        from std_msgs.msg import Int32
        self.numerical_pub = rospy.Publisher('/numerical_response', Int32, queue_size=10)
        # Publisher for annotated image showing RoboRefer results and candidate markers
        self.annotated_image_pub = rospy.Publisher('/roborefer_annotated_image', ROSImage, queue_size=1, latch=True)

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
            self.handle_object_reference_end(action)
        elif self.question_type == 'numerical':
            rospy.loginfo("VLM chose to end. Publishing numerical answer.")
            self.handle_numerical_end(action)
        else:
            rospy.loginfo(f"VLM chose to stop: {action.get('reasoning')}. Challenge complete!")
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
        self.reprompt_count = 0  # Reset reprompt counter for new mission

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
                self.handle_object_reference_end(action)
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
        # Debug: Print the entire action dictionary to see what VLM returned
        rospy.loginfo(f"DEBUG: VLM returned action for numerical end: {action}")
        
        # Expecting the VLM to return a number in the action dict, e.g. {'type': 'end', 'number': 3, ...}
        number = action.get('number')
        if number is not None:
            from std_msgs.msg import Int32
            rospy.loginfo(f"Publishing numerical answer: {number}")
            self.numerical_pub.publish(Int32(data=int(number)))
        else:
            # Reprompt VLM to provide the proper JSON format with the required 'number' field
            reasoning = action.get('reasoning', '')
            rospy.loginfo(f"No 'number' field found. Reprompting VLM to provide proper JSON format.")
            
            # Get current image for reprompting
            sensor_snapshot = self.vln_data_interface.get_current_snapshot()
            panoramic_image = sensor_snapshot.get('image')
            if panoramic_image is None:
                rospy.logwarn("Cannot reprompt VLM, image data is not available.")
                self.is_answering = False
                return
            
            # Create a specific reprompt message for numerical questions
            reprompt_msg = f"""You previously provided this reasoning: "{reasoning}"
            
            However, your response was missing the required 'number' field. You have two options:
            
            1. If you can count the objects from your current view, provide the final answer:
            {{
                "type": "end",
                "reasoning": "<your explanation>",
                "number": <integer_answer>
            }}
            
            2. If you need a better view to count accurately, continue navigating:
            {{
                "type": "navigation",
                "reasoning": "<explain why you need a better view>",
                "image_division": "<'left', 'center', or 'right'>",
                "subgoal_description": "<where to move for better counting view>"
            }}
            
            Please choose the appropriate response based on your confidence in the count."""
            
            # Reprompt the VLM
            reprompt_action = self.vlm_client.get_vlm_response(panoramic_image, self.current_question, reprompt=reprompt_msg)
            
            if reprompt_action:
                if reprompt_action.get('type') == 'end':
                    reprompt_number = reprompt_action.get('number')
                    if reprompt_number is not None:
                        from std_msgs.msg import Int32
                        rospy.loginfo(f"Reprompt successful! Publishing numerical answer: {reprompt_number}")
                        self.numerical_pub.publish(Int32(data=int(reprompt_number)))
                    else:
                        rospy.logwarn("VLM reprompt still did not provide a numerical answer. Trying text extraction as fallback.")
                        self._try_extract_number_from_text(reasoning)
                elif reprompt_action.get('type') == 'navigation':
                    rospy.loginfo("VLM decided to navigate further for better counting view. Continuing navigation.")
                    self.handle_navigation_action(reprompt_action, panoramic_image)
                    # Don't set is_answering = False here, let the navigation continue
                    return
                else:
                    rospy.logwarn(f"VLM reprompt returned unexpected action type: {reprompt_action.get('type')}. Trying text extraction as fallback.")
                    self._try_extract_number_from_text(reasoning)
            else:
                rospy.logwarn("VLM reprompt failed to return any action. Trying text extraction as fallback.")
                self._try_extract_number_from_text(reasoning)
        self.is_answering = False

    def _try_extract_number_from_text(self, reasoning: str):
        """Fallback method to extract number from reasoning text when VLM reprompt fails."""
        rospy.loginfo(f"Attempting text extraction from reasoning: '{reasoning}'")
        
        # Try to find numbers in the reasoning text (both digits and words)
        import re
        
        # First try to find digit numbers
        digit_numbers = re.findall(r'\b\d+\b', reasoning)
        
        # Also try to find written numbers
        word_to_num = {
            'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
            'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20
        }
        
        written_numbers = []
        for word, num in word_to_num.items():
            if re.search(r'\b' + word + r'\b', reasoning.lower()):
                written_numbers.append(num)
        
        if digit_numbers:
            extracted_number = int(digit_numbers[-1])  # Use last digit number found
            rospy.loginfo(f"Extracted digit number {extracted_number} from reasoning. Publishing.")
            from std_msgs.msg import Int32
            self.numerical_pub.publish(Int32(data=extracted_number))
        elif written_numbers:
            extracted_number = written_numbers[-1]  # Use last written number found
            rospy.loginfo(f"Extracted written number {extracted_number} from reasoning. Publishing.")
            from std_msgs.msg import Int32
            self.numerical_pub.publish(Int32(data=extracted_number))
        else:
            rospy.logwarn("Could not extract numerical answer from text. Mission failed.")

    def _use_exploration_fallback(self, panoramic_image):
        """Last resort exploration when VLM fails to respond properly."""
        rospy.loginfo("Using exploration fallback - trying to navigate to center division.")
        
        # Create a simple exploration action to move forward/center
        fallback_action = {
            'type': 'navigation',
            'reasoning': 'Exploration fallback to continue searching for the target',
            'image_division': 'center',
            'subgoal_description': 'Point to the free area in the center to continue exploration'
        }
        
        try:
            self.handle_navigation_action(fallback_action, panoramic_image)
            rospy.loginfo("Exploration fallback navigation initiated.")
        except Exception as e:
            rospy.logerr(f"Exploration fallback failed: {e}. Mission will stop.")
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

    def handle_object_reference_end(self, action):
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
                # Get the image division where VLM found the target
                target_division = action.get('image_division')
                self.resolve_multiple_objects(target_name, target_markers, find_result.get('reasoning', ''), target_division)
        else:
            # FAILURE: The target was not found, or an error occurred.
            reason = find_result.get('reasoning') if find_result else "No valid response from VLM."
            rospy.loginfo(f"Target not found in current vicinity. Re-prompting VLM to continue navigation. Reason: {reason}")
            self.reprompt_and_continue()

    def reprompt_and_continue(self):
        # Check if we've exceeded maximum reprompts
        if self.reprompt_count >= self.max_reprompts:
            rospy.logwarn(f"Exceeded maximum reprompts ({self.max_reprompts}). Using exploration fallback.")
            sensor_snapshot = self.vln_data_interface.get_current_snapshot()
            panoramic_image = sensor_snapshot.get('image')
            if panoramic_image:
                self._use_exploration_fallback(panoramic_image)
            else:
                rospy.logerr("Cannot continue, image data not available. Stopping mission.")
                self.is_answering = False
            return
        
        self.reprompt_count += 1
        rospy.loginfo(f"Reprompt attempt {self.reprompt_count}/{self.max_reprompts}")
        
        sensor_snapshot = self.vln_data_interface.get_current_snapshot()
        panoramic_image = sensor_snapshot.get('image')
        if panoramic_image is None:
            rospy.logwarn("Cannot re-prompt, image data is not available.")
            return

        reprompt_msg = "You are not yet close enough to the target object. Please provide a new navigation action to get closer to the object described in the mission."
        action = self.vlm_client.get_vlm_response(panoramic_image, self.current_question, reprompt=reprompt_msg)
        
        if action and action.get('type') == 'navigation':
            self.handle_navigation_action(action, panoramic_image)
        elif action and action.get('type') == 'end':
            # VLM decided to end instead of navigate - handle the end action
            rospy.loginfo("VLM chose to end after reprompt. Processing end action.")
            self.handle_end_action(action)
        else:
            # VLM failed to provide a valid response - try alternative approaches
            rospy.logwarn("VLM failed to provide a valid response after re-prompting. Trying alternative approach.")
            
            # Try a more generic reprompt with different wording
            fallback_msg = "The target object may not be clearly visible from your current position. Please navigate to explore the environment and find a better view of the target object."
            fallback_action = self.vlm_client.get_vlm_response(panoramic_image, self.current_question, reprompt=fallback_msg)
            
            if fallback_action and fallback_action.get('type') == 'navigation':
                rospy.loginfo("Fallback reprompt successful. Continuing navigation.")
                self.handle_navigation_action(fallback_action, panoramic_image)
            elif fallback_action and fallback_action.get('type') == 'end':
                rospy.loginfo("Fallback reprompt resulted in end action. Processing.")
                self.handle_end_action(fallback_action)
            else:
                # Last resort: continue with a simple exploration command
                rospy.logwarn("All reprompt attempts failed. Using exploration fallback.")
                self._use_exploration_fallback(panoramic_image)

    def waypoint_reached_callback(self, msg):
        if not self.is_answering or not msg.data:
            return
        rospy.loginfo("Waypoint reached. Executing next Reason-Act step.")
        self.execute_reason_act_step()

    def draw_and_publish_roborefer_annotation(self, panoramic_image, target_pixel, target_markers, closest_marker_id=None):
        """
        Annotate the panoramic image with RoboRefer result and candidate markers,
        similar to pixel_to_waypoint_node.py
        """
        try:
            # Convert PIL image to OpenCV format
            cv_image = cv2.cvtColor(np.array(panoramic_image), cv2.COLOR_RGB2BGR)
            
            # Draw RoboRefer target pixel (bright green circle with black outline)
            target_x, target_y = int(target_pixel.x), int(target_pixel.y)
            cv2.circle(cv_image, (target_x, target_y), radius=20, color=(0, 0, 0), thickness=6)  # Black outline
            cv2.circle(cv_image, (target_x, target_y), radius=20, color=(0, 255, 0), thickness=3)  # Green fill
            cv2.putText(cv_image, "RoboRefer", (target_x + 25, target_y - 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
            # Draw candidate marker positions
            for marker in target_markers:
                marker_pixel = self.project_marker_to_pixel(marker)
                if marker_pixel is not None:
                    marker_x, marker_y = int(marker_pixel.x), int(marker_pixel.y)
                    
                    # Use different colors for selected vs non-selected markers
                    if closest_marker_id is not None and marker.id == closest_marker_id:
                        # Selected marker: bright blue
                        color = (255, 0, 0)  # Blue in BGR
                        label = f"SELECTED {marker.id}"
                    else:
                        # Candidate marker: red
                        color = (0, 0, 255)  # Red in BGR
                        label = f"Candidate {marker.id}"
                    
                    cv2.circle(cv_image, (marker_x, marker_y), radius=15, color=(0, 0, 0), thickness=4)  # Black outline
                    cv2.circle(cv_image, (marker_x, marker_y), radius=15, color=color, thickness=2)
                    cv2.putText(cv_image, label, (marker_x + 20, marker_y + 20),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            # Convert back to ROS Image message
            annotated_image_msg = self.bridge.cv2_to_imgmsg(cv_image, "bgr8")
            annotated_image_msg.header.stamp = rospy.Time.now()
            
            # Publish the annotated image
            self.annotated_image_pub.publish(annotated_image_msg)
            rospy.loginfo("Published RoboRefer annotated image to /roborefer_annotated_image")
            
        except Exception as e:
            rospy.logwarn(f"Failed to create annotated image: {e}")

    def resolve_multiple_objects(self, target_name: str, target_markers: List[Marker], reasoning: str, target_division: str = None):
        """
        When multiple objects of the same type exist, use RoboRefer to determine 
        which specific object matches the description in the question.
        """
        # Get current panoramic image
        sensor_snapshot = self.vln_data_interface.get_current_snapshot()
        panoramic_image = sensor_snapshot.get('image')
        if panoramic_image is None:
            rospy.logwarn("Cannot resolve multiple objects, image data is not available. Please check if the system is functioning correctly.")
            self.reprompt_and_continue()
            return

        # If VLM specified which division contains the target, use that specific crop
        roborefer_image = panoramic_image
        pixel_offset_x = 0
        
        if target_division:
            rospy.loginfo(f"VLM specified target is in '{target_division}' division. Using cropped image for RoboRefer.")
            crop_width = 640
            if target_division == 'left':
                pixel_offset_x = 0
                roborefer_image = panoramic_image.crop((0, 0, crop_width, 640))
            elif target_division == 'center':
                pixel_offset_x = crop_width
                roborefer_image = panoramic_image.crop((crop_width, 0, 2 * crop_width, 640))
            elif target_division == 'right':
                pixel_offset_x = 2 * crop_width
                roborefer_image = panoramic_image.crop((2 * crop_width, 0, 3 * crop_width, 640))
            else:
                rospy.logwarn(f"Unknown target division '{target_division}'. Using full panoramic image.")
        else:
            rospy.loginfo("No target division specified. Using full panoramic image for RoboRefer.")

        # Use RoboRefer to get the pixel coordinate of the target object
        # Extract the description from the original question for RoboRefer
        rospy.loginfo(f"Using RoboRefer to ground the description: '{self.current_question}' in {roborefer_image.size} image")
        target_pixel = self.roborefer_client.get_pixel_from_description(roborefer_image, self.current_question)
        
        if target_pixel and target_division:
            rospy.loginfo(f"RoboRefer found target at ({target_pixel.x}, {target_pixel.y}) in {target_division} crop, adjusting to ({target_pixel.x + pixel_offset_x}, {target_pixel.y}) on full image")
        
        if target_pixel is None:
            rospy.logwarn("RoboRefer failed to ground the target description. Re-prompting to navigate.")
            self.reprompt_and_continue()
            return

        # Convert target pixel to comparable format and adjust for crop offset
        target_x = target_pixel.x + pixel_offset_x
        target_y = target_pixel.y
        rospy.loginfo(f"Adjusted target coordinates: ({target_x}, {target_y}) on full panoramic image")
        
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
        
        # Draw and publish annotated image showing RoboRefer result and all candidate markers
        closest_marker_id = closest_marker.id if closest_marker is not None else None
        
        # Create adjusted target pixel for annotation (on full panoramic image)
        class AdjustedPixel:
            def __init__(self, x, y):
                self.x = x
                self.y = y
        
        adjusted_target_pixel = AdjustedPixel(target_x, target_y)
        self.draw_and_publish_roborefer_annotation(panoramic_image, adjusted_target_pixel, target_markers, closest_marker_id)
        
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
            # Transform marker position to sensor frame (same as marker_annotater.py)
            # Import tf here to avoid circular imports
            import tf
            from geometry_msgs.msg import PoseStamped
            
            # Create tf listener if not exists
            if not hasattr(self, 'tf_listener'):
                self.tf_listener = tf.TransformListener()
            
            # Create PoseStamped for the marker with current timestamp
            marker_pose = PoseStamped()
            marker_pose.header.frame_id = marker.header.frame_id
            marker_pose.header.stamp = rospy.Time.now()  # Use current time to avoid extrapolation
            marker_pose.pose = marker.pose
            
            # Transform to sensor frame with multiple timestamp approaches
            try:
                # First try: Use most recent transform
                self.tf_listener.waitForTransform("sensor", marker.header.frame_id, rospy.Time(0), rospy.Duration(1.0))
                marker_pose_sensor = self.tf_listener.transformPose("sensor", marker_pose)
            except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
                # Fallback: Try with rospy.Time(0) timestamp for the pose too
                marker_pose.header.stamp = rospy.Time(0)
                self.tf_listener.waitForTransform("sensor", marker.header.frame_id, rospy.Time(0), rospy.Duration(1.0))
                marker_pose_sensor = self.tf_listener.transformPose("sensor", marker_pose)
            
            x = marker_pose_sensor.pose.position.x
            y = marker_pose_sensor.pose.position.y
            z = marker_pose_sensor.pose.position.z
            rospy.logdebug(f"Marker {marker.id} in sensor frame: ({x:.2f}, {y:.2f}, {z:.2f})")
            
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
                
        except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException) as e:
            rospy.logwarn(f"Transform to sensor frame failed: {e}")
            return None
        except Exception as e:
            rospy.logwarn(f"Failed to project marker to pixel: {e}")
            return None

if __name__ == '__main__':
    rospy.init_node('challenge_agent_node')
    agent = ChallengeAgentNode()
    rospy.spin()