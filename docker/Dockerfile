FROM ros:noetic-ros-core-focal

# === [1] Remove ALL ROS source lists BEFORE apt update ===
RUN rm -f /etc/apt/sources.list.d/ros* || true

# === [2] Run apt update safely, install gpg tools and curl ===
RUN apt-get update -o Dir::Etc::sourcelist="sources.list" \
                   -o Dir::Etc::sourceparts="-" \
                   -o APT::Get::List-Cleanup="0" && \
    apt-get install --no-install-recommends -y curl gnupg2 ca-certificates

# === [3] Re-add the valid ROS key and source list ===
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | \
    gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros/ubuntu focal main" > /etc/apt/sources.list.d/ros1.list

# install bootstrap tools
RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    python3-rosdep \
    python3-rosinstall \
    python3-vcstools \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get install -y --no-install-recommends python3.9 python3.9-distutils && \
    # Install pip specifically for python3.9
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.9 && \
    rm -rf /var/lib/apt/lists/*

# === Install ROS packages and Python dependencies for ROS ===
# We now install `python3-netifaces` via apt. This is the key change.
# `apt` will install it for the system's default Python 3.8, which is what roslaunch needs.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        python3-pip \
        python3-rosdep \
        python3-rosinstall \
        python3-vcstools \
        python3-netifaces \
        ros-noetic-ros-base=1.5.0-1* \
        ros-noetic-cv-bridge \
        ros-noetic-tf \
    && rm -rf /var/lib/apt/lists/*

# === Install Python packages specifically for Python 3.9 ===
# Use `python3.9 -m pip` to ensure these are installed for the newer interpreter.
# We add `rospy` here so that Python 3.9 scripts can act as ROS nodes.
RUN python3.9 -m pip install --no-cache-dir --upgrade pip
RUN python3.9 -m pip install --no-cache-dir -q -U google-genai flask pillow

RUN python3 -m pip install --no-cache-dir flask pillow requests
    
# bootstrap rosdep
RUN rosdep init && \
  rosdep update --rosdistro $ROS_DISTRO

# install ros packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-noetic-ros-base=1.5.0-1* \
    && rm -rf /var/lib/apt/lists/*

# Source ROS
RUN echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc
