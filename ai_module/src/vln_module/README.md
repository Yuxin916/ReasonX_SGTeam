# VLN Module README

This guide explains how to set up and run the VLN (Vision-and-Language Navigation) module.

## Setup Instructions

1. **Re-compose the image and enter the image**  
    Make sure your environment is ready.

2. **Launch the system**  
    Open a terminal and run:
    ```bash
    ./launch_system.sh
    ```
    Ensure there are no errors.

3. **Build and source the workspace, launch the vln nodes**  
    In a second terminal:
    ```bash
    cd ai_module/
    catkin_make
    source devel/setup.bash
    export GOOGLE_API_KEY="your_key"
    roslaunch vln_module vln_agent.launch
    ```

4. **Start the VLM server**  
    In another terminal:
    ```bash
    python3.9 src/vln_module/src/vln_module/utils/vlm_server.py
    ```

5. **Start the Roborefer server**
    Please refer to https://github.com/Zhoues/RoboRefer/tree/main for reference to 1. set up environment 2. download checkpoints and 3. start the server 
    ```bash
    python api.py \
    --port 25547 \
    --depth_model_path /your/custom/path/depth_anything_v2_vitl.pth \
    --vlm_model_path /your/custom/path/to/roborefer
    ```

6. **Publish a challenge question**  
    In another terminal, publish a question to the ROS topic. Example:
    ```bash
    rostopic pub -1 /challenge_question std_msgs/String "navigate to the teal pillow on the sofa farthest from the window"
    ```

7. **Visualize the pixel goal in RViz**  
    In RViz, add the image topic `image_annotated` to see the VLM pixel goal visualized.

## Notes

- Replace `"your_key"` with your actual Google API key.
