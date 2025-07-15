import os
import io
import base64
from flask import Flask, request, jsonify
from PIL import Image as PILImage

# Import your existing VLMPlanner class (I've copied it here for completeness)
from vlm_planner import VLMPlanner, VLMResponse 

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
    # THIS LINE IS CRITICAL: It tells the planner to start a new conversation.
    vlm_planner.start_new_mission(question)
    
    return jsonify({"status": "success", "message": f"New mission started for question: {question}"})


@app.route('/get_next_action', methods=['POST'])
def get_next_action():
    """
    Endpoint for the main Reason-Act loop.
    Expects JSON: {"image": "base64-encoded-string"}
    """
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({"error": "Missing 'image' data in request body"}), 400

    try:
        # Decode the Base64 image string back into a PIL Image
        base64_image_str = data['image']
        image_bytes = base64.b64decode(base64_image_str)
        image_stream = io.BytesIO(image_bytes)
        panoramic_image = PILImage.open(image_stream)
    except Exception as e:
        return jsonify({"error": f"Failed to decode image: {str(e)}"}), 400

    # Call the VLM planner to get the next action
    action_response = vlm_planner.get_vlm_response(panoramic_image)
    
    if action_response:
        # Use Pydantic's .model_dump() to convert the response object to a dictionary
        return jsonify(action_response.model_dump())
    else:
        return jsonify({"error": "VLM Handler failed to produce a response"}), 500

# --- 3. Run the Server ---
if __name__ == '__main__':
    # Make sure your GOOGLE_API_KEY is set as an environment variable before running
    if not os.getenv("GOOGLE_API_KEY"):
        print("\nERROR: Please set the GOOGLE_API_KEY environment variable first.")
        print("Example: export GOOGLE_API_KEY='your_key_here'\n")
        exit()
    app.run(host='0.0.0.0', port=5000, debug=True)