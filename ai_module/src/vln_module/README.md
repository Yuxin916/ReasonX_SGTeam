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
    conda activate rosenv
    python src/vln_module/src/vln_module/utils/vlm_server.py
    ```

5. **Start the Roborefer server**  
    Please refer to https://github.com/Zhoues/RoboRefer/tree/main for reference to:
    1. Set up environment: `bash env_setup.sh roborefer`
    2. Download checkpoints
    3. Start the server
    
    ```bash
    conda activate roborefer
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

    ### Known Issues and Solutions
    - **Missing Docker dependencies**: The dockerfile is incomplete and missing libraries like `pillow` and `requests`, which will cause errors when launching `vln_agent`. 
        - **Solution**: Install the missing libraries when errors occur.
    - **Conda initialization error**: May occur when entering the Docker container for the first time.
        - **Solution**: Follow standard conda initialization procedures.

    ### Python Environment Requirements
    - **ROS-related Python**: Runs in Python 3.8
    - **VLM server** (`vlm_server.py`): Runs in Python 3.9 (in the "rosenv" conda environment)
    - **RoboRefer module**: Requires conda environment with Python 3.10 (follow the Roborefer repo instruction)

    ### Tested Commands
    The following commands have been verified to run without errors:
    ```bash
    roslaunch vln_module vln_agent.launch
    python src/vln_module/src/vln_module/utils/vlm_server.py
    ```

    ### Configuration
    - Replace `"your_key"` with your actual Google API key in step 3.
