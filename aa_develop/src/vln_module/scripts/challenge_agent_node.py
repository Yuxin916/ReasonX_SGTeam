# vln_module/scripts/challenge_agent_node.py

import rospy
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Point
from vln_module.utils.vln_data_interface import VLNDataInterface
from vln_module.utils.vlm_client import VLMClient

import requests
import tempfile
import os
import ast
from PIL import Image

# class RoboReferClient:
#     """
#     A DUMMY client that simulates the roborefer grounding server for testing.
#     It does NOT make any network calls.
#     """
#     def __init__(self, server_url="http://127.0.0.1:25547"):
#         # The URL is not used in this dummy version.
#         rospy.loginfo("--- Using DUMMY RoboReferClient ---")
#         pass

#     def get_pixel_from_description(self, image: Image.Image, description: str):
#         """
#         Ignores the image and description, and returns a fixed pixel coordinate (50, 50).
#         """
#         rospy.loginfo(f"RoboRefer (DUMMY): Received description '{description}' for a {image.size} image.")
        
#         # All network and file logic is removed.
#         # Simply return a hardcoded point for testing purposes.
#         dummy_x = 50
#         dummy_y = 50
        
#         rospy.loginfo(f"RoboRefer (DUMMY): Returning fixed pixel ({dummy_x}, {dummy_y})")
#         return Point(x=dummy_x, y=dummy_y, z=0)
class RoboReferClient:
    """A client to interact with the roborefer grounding server."""
    def __init__(self, server_url="http://127.0.0.1:25547"):
        self.server_url = server_url
        # The prompt suffix required by the roborefer API
        self.suffix = " Your answer should be formatted as a list of tuples, i.e. [(x1, y1)], where each tuple contains the x and y coordinates of a point satisfying the conditions above. The coordinates should be between 0 and 1, indicating the normalized pixel locations of the points in the image."

    def get_pixel_from_description(self, image: Image.Image, description: str) -> Point | None:
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

        self.pixel_pub = rospy.Publisher('/vlm_pixel_input', Point, queue_size=10)
        rospy.Subscriber('/challenge_question', String, self.question_callback)
        rospy.Subscriber('/waypoint_reached', Bool, self.waypoint_reached_callback)
        rospy.loginfo("Agent is ready and waiting for a question.")

    def question_callback(self, msg):
        if self.is_answering:
            rospy.logwarn("Received a new question while still processing the previous one. Ignoring.")
            return
        rospy.loginfo(f"New challenge started! Question: '{msg.data}'")
        self.current_question = msg.data
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

        # 1. Get region choice and description from the VLM
        action = self.vlm_client.get_vlm_response(panoramic_image)
        action_type = action.get('type')
        
        if action_type == 'end':
            rospy.loginfo(f"VLM chose to stop: {action.get('reasoning')}. Challenge complete!")
            self.is_answering = False
        elif action_type == 'navigation':
            division = action.get('image_division')
            description = action.get('subgoal_description')
            
            if division and description:
                rospy.loginfo(f"VLM chose division '{division}' with description: '{description}'")
                
                # 2. Crop the image based on VLM's choice
                # Note: Assuming 1920x640, matching the VLM planner.
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

                # 3. Ground the description using RoboRefer on the *cropped* image
                relative_pixel = self.roborefer_client.get_pixel_from_description(selected_crop, description)
                
                if relative_pixel:
                    # 4. Convert relative pixel to panoramic coordinates and publish
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
        else:
            rospy.logerr(f"VLM returned an unknown or error action type: '{action_type}'. Stopping.")
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