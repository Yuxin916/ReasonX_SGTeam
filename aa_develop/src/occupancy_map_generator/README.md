## Note

Self implementation of occupancy grid mapping algorithm.

Subcribing to `/registered_scan`, `/state_estimation` and `/tf (map to sensor)` topics, publishing to `/map` topic.

Currently suffering from low updating frequency with following error:

```bash
root@ZHRDesktop:/home/eric/ReasonX_SGTeam/aa_develop# roslaunch occupancy_map_generator occupancy_map_generator.launch
... logging to /root/.ros/log/0cb9ca4a-62f3-11f0-84fe-00155d596c38/roslaunch-ZHRDesktop-1953.log
Checking log directory for disk usage. This may take a while.
Press Ctrl-C to interrupt
Done checking log file disk usage. Usage is <1GB.

started roslaunch server http://ZHRDesktop:33783/

SUMMARY
========

PARAMETERS
 * /occupancyGridGenerator/map_center_x: -50.0
 * /occupancyGridGenerator/map_center_y: -50.0
 * /occupancyGridGenerator/map_frame: map
 * /occupancyGridGenerator/map_publish_freq: 0.2
 * /occupancyGridGenerator/map_resolution: 0.1
 * /occupancyGridGenerator/map_size_x: 60.0
 * /occupancyGridGenerator/map_size_y: 60.0
 * /occupancyGridGenerator/robot_frame: sensor
 * /occupancyGridGenerator/sensor_model_p_free: 0.45
 * /occupancyGridGenerator/sensor_model_p_occ: 0.75
 * /occupancyGridGenerator/sensor_model_p_prior: 0.5
 * /occupancyGridGenerator/update_movement: 0.05
 * /rosdistro: noetic
 * /rosversion: 1.17.4

NODES
  /
    occupancyGridGenerator (occupancy_map_generator/occupancy_map_generator.py)

ROS_MASTER_URI=http://localhost:11311

process[occupancyGridGenerator-1]: started with pid [1961]
[ERROR] [1752745680.479520]: Lookup would require extrapolation 0.379911899s into the past.  Requested time 1752745679.134298325 but the earliest data is at time 1752745679.514210224, when looking up transform from frame [sensor] to frame [map]
[INFO] [1752745685.162567]: Published map!
/home/eric/ReasonX_SGTeam/aa_develop/src/occupancy_map_generator/scripts/occupancy_map_generator.py:14: RuntimeWarning: overflow encountered in exp
  return 1 - (1 / (1 + np.exp(l)))
[ERROR] [1752745698.314477]: Lookup would require extrapolation 1.530471086s into the past.  Requested time 1752745686.778939724 but the earliest data is at time 1752745688.309410810, when looking up transform from frame [sensor] to frame [map]
[ERROR] [1752745698.316126]: Lookup would require extrapolation 0.285150528s into the past.  Requested time 1752745688.029411793 but the earliest data is at time 1752745688.314562321, when looking up transform from frame [sensor] to frame [map]
[WARN] [1752745698.244216]: Detected jump back in time of 0.487433s. Clearing TF buffer.
[WARN] [1752745697.831330]: Detected jump back in time of 0.571205s. Clearing TF buffer.
[ERROR] [1752745700.413961]: Lookup would require extrapolation 7.371130943s into the past.  Requested time 1752745690.459419012 but the earliest data is at time 1752745697.830549955, when looking up transform from frame [sensor] to frame [map]
[ERROR] [1752745700.415735]: Lookup would require extrapolation 6.226050377s into the past.  Requested time 1752745691.604499578 but the earliest data is at time 1752745697.830549955, when looking up transform from frame [sensor] to frame [map]
[ERROR] [1752745700.416588]: Lookup would require extrapolation 4.865991830s into the past.  Requested time 1752745692.964558125 but the earliest data is at time 1752745697.830549955, when looking up transform from frame [sensor] to frame [map]
```

Presumably due to the synchronization issue between tf frame and registered scan.

## TODO

- [ ] Consider existing SLAM package (like Gmapping)
    - [ ] Gmapping only takes LaserScan as input, need to convert PointCloud2 to LaserScan?