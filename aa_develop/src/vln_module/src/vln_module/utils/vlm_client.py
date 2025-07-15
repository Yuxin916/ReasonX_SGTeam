import rospy
import requests
import base64
import io
from PIL import Image as PILImage

class VLMClient:
    """
    A client to communicate with the standalone VLM Flask server.
    This class runs in the ROS Python 3.8 environment.
    """
    def __init__(self, server_url="http://localhost:5000"):
        self.server_url = server_url
        rospy.loginfo(f"VLM Client initialized. Server URL: {self.server_url}")

    def start_new_mission(self, question: str) -> bool:
        """Sends the initial question to the VLM server."""
        try:
            endpoint = f"{self.server_url}/start_mission"
            response = requests.post(endpoint, json={"question": question}, timeout=60)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            rospy.loginfo("Successfully started new mission on VLM server.")
            return True
        except requests.exceptions.RequestException as e:
            rospy.logerr(f"Failed to start new mission on VLM server: {e}")
            return False

    def get_vlm_response(self, panoramic_image: PILImage.Image) -> dict:
        """Encodes the image, sends it, and gets the next action."""
        # Convert PIL Image to a Base64 string
        buffered = io.BytesIO()
        panoramic_image.save(buffered, format="PNG")
        base64_image_str = base64.b64encode(buffered.getvalue()).decode('utf-8')

        try:
            endpoint = f"{self.server_url}/get_next_action"
            payload = {"image": base64_image_str}
            response = requests.post(endpoint, json=payload, timeout=60) # Longer timeout for VLM processing
            response.raise_for_status()
            
            # The response JSON is the action dictionary we need
            return response.json()
        except requests.exceptions.RequestException as e:
            rospy.logerr(f"Failed to get VLM response from server: {e}")
            return {'type': 'error', 'data': 'HTTP request failed'}