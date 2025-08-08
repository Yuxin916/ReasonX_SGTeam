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
from typing import Dict
import rospy
from geometry_msgs.msg import Point
from PIL import Image

class RoboReferClient:
    """A client to interact with the roborefer grounding server."""
    def __init__(self, server_url="http://127.0.0.1:25547"):
        self.server_url = server_url
        # The prompt suffix required by the roborefer API
        self.suffix = " Your answer should be formatted as a list of tuples, i.e. [(x1, y1)], where each tuple contains the x and y coordinates of a point satisfying the conditions above. The coordinates should be between 0 and 1, indicating the normalized pixel locations of the points in the image."

    def get_pixel_from_description(self, image: Image.Image, description: str):
        """
        Takes a PIL image and a text description, calls the roborefer server,
        and returns the denormalized pixel coordinate relative to THAT image.
        """
        rospy.loginfo(f"RoboRefer: Grounding description: '{description}'")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image.save(tmp.name, "PNG")
            tmp_path = tmp.name
        
        try:
            full_prompt = description + self.suffix
            with open(tmp_path, 'rb') as f:
                files = {'images': (os.path.basename(tmp_path), f, 'image/png')}
                data = {'prompt': full_prompt}
                rospy.loginfo(f"RoboRefer: Calling server at {self.server_url} with a {image.size[0]}x{image.size[1]} image.")
                response = requests.post(self.server_url, files=files, data=data, timeout=20)
                response.raise_for_status()
                
                normalized_points = ast.literal_eval(response.text.strip())
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
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

class ChallengeAgentNode:
    def __init__(self):
        rospy.loginfo("Initializing Challenge Agent Node...")
        self.vln_data_interface = VLNDataInterface()
        self.vlm_client = VLMClient()
        self.roborefer_client = RoboReferClient()

        self.current_question = None
        self.is_answering = False
        self.question_type = None 
        self.nearby_objects_data: Dict[str, Marker] = {}

        self.pixel_pub = rospy.Publisher('/vlm_pixel_input', Point, queue_size=10)
        self.answer_pub = rospy.Publisher('/selected_object_marker', Marker, queue_size=10)
        
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

    def object_markers_callback(self, msg: MarkerArray):
        current_objects: Dict[str, Marker] = {}
        for marker in msg.markers:
            if marker.ns:
                current_objects[marker.ns] = marker
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

        action = self.vlm_client.get_vlm_response(panoramic_image)
        if not action:
            rospy.logerr("Failed to get a valid action from VLM. Stopping mission.")
            self.is_answering = False
            return

        action_type = action.get('type')
        
        if action_type == 'end':
            if self.question_type == 'object_reference':
                rospy.loginfo("VLM chose to end. Verifying object presence for reference question.")
                self.handle_object_reference_end()
            else:
                rospy.loginfo(f"VLM chose to stop: {action.get('reasoning')}. Challenge complete!")
                self.is_answering = False

        elif action_type == 'navigation':
            self.handle_navigation_action(action, panoramic_image)
        else:
            rospy.logerr(f"VLM returned an unknown or error action type: '{action_type}'. Stopping.")
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
            target_marker = self.nearby_objects_data[target_name]
            rospy.loginfo(f"SUCCESS: Identified target '{target_name}'. Publishing its bounding box. Reason: {find_result.get('reasoning')}")
            self.answer_pub.publish(target_marker)
            self.is_answering = False # Mission complete!
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
        action = self.vlm_client.get_vlm_response(panoramic_image, reprompt=reprompt_msg)
        
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

if __name__ == '__main__':
    rospy.init_node('challenge_agent_node')
    agent = ChallengeAgentNode()
    rospy.spin()