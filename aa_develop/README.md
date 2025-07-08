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
docker exec -it ubuntu20_ros bash

./launch_module.sh
```

# AI Navigation Policy (Python-based dummy VLM policy)
```
docker exec -it ubuntu20_ros bash

./launch_module.sh
```