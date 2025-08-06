# vln_module/src/vln_module/utils/vlm_planner.py

import os
import logging
from PIL import Image as PILImage
import json
import re

from google import genai
from typing import Literal, Optional
from pydantic import BaseModel, Field

def clean_and_parse_json(response: str):
    # Remove code fencing (```json or ```), then strip extra whitespace
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
    return json.loads(cleaned)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- MODIFIED Pydantic Model for the new task ---
class VLMResponse(BaseModel):
    """The structured output we expect from the VLM."""
    type: Literal["navigation", "end"]
    reasoning: str
    
    image_division: Optional[Literal["left", "center", "right"]] = Field(
        default=None, 
        description="The selected image division ('left', 'center', 'right') containing the navigation subgoal."
    )
    subgoal_description: Optional[str] = Field(
        default=None, 
        description="A natural language description of the subgoal within the selected division, starting with 'Point to' or 'Point out'."
    )


class VLMPlanner:
    """
    Handles interactions with the Gemini VLM to select an image region and a subgoal.
    """
    def __init__(self):
        logging.info("Initializing VLM Planner...")
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logging.error("GOOGLE_API_KEY environment variable not set!")
            raise ValueError("API Key not found")
        
        self.client = genai.Client(api_key=api_key)
        self.question = None
        logging.info("VLM Planner initialized successfully.")

    def start_new_mission(self, question: str):
        self.chat = self.client.chats.create(model="gemini-2.5-pro")
        logging.info(f"VLM Planner: Starting new mission. Question: '{question}'")
        self.question = question
        # --- REFINED PROMPT for the new 3-image selection task ---
        self.chat.send_message(
            f"""You are a visual decision-making module for a home-assistant robot. Your mission is: "{self.question}".

    You will be given three 640x640 square images, labeled "left", "center", and "right", which form a combined panoramic view of the robot's surroundings.

    Your task is to:
    1. Decide which of the three images ("left", "center", or "right") shows the most promising direction to proceed for the mission.
    2. Within that CHOSEN image, provide a clear natural language description of the navigation target.

    You have two choices for your action type:
    1. "navigation": If you should move. You must specify the `image_division` and provide a `subgoal_description`. This description MUST start with "Point to the free area".
        - Example: "Point to the free area between the black chair and the sofa." or "Point to the free area in front of the plant".
    2. "end": If you believe the mission is complete.

    Respond ONLY with a single JSON object in this exact format (no extra text):

    {{
      "type": "navigation" or "end",
      "reasoning": "<brief explanation of your decision>",
      "image_division": "<'left', 'center', or 'right', required if type is 'navigation'>",
      "subgoal_description": "<A description for the CHOSEN division, starting with 'Point to the free area'>"
    }}
    You will begin to move after you receive the first set of images.
    """
        )

    def get_vlm_response(self, panoramic_image: PILImage.Image) -> Optional[VLMResponse]:
        if not self.question:
            logging.error("VLM Planner: get_vlm_response called before start_new_mission.")
            return None

        logging.info("VLM Planner: Preparing new VLM call with 3 image divisions...")
        
        # Crop the panoramic image into three 640x640 sections
        width, height = panoramic_image.size
        if width != 1920 or height != 640:
            logging.warning(f"Expected 1920x640 image, but got {width}x{height}. Cropping might be incorrect.")
            # Fallback for potentially different aspect ratios, assuming width is 3*height
            crop_width = width // 3
        else:
            crop_width = 640

        img_left = panoramic_image.crop((0, 0, crop_width, 640))
        img_center = panoramic_image.crop((crop_width, 0, 2 * crop_width, 640))
        img_right = panoramic_image.crop((2 * crop_width, 0, 3 * crop_width, 640))

        prompt_parts = [
            "Here are the three views: left, center, and right. Analyze them and decide on the next action based on the instructions.",
            "Left view:", img_left,
            "Center view:", img_center,
            "Right view:", img_right,
        ]

        try:
            logging.info("VLM Planner: Sending prompt with 3 images to Gemini...")
            response = self.chat.send_message(prompt_parts)

            logging.info("VLM Planner: Received raw response.")
            print(response.text)

            response_model = VLMResponse.model_validate(clean_and_parse_json(response.text))
            logging.info(f"Parsed response: {response_model.type}, Division: {response_model.image_division}, Reasoning: {response_model.reasoning}")
            return response_model

        except Exception as e:
            logging.error(f"VLM call or parsing failed: {e}")
            return None