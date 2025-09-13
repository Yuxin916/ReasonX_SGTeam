# vln_module/src/vln_module/utils/vlm_planner.py

import os
import logging
from PIL import Image as PILImage
import json
import re

from google import genai
from typing import Literal, Optional, List
from pydantic import BaseModel, Field

def clean_and_parse_json(response: str):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
    if not cleaned:
        raise ValueError("VLM response was empty.")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print("Raw VLM response:", repr(response))
        raise

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SubgoalState(BaseModel):
    """Represents a subgoal in the task."""
    description: str = Field(description="Natural language description of the subgoal")
    completed: bool = Field(default=False, description="Whether this subgoal has been completed")

class SubgoalStatus(BaseModel):
    """Status of a subgoal in the task"""
    description: str = Field(description="The subgoal description")
    completed: bool = Field(description="Whether this subgoal has been completed")

class VLMResponse(BaseModel):
    """The structured output we expect from the VLM."""
    type: Literal["navigation", "end"]
    reasoning: str
    
    image_division: Optional[Literal["left", "center", "right"]] = Field(
        default=None, 
        description="The selected image division ('left', 'center', 'right') containing the navigation subgoal or target object."
    )
    subgoal_description: Optional[str] = Field(
        default=None, 
        description="A natural language description of the subgoal within the selected division, starting with 'Point to' or 'Point out'."
    )
    number: Optional[int] = Field(
        default=None,
        description="The answer to a numerical question, e.g., for 'How many' questions. Only present if type is 'end' and the question is numerical."
    )
    subgoal_states: Optional[List[SubgoalStatus]] = Field(
        default=None,
        description="List of all subgoals and their completion status"
    )

# --- NEW Consolidated Pydantic Model ---
class FoundObjectResponse(BaseModel):
    """The structured output for finding a target object in a list."""
    is_present: bool = Field(description="True if the primary target object from the question is found in the provided list, otherwise False.")
    target_name: Optional[str] = Field(default=None, description="The name of the target object from the list if it is present.")
    reasoning: str = Field(description="A brief explanation for the decision.")


class VLMPlanner:
    """
    Handles interactions with the Gemini VLM to select an image region and a subgoal.
    """
    def __init__(self):
        logging.info("Initializing VLM Planner...")
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            # api_key = "AIzaSyDo6m4aQtQSU7ILS6ZlDxXz6P_YCxmOeoQ"
            logging.warning("GOOGLE_API_KEY environment variable not set. Using the default API key.")
            # logging.error("GOOGLE_API_KEY environment variable not set!")
            # raise ValueError("API Key not found")
        
        self.client = genai.Client(api_key=api_key)
        self.question = None
        self.chat = None
        self.subgoals = []  # List[SubgoalState]
        self.is_instruction_task = False
        logging.info("VLM Planner initialized successfully.")

    def start_new_mission(self, question: str):
        logging.info(f"VLM Planner: Starting new mission. Question: '{question}'")
        self.question = question
        self.subgoals = []

        # Determine question type
        self.is_numerical = bool(re.match(r"\s*how many", question.strip(), re.IGNORECASE))
        self.is_object_reference = bool(re.search(r'\b(find|locate|point to|what is|which is|get|bring me)\b', question.strip(), re.IGNORECASE))
        self.is_instruction_task = not (self.is_numerical or self.is_object_reference)
        
        # Just initialize empty subgoals list if it's an instruction task
        if self.is_instruction_task:
            self._initialize_subgoals()

    def _initialize_subgoals(self):
        """Analyzes the instruction and prepares empty subgoal list without VLM interaction"""
        prompt = f'''You are a task planning assistant. Your job is to break down navigation instructions into key spatial targets.

        Instruction: "{self.question}"

        Extract navigation targets from the instruction and create subgoals. Pay special attention to these types of targets:
        1. Objects with spatial context (e.g., "vase on the cabinet")
        2. Spaces between objects (e.g., "path between couch and table" → "free space between couch and table")

        Important Rules:
        - Convert phrases about paths or routes into "free space between" format
        - For actions like "take the path between X and Y", convert to "free space between X and Y"
        - Keep all spatial relationships and context in the subgoal description
        - Preserve the order of goals from the original instruction

        Format your response as a JSON array of object-relationship descriptions:
        ["<target description with spatial context>", ...]
        '''

        try:
            # Create a temporary chat just for decomposition
            temp_chat = self.client.chats.create(model="gemini-2.5-pro")
            response = temp_chat.send_message(prompt)
            subgoals = clean_and_parse_json(response.text)
            if isinstance(subgoals, list):
                self.subgoals = [SubgoalState(description=desc) for desc in subgoals]
                print("\n=== Initial Task Decomposition ===")
                print(f"Original instruction: \"{self.question}\"")
                print("\nPlanned Subgoals:")
                for i, subgoal in enumerate(self.subgoals, 1):
                    print(f"{i}. {subgoal.description}")
                print("=========================\n")
                logging.info(f"Task decomposed into {len(self.subgoals)} subgoals: {[s.description for s in self.subgoals]}")
            else:
                logging.error("Failed to parse subgoals from response")
                self.subgoals = []
        except Exception as e:
            logging.error(f"Failed to decompose task into subgoals: {e}")
            self.subgoals = []

    def _get_initial_prompt(self):
        """Returns the appropriate initial prompt based on question type and includes initial subgoal state for instruction tasks"""
        base_prompt = f"You are a visual decision-making module for a home-assistant robot. Your mission is: \"{self.question}\"\n\n"
        
        if self.is_instruction_task:
            # For instruction tasks, include the initial subgoal states and rules for completion
            subgoals_json = json.dumps([{"description": sg.description, "completed": sg.completed} for sg in self.subgoals])
            return base_prompt + f"""Initial Task Structure:
            These are the subgoals I've identified: {subgoals_json}
            
            **Critical Rules for Subgoal Completion and Navigation:**
            1. Never mark a subgoal as complete until you see CLEAR VISUAL EVIDENCE of completion
            2. The robot hasn't moved yet, so no subgoals can be complete at the start
            3. Work through subgoals in sequence
            4. You must visually confirm arrival at each target before marking it complete
            5. Include updated subgoal_states in EVERY response
            6. Navigation Strategy for Subgoals:
               IF TARGET IS VISIBLE in any view:
                 - Use EXACTLY the same language as in the subgoal list
                 - Just add "Point to the free area near/at/between" in front
                 - Example: If subgoal is "vase on the cabinet", say "Point to the free area near vase on the cabinet"
               IF TARGET IS NOT VISIBLE:
                 - Look for environmental cues or connecting spaces that might lead to the target
                 - Choose directions that open up more of the space
                 - Describe navigation in terms of visible landmarks or spaces
                 - Examples:
                   • For "guitar in bedroom" but bedroom isn't visible: "Point to the free area near the hallway"
                   • For "vase on cabinet" but no vase visible: "Point to the free area near the open doorway"
               ALWAYS explain your navigation choice in the reasoning field, especially for non-visible targets
            
            **Response Format:**
            For each observation, respond with:
            {{
                "type": "navigation" or "end",
                "reasoning": "<explain what you see and why you're making this decision>",
                "image_division": "<'left', 'center', or 'right' - required for navigation>",
                "subgoal_description": "<Point to the free area + EXACT SUBGOAL DESCRIPTION>",
                "subgoal_states": {subgoals_json}
            }}
            
            Wait for the first set of images to begin navigation."""
        
        elif self.is_numerical:
            return base_prompt + """
            You will analyze three images for number counting tasks.
            Respond with 'navigation' if you need a better view, or 'end' with the final count.
            You MUST be certain of the count before sending an 'end' response with a number.
            
            **Response Format:**
            {
                "type": "navigation" or "end",
                "reasoning": "<explain what you see and why you're making this decision>",
                "image_division": "<'left', 'center', or 'right' - required for navigation>",
                "subgoal_description": "<where to move, starting with 'Point to the free area'>",
                "number": <integer, required ONLY for 'end' responses>
            }
            
            Wait for the first set of images to begin navigation."""
        
        else:  # object reference
            return base_prompt + """
            You will help find specific objects in the scene.
            Use clear visual evidence to confirm object locations.
            Navigate carefully and end only when the target is clearly found.
            
            **Your Capabilities:**
            You have a local planner that handles pathing and obstacle avoidance.
            For objects you want to approach, use "Point to the free area near <object>".
            
            **Task Strategy:**
            1. Identify Primary Target and any Relational Objects
            2. For "closest to" queries, focus on reaching the reference object first
            3. For general searches, navigate toward visible targets or promising areas
            4. Only end when target is clearly found with visual confirmation
            5. **CRITICAL**: When you end (type: "end"), you MUST specify which image division contains the target object
            
            **Response Format:**
            For navigation:
            {
                "type": "navigation",
                "reasoning": "<explain what you see and why you're making this decision>",
                "image_division": "<'left', 'center', or 'right' - required for navigation>",
                "subgoal_description": "<where to move, starting with 'Point to the free area'>"
            }
            
            For ending (target found):
            {
                "type": "end",
                "reasoning": "<explain that you found the target and where it is>",
                "image_division": "<'left', 'center', or 'right' - REQUIRED: which division contains the target object>"
            }
            
            Wait for the first set of images to begin navigation."""

    def get_vlm_response(self, panoramic_image: PILImage.Image, question: str, reprompt: Optional[str] = None) -> Optional[VLMResponse]:
        if not self.question:
            logging.error("VLM Planner: get_vlm_response called before start_new_mission.")
            return None

        # Create chat session if this is the first call
        is_first_call = not self.chat
        if is_first_call:
            self.chat = self.client.chats.create(model="gemini-2.5-pro")
            
        logging.info("VLM Planner: Preparing new VLM call with 3 image divisions...")

        width, height = panoramic_image.size
        if width != 1920 or height != 640:
            logging.warning(f"Expected 1920x640 image, but got {width}x{height}. Cropping might be incorrect.")
            crop_width = width // 3
        else:
            crop_width = 640

        img_left = panoramic_image.crop((0, 0, crop_width, 640))
        img_center = panoramic_image.crop((crop_width, 0, 2 * crop_width, 640))
        img_right = panoramic_image.crop((2 * crop_width, 0, 3 * crop_width, 640))

        # Build prompt based on task type and whether this is the first call
        if is_first_call:
            # First call - get initial prompt for the task type
            initial_prompt = self._get_initial_prompt()
            
            if self.is_instruction_task:
                # For instruction tasks, add the critical first observation rules
                first_observation_rules = """
                ⚠️ CRITICAL FIRST OBSERVATION RULES ⚠️
                1. This is your FIRST VIEW of the environment
                2. The robot has NOT MOVED from its starting position
                3. You CANNOT mark ANY subgoal as complete because:
                   - No navigation has occurred yet
                   - You haven't reached any destinations
                   - You need to MOVE to confirm completion
                4. Your first observation tasks:
                   - Understand the full panoramic view and room layout
                   - Check if any subgoal targets are directly visible
                   - If targets aren't visible, look for promising paths:
                     • Doorways, hallways, or openings to unexplored areas
                     • Architectural cues about room types
                     • Signs of the type of space you're looking for
                   - Choose direction based on visible evidence or exploration potential
                5. You MUST keep ALL subgoals marked as incomplete (completed: false)
                6. Be explicit in your reasoning about why you chose a direction, especially for non-visible targets
                """
                prompt_parts = [initial_prompt + "\n\n" + first_observation_rules]
            else:
                prompt_parts = [initial_prompt]
        else:
            # For subsequent calls
            prompt_parts = [f"The original question is: {question}"]
            
            if self.is_instruction_task:
                # Prepare the current state of all subgoals
                subgoals_json = json.dumps([{"description": sg.description, "completed": sg.completed} for sg in self.subgoals])
                
                # Find the first uncompleted task
                current_task = next((sg.description for sg in self.subgoals if not sg.completed), "All tasks complete")
                
                subgoal_status = (
                    f"Current Subgoals State: {subgoals_json}\n\n"
                    f"Current focus task: {current_task}\n\n"
                    "Your task:\n"
                    "1. Analyze the scene and current subgoals state\n"
                    "2. Update the completion status of subgoals based on what you observe\n"
                    "3. Focus on the first uncompleted subgoal\n"
                    "4. Only mark a subgoal as complete when you're absolutely sure it's achieved based on visual evidence\n"
                    "5. Include the updated subgoal states in your response using the 'subgoal_states' field\n"
                    "6. IMPORTANT Navigation Strategy:\n"
                    "   IF YOU CAN SEE THE TARGET:\n"
                    "   - Use EXACTLY the same language as in the subgoal list\n"
                    "   - Just add 'Point to the free area near/at/between' in front\n"
                    "   - Example: 'Point to the free area near vase on the cabinet'\n\n"
                    "   IF TARGET IS NOT VISIBLE:\n"
                    "   - Look for promising paths or openings that might lead to the target\n"
                    "   - Navigate based on visible landmarks and spatial layout\n"
                    "   - Example: For 'vase in bedroom' but no bedroom visible:\n"
                    "     → 'Point to the free area near the hallway entrance'\n"
                    "   - Example: For 'TV' but not in view:\n"
                    "     → 'Point to the free area near the living room opening'\n\n"
                    "   ALWAYS explain your navigation strategy in the reasoning field"
                )
                prompt_parts.extend([subgoal_status])

        # First show the full panoramic view
        prompt_parts.extend([
            "First, observe the full panoramic view to understand the complete environment:",
            panoramic_image,
            "\nNow, let's examine each section in detail. Here are the three detailed views (left, center, right) for precise navigation:",
            "Left view:", img_left,
            "Center view:", img_center,
            "Right view:", img_right,
        ])

        if reprompt:
            prompt_parts.insert(0, f"IMPORTANT: {reprompt}")

        try:
            logging.info("VLM Planner: Sending prompt with 3 images to Gemini...")
            response = self.chat.send_message(prompt_parts)
            logging.info("VLM Planner: Received raw response.")
            logging.debug(f"Raw VLM response text: {response.text}")
            response_model = VLMResponse.model_validate(clean_and_parse_json(response.text))
            
            # For instruction tasks, update subgoal states from VLM response
            if self.is_instruction_task and response_model.subgoal_states:
                # Log state before update
                self._log_subgoal_state("Before updating from VLM")
                
                # Update our subgoal states from VLM's assessment
                for i, new_state in enumerate(response_model.subgoal_states):
                    if i < len(self.subgoals):
                        self.subgoals[i].completed = new_state.completed
                
                # Log updated state
                self._log_subgoal_state("After updating from VLM")
                
                # Check if all subgoals are complete
                if all(sg.completed for sg in self.subgoals):
                    response_model.type = "end"
                    response_model.reasoning = "Mission complete: All subgoals achieved"

                # Log final state
                self._log_subgoal_state("After processing response")
            
            logging.info(f"Parsed response: {response_model.type}, Division: {response_model.image_division}, Reasoning: {response_model.reasoning}")
            if self.is_instruction_task and response_model.subgoal_states:
                # Print current status of all subgoals
                print("\n=== Current Task Status ===")
                for i, subgoal in enumerate(response_model.subgoal_states, 1):
                    status = "✓" if subgoal.completed else "□"
                    current = " (CURRENT)" if not subgoal.completed else ""
                    print(f"{status} {i}. {subgoal.description}{current}")
                print("=======================\n")
            
            return response_model

        except Exception as e:
            logging.error(f"VLM call or parsing failed: {e}")
            return None



    def _log_subgoal_state(self, context: str):
        """Helper to log the current state of all subgoals."""
        print(f"\n=== Subgoal State: {context} ===")
        print(f"Total subgoals: {len(self.subgoals)}")
        for i, subgoal in enumerate(self.subgoals, 1):
            status = "✓" if subgoal.completed else "□"
            current = " (CURRENT)" if not subgoal.completed else ""
            print(f"{status} {i}. {subgoal.description}{current}")
        print("=" * (20 + len(context)) + "\n")

    def find_target_in_list(self, question: str, object_list: List[str]) -> Optional[FoundObjectResponse]:
        """
        Asks the VLM to identify the primary target from a question in a list of objects.
        Returns both a boolean for presence and the object's name if found.
        """
        logging.info(f"VLM Planner: Finding target for '{question}' in list: {object_list}")
        prompt = f"""
        You are a helpful reasoning assistant. Your task is to identify if the primary target object from a user's question exists within a given list of objects.

        User's question: "{question}"
        List of objects detected nearby: {object_list}

        First, determine the primary object the user is asking to find. Secondary objects used for location context (e.g., "the book *on the table*") should not be the target.
        Then, check if this primary target is in the provided list.

        Respond ONLY with a single JSON object in this exact format.
        If the primary target is in the list, `is_present` must be true and `target_name` must be the object's name from the list.
        If the primary target is NOT in the list, `is_present` must be false and `target_name` must be null.

        {{
            "is_present": <true or false>,
            "target_name": "<exact_object_name_from_the_list_if_present_else_null>",
            "reasoning": "<brief explanation of your decision>"
        }}
        """
        try:
            response = self.chat.send_message(prompt)
            logging.info("VLM Planner: Received find target response.")
            return FoundObjectResponse.model_validate(clean_and_parse_json(response.text))
        except Exception as e:
            logging.error(f"VLM find target call or parsing failed: {e}")
            return None