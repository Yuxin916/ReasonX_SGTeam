## Start the docker 
```
xhost +

# Go inside this folder in terminal.
cd CMU-VLA-Challenge/docker/

# Starting the container with GPU support
docker compose -f compose_gpu.yml up --build -d
```

## System Launch
```
# Access the running containers and launch the unity environment and ROS system
# This will launch the rviz with the Unity environment

docker exec -it ubuntu20_ros_system bash

./launch_system.sh

```
## AI Navigation Policy (Given dummy C++ VLM policy)
```
# new terminal
docker exec -it ubuntu20_ros bash

./launch_module.sh
```

# AI Navigation Policy (Python-based dummy VLM policy)
```
# new terminal
docker exec -it ubuntu20_ros bash
apt update
apt install -y python3-opencv
apt install -y ros-noetic-cv-bridge
export PYTHONPATH=$PYTHONPATH:./aa_develop/src/dummy_vlm_python/
./launch_py_module.sh

# new terminal
rostopic pub /challenge_question std_msgs/String "data: 'how many sofa'"
# or
rostopic pub /challenge_question std_msgs/String "data: 'find chairs'"
# or
rostopic pub /challenge_question std_msgs/String "data: 'Go straight and turn left at the sofa'"
```

### TODO: 
- [x] Example of navigate to a waypoint and visualize in RViz
- [ ] Re-organize the interface for question answering ([questions.json](../questions/questions.json))
  - [ ] How to parse the numerical answers? (seems in pdf there are ground truth answers)
  - [ ] How to output the bounding box for the objects?
  - [ ] What is the [trajectory_q4.ply](../questions/studio/trajectory_q4.ply) given for Q4 and Q5? How to visualize this given target trajectory?


