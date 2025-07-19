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

# bootstrap rosdep
RUN rosdep init && \
    rosdep update --rosdistro $ROS_DISTRO

# install ros packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-noetic-ros-base=1.5.0-1* \
    ros-noetic-tf \
    python3-opencv \
    python3-scipy \
    ros-noetic-cv-bridge \
    ros-noetic-image-transport \
    ros-noetic-rqt \
    ros-noetic-rqt-common-plugins \
    ros-noetic-pcl-ros \
    && rm -rf /var/lib/apt/lists/*

# Source ROS
RUN echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc
