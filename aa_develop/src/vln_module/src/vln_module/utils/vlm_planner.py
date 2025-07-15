import os
import time
import logging
from PIL import Image as PILImage
import json
import re


# import google.generativeai as genai
from google import genai
# from google.generativeai.types import GenerationConfig, content_types

from typing import Literal, Optional
from pydantic import BaseModel, Field

def clean_and_parse_json(response: str):
    # Remove code fencing (```json or ```), then strip extra whitespace
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
    return json.loads(cleaned)


# --- 1. Standard Python Logging Setup ---
# Replaces rospy.loginfo, etc.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 2. Pydantic Model for Structured VLM Output (Unchanged) ---
# This class is pure Python and requires no changes.
class VLMResponse(BaseModel):
    """The structured output we expect from the VLM."""
    type: Literal["navigation", "end"]
    reasoning: str
    
    # These fields are optional. If the VLM doesn't provide them,
    pixel_x: Optional[int] = Field(default=None, description="The x-coordinate of the pixel to navigate towards if type is 'navigation'.")
    pixel_y: Optional[int] = Field(default=None, description="The y-coordinate of the pixel to navigate towards if type is 'navigation'.")


class VLMPlanner:
    """
    A standalone Python class to handle all interactions with the Gemini VLM.
    It takes a PIL Image and a mission history to generate a structured action.
    """
    def __init__(self):
        logging.info("Initializing VLM Planner...")
        # --- Securely configure the Gemini client ---
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logging.error("GOOGLE_API_KEY environment variable not set!")
            raise ValueError("API Key not found")
        
        # genai.configure(api_key=api_key)
        self.client = genai.Client(api_key=api_key)
        
        self.question = None

        # --- Set up the model for structured (JSON) output ---
        # generation_config = GenerationConfig(response_mime_type="application/json")
        # self.model = genai.GenerativeModel(
        #     model_name="gemini-2.5-flash",
        #     # generation_config=generation_config,
        #     system_instruction="You are the reasoning engine for a robot navigating a home environment. Your goal is to follow user commands step-by-step."
        # )

        self.conversation_history = []
        logging.info("VLM Planner initialized successfully.")

    def start_new_mission(self, question: str):
        # response = self.client.models.generate_content(
        #     model="gemini-2.5-pro", contents="Explain how AI works in a few words"
        # )
        # # Print response.text with simple coloring (green) using ANSI escape codes
        # print(f"\033[92m{response.text}\033[0m")
        self.chat = self.client.chats.create(model="gemini-2.5-pro")
        logging.info(f"VLM Planner: Starting new mission. Question: '{question}'")
        self.question = question
        self.chat.send_message(
            f"""You are a visual decision-making module for a home-assistant robot.
    Your job is to interpret visual observations and plan the next step toward the mission: "{self.question}".

    The robot is stationary and provides a 360-degree panoramic image of its surroundings. It is equipped with a local planner that can navigate to specific pixel locations in the image.
    The image resolution is 1920x640 pixels (width x height), with the front-facing direction at the left edge.
    Locate important object bounding boxes in the scene to enhance reasoning about the next action.
    You have two choices for your action:
    1. "navigation": If the robot should move to a new region of interest. You must provide the (x, y) pixel location on navigable ground to move toward.
    2. "end": If you are close enough to the goal or task-relevant object and believe the mission is complete.

    Respond ONLY with a single JSON object in this exact format (no extra text):

    {{
      "type": "navigation" or "end",
      "important_objects_bounding_boxes": [
        {{ "label": "<object_label>", "bounding_box": [<x1>, <y1>, <x2>, <y2>] }},
        ...
      ],
      "reasoning": "<brief explanation of your decision>",
      "pixel_x": <integer, required if type is 'navigation'>,
      "pixel_y": <integer, required if type is 'navigation'>
    }}
    In the next step, you will receive a panoramic image. You will begin to move after you receive the first image.
    """
        )
        # self.chat.send_message(f"My mission is: {question}")

    def get_vlm_response(self, panoramic_image: PILImage.Image) -> Optional[VLMResponse]:
        if not self.question:
            logging.error("VLM Planner: get_vlm_response called before start_new_mission.")
            return None

        logging.info("VLM Planner: Preparing new VLM call...")

        prompt_parts = [
            "Here is the current 1920x640 panoramic view. What is the next action? Note that it is not guaranteed you navigated to the intended area proposed last step, so you need to carefully observe the environment to make a new decision.",
            panoramic_image
        ]


        try:
            logging.info("VLM Planner: Sending prompt to Gemini...")
            response = self.chat.send_message(prompt_parts)

            logging.info("VLM Planner: Received raw response.")
            print(response.text)

            response_model = VLMResponse.model_validate(clean_and_parse_json(response.text))
            logging.info(f"Parsed response: {response_model.type}, Reasoning: {response_model.reasoning}")
            return response_model

        except Exception as e:
            logging.error(f"VLM call or parsing failed: {e}")
            return None

# # --- Standalone Testing Block ---
# if __name__ == '__main__':
#     print("--- Running VLM Planner Standalone Test ---")

#     # 1. Make sure your GOOGLE_API_KEY is set as an environment variable
#     if not os.getenv("GOOGLE_API_KEY"):
#         print("\nERROR: Please set the GOOGLE_API_KEY environment variable first.")
#         print("Example: export GOOGLE_API_KEY='your_key_here'\n")
#         exit()

#     # 2. Create a dummy PIL image (e.g., a black panoramic image)
#     # In your real application, you would load your image here:
#     # try:
#     #     dummy_panoramic_image = PILImage.open("path/to/your/image.png")
#     # except FileNotFoundError:
#     #     print("Test image not found, using a black placeholder.")
#     #     dummy_panoramic_image = PILImage.new('RGB', (1920, 640), 'black')
    
#     print("Using a black placeholder image for this test.")
#     dummy_panoramic_image = PILImage.new('RGB', (1920, 640), 'black')

#     # 3. Initialize the planner and start a mission
#     planner = VLMPlanner()
#     planner.start_new_mission("find the flowers near the window")

#     # 4. Get the first response from the VLM
#     response1 = planner.get_vlm_response(dummy_panoramic_image)
#     if response1:
#         print("\n--- First VLM Response ---")
#         # .model_dump_json() is the Pydantic v2 equivalent of .json()
#         print(response1.model_dump_json(indent=2))

#         # 5. Simulate getting a second response after "moving"
#         if response1.type == 'explore':
#             print("\nSimulating a second step after exploration...")
#             # In a real scenario, you'd load a new image here
#             response2 = planner.get_vlm_response(dummy_panoramic_image)
#             if response2:
#                 print("\n--- Second VLM Response ---")
#                 print(response2.model_dump_json(indent=2))