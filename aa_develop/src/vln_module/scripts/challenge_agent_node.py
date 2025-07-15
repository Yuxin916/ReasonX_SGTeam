import rospy
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Point
# --- IMPORTS HAVE CHANGED ---
from vln_module.utils.vln_data_interface import VLNDataInterface
from vln_module.utils.vlm_client import VLMClient # Use the client, not the planner

class ChallengeAgentNode:
    def __init__(self):
        rospy.loginfo("Initializing Challenge Agent Node...")
        self.vln_data_interface = VLNDataInterface()
        self.vlm_client = VLMClient() # Instantiate the client

        self.current_question = None
        self.is_answering = False

        # ... (Publishers and Subscribers remain the same) ...
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
        
        # Start the mission on the VLM Server
        if self.vlm_client.start_new_mission(self.current_question):
            self.is_answering = True
            # Start the first step of the Reason-Act loop
            self.execute_reason_act_step()
        else:
            rospy.logerr("Could not start mission on VLM server. Aborting.")

    def execute_reason_act_step(self):
        rospy.loginfo("--- New Reason-Act Step ---")
        
        sensor_snapshot = self.vln_data_interface.get_current_snapshot()
        pil_image = sensor_snapshot.get('image')

        if pil_image is None:
            rospy.logwarn("Cannot execute step, image data is not yet available.")
            return

        # Get a structured action from the VLM Client
        action = self.vlm_client.get_vlm_response(pil_image)

        # ... (The rest of the logic for parsing the action is almost the same) ...
        action_type = action.get('type')
        
        if action_type == 'end':
            rospy.loginfo(f"VLM chose to stop: {action.get('reasoning')}. Challenge complete!")
            self.is_answering = False
            
        elif action_type == 'navigation':
            pixel_x = action.get('pixel_x')
            pixel_y = action.get('pixel_y')
            if pixel_x is not None and pixel_y is not None:
                rospy.loginfo(f"VLM chose to navigate. Target pixel: ({pixel_x}, {pixel_y})")
                pixel_msg = Point(x=pixel_x, y=pixel_y, z=0)
                self.pixel_pub.publish(pixel_msg)
            else:
                rospy.logerr("VLM chose to navigate but provided no pixel coordinates.")
                self.is_answering = False
            
        else:
            rospy.logerr(f"VLM returned an unknown or error action type: '{action_type}'. Stopping.")
            self.is_answering = False

    # ... waypoint_reached_callback remains the same ...
    def waypoint_reached_callback(self, msg):
        if not self.is_answering or not msg.data:
            return
        
        rospy.loginfo("Waypoint reached. Executing next Reason-Act step.")
        self.execute_reason_act_step()

if __name__ == '__main__':
    rospy.init_node('challenge_agent_node')
    agent = ChallengeAgentNode()
    rospy.spin()