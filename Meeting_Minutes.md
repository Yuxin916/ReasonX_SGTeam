### Meeting Minutes (July 13th, 2025)
- [ ] Yuxin: 
  - [ ] For Q4 and Q5 (VLN), tune the waypoint space in GT trajectory
  - [ ] Parse pdf questions and answers, store in `questions.json` 
  - [ ] Train an end-to-end baseline model for VLN (Q4 and Q5) waypoint prediction

- [ ] Chen Jie:
  - [ ] PixelNav transfer to current workspace
  - [ ] Q2 and Q3 object refer segmentation. Not focus on where to search for objects, 
  but focus on how to segment the objects in the scene (whether use ground truth bounding box or not)

- [ ] Haoruo:
  - [ ] Be familiar with 3D-Mem codebase 
  - [ ] Base on the scene provided, real-time construct Occupancy map (Traverse map) and visualize in RViz
    - [ ] After some learning about grid map, a self implemented module `occupancy_map_generator` was created with some serious bugs
    - [ ] Browsed through some popular SLAM algorithms (such as Gmapping), but they relies on `sensor_msg/LaserScan` messages, which is not available in our case. Theoretically `sensor_msg/PointCloud2` can be converted, but they will lose many information.
    - [ ] The (`pointcloud_to_grid`)[https://github.com/jkk-research/pointcloud_to_grid/tree/ros1] package was used to convert point cloud to grid map.
  - [ ] Given semantic view at every time step, construct the scene graph along the trajectory (object list)
    - [ ] After browing thourh 3D mem's repo, they are using the package (concept graphs)[https://github.com/concept-graphs/concept-graphs] to manage the detected objects. The code for object detection is in file `/3D-Mem/src/conceptgraph/slam/r3d_stream_rerun_realtime_mapping.py` line 267-375. Still working on to fully understand it for porting.
  - [ ] Optional: Yolo object detection and semantic segmentation, SAM2 (if time allows)

