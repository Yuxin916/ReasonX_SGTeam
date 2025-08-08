import os
import io
import base64
from flask import Flask, request, jsonify
from PIL import Image as PILImage

# --- MODIFIED: Import the new FoundObjectResponse model ---
from vlm_planner import VLMPlanner, FoundObjectResponse 

# --- 1. Initialize the Flask App and the VLM Planner ---
# The planner is created once and holds its state (like conversation history)
app = Flask(__name__)
vlm_planner = VLMPlanner()

# --- 2. Define API Endpoints ---

@app.route('/start_mission', methods=['POST'])
def start_mission():
    """Endpoint to start a new mission and initialize the VLM's memory."""
    data = request.get_json()
    if not data or 'question' not in data:
        return jsonify({"error": "Missing 'question' in request body"}), 400
    
    question = data['question']
    vlm_planner.start_new_mission(question)
    
    return jsonify({"status": "success", "message": f"New mission started for question: {question}"})


@app.route('/get_next_action', methods=['POST'])
def get_next_action():
    """
    Endpoint for the main Reason-Act loop.
    Expects JSON: {"image": "base64-encoded-string", "reprompt": "optional-string"}
    """
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({"error": "Missing 'image' data in request body"}), 400

    try:
        base64_image_str = data['image']
        image_bytes = base64.b64decode(base64_image_str)
        image_stream = io.BytesIO(image_bytes)
        panoramic_image = PILImage.open(image_stream)
    except Exception as e:
        return jsonify({"error": f"Failed to decode image: {str(e)}"}), 400

    # --- MODIFIED: Handle the optional 'reprompt' message ---
    # This allows the agent to give feedback to the VLM if it needs to try again.
    reprompt = data.get('reprompt', None)

    # Call the VLM planner with the image and the optional reprompt
    action_response = vlm_planner.get_vlm_response(panoramic_image, reprompt=reprompt)
    
    if action_response:
        return jsonify(action_response.model_dump())
    else:
        return jsonify({"type": "error", "reasoning": "VLM Handler failed to produce a response"}), 500


# --- NEW ENDPOINT for the object reference check ---
@app.route('/find_target', methods=['POST'])
def find_target():
    """
    Receives a question and a list of object names, and uses the VLM planner
    to determine if the target object is in the list.
    """
    data = request.get_json()
    if not data or 'question' not in data or 'object_list' not in data:
        return jsonify({"error": "Missing 'question' or 'object_list' in request"}), 400

    question = data['question']
    object_list = data['object_list']

    # Use the planner's consolidated find_target_in_list method
    result = vlm_planner.find_target_in_list(question, object_list)

    if result:
        # Convert the Pydantic model to a dictionary for the JSON response
        return jsonify(result.model_dump())
    else:
        # Return a failure response in the expected format
        return jsonify({"is_present": False, "reasoning": "VLM Planner failed to produce a result."}), 500


# --- 3. Run the Server ---
if __name__ == '__main__':
    # Make sure your GOOGLE_API_KEY is set as an environment variable before running
    if not os.getenv("GOOGLE_API_KEY"):
        print("\nERROR: Please set the GOOGLE_API_KEY environment variable first.")
        print("Example: export GOOGLE_API_KEY='your_key_here'\n")
        exit()
    app.run(host='0.0.0.0', port=5000, debug=False) # Switched debug to False for stability