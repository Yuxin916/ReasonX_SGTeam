# VLN Module README

This guide explains how to set up and run the **VLN (Vision-and-Language Navigation)** module for the CMU VLA Challenge system.

## Overview

The VLN module integrates vision-language models with ROS navigation to enable robots to understand natural language instructions and navigate to specified objects in indoor environments.

## Prerequisites

- Docker with GPU support
- NVIDIA drivers properly installed
- At least 8GB GPU memory recommended

## Setup Instructions

### 1. Pull Docker Image and Start Containers

```bash
# Pull the base image
docker pull xerneaschen/docker-ubuntu20_ros:latest

# Navigate to docker directory and start containers
cd docker
docker compose -f compose_gpu.yml up --build -d
```

**Verify**: Ensure all containers are running without errors.

### 2. Launch the System

#### System Container (Simulator)
```bash
docker exec -it ubuntu20_ros_system bash
./launch_system.sh
```

#### AI Module Container (Navigation Agent)
```bash
docker exec -it ubuntu20_ros bash
./launch.sh
```

**Note**: The `launch.sh` script automatically handles:
- ROS environment setup
- VLM server initialization  
- RoboRefer API server startup
- All necessary conda environments

<!-- 3. **Build and source the workspace, launch the vln nodes**  
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
    ``` -->

### 3. Send Navigation Commands

Once the system is running, you can send navigation instructions via ROS topics:

```bash
# Example navigation commands
rostopic pub -1 /challenge_question std_msgs/String "navigate to the teal pillow on the sofa farthest from the window"
rostopic pub -1 /challenge_question std_msgs/String "go to the red book on the table"
rostopic pub -1 /challenge_question std_msgs/String "find the coffee mug near the kitchen counter"
```

### 4. Visualization and Monitoring

#### RViz Visualization
Launch RViz to monitor the navigation process:
```bash
# In the AI container
rosrun rviz rviz
```

**Add these topics in RViz:**
- `/image_annotated` - Shows VLM pixel targets with visual markers
- `/way_point_with_heading` - Displays computed waypoints
- `/visualization_marker_array` - Shows detected objects and navigation markers

#### Monitoring Logs
Monitor system performance through ROS logs:
```bash
# Monitor challenge agent activity
rostopic echo /challenge_question

# Check navigation decisions
rostopic echo /way_point_with_heading

# View detected objects
rostopic echo /vlm_pixel_input
```

## System Architecture

### Key Components

1. **Challenge Agent Node** (`challenge_agent_node.py`)
   - Main navigation controller
   - Processes natural language instructions
   - Coordinates VLM and RoboRefer services
   - Handles multi-object resolution and exploration fallbacks

2. **VLM Planner** (`vlm_planner.py`)
   - Interfaces with Google Gemini API
   - Processes panoramic images and text instructions
   - Returns structured navigation decisions

3. **Pixel to Waypoint Node** (`pixel_to_waypoint_node.py`)
   - Converts 2D pixel coordinates to 3D waypoints
   - Handles camera projection and coordinate transformations
   - Includes robust ray adjustment for edge cases

4. **RoboRefer Integration**
   - Provides object grounding and localization
   - Resolves multiple object instances
   - Runs on dedicated conda environment

### Data Flow

```
Natural Language Instruction → Challenge Agent → VLM Processing → 
Object Detection → Pixel Coordinate → 3D Waypoint → Navigation Action
```

## Troubleshooting

### Common Issues

**"ModuleNotFoundError: No module named 'llava'"**
- The RoboRefer environment setup may be incomplete
- Try rebuilding the roborefer conda environment:
  ```bash
  cd ai_module/src/RoboRefer
  ./env_setup.sh roborefer
  ```

**Navigation failures or timeouts**
- Check network connectivity to external APIs (Gemini, RoboRefer)
- Verify all ROS nodes are running: `rosnode list`
- Monitor topic activity: `rostopic list`

**Image processing errors**
- Ensure camera topics are publishing: `rostopic echo /camera/image`
- Check image dimensions match expected panoramic format (1920x640)

### Performance Tips

- Ensure adequate GPU memory (8GB+ recommended)
- Use SSD storage for faster model loading
- Monitor system resources during operation
- Consider reducing image resolution for faster processing on limited hardware

## Configuration

### Environment Variables
```bash
export GOOGLE_API_KEY="your_gemini_api_key_here"
export ROBOREFER_SERVER_URL="100.94.98.59:25547"  # Or your server address
```

### Model Paths
Update paths in launch scripts if using custom model locations:
- RoboRefer VLM model path
- Depth estimation model path
- Custom VLM configurations
    