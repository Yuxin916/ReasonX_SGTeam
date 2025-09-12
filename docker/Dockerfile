FROM ros:noetic-ros-core-focal

# === [1] Remove ALL ROS source lists BEFORE apt update ===
RUN rm -f /etc/apt/sources.list.d/ros* || true

# === [2] Run apt update safely, install gpg tools and curl ===
RUN apt-get update -o Dir::Etc::sourcelist="sources.list" \
                   -o Dir::Etc::sourceparts="-" \
                   -o APT::Get::List-Cleanup="0" && \
    apt-get install --no-install-recommends -y curl gnupg2 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# === [3] Re-add the valid ROS key and source list ===
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | \
    gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros/ubuntu focal main" > /etc/apt/sources.list.d/ros1.list

# === [4] Install bootstrap ROS tools ===
RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    python3-rosdep \
    python3-rosinstall \
    python3-vcstools \
    && rm -rf /var/lib/apt/lists/*

# === [5] Install ROS core packages ===
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3-netifaces \
        ros-noetic-ros-base=1.5.0-1* \
        ros-noetic-cv-bridge \
        ros-noetic-tf \
    && rm -rf /var/lib/apt/lists/*

# === [6] Install Miniconda ===
ENV CONDA_DIR=/opt/conda
ENV PATH=$CONDA_DIR/bin:$PATH
RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh && \
    bash /tmp/miniconda.sh -b -p $CONDA_DIR && \
    rm /tmp/miniconda.sh && \
    $CONDA_DIR/bin/conda clean -afy

RUN conda config --set always_yes yes --set changeps1 no && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r


# === [7] Create Python 3.9 env for GenAI work ===
RUN conda create -y -n rosenv python=3.9 && \
    conda clean -afy && \
    echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc && \
    echo "conda activate rosenv" >> ~/.bashrc

# === [Init Conda for bash and auto-activate rosenv] ===
RUN /opt/conda/bin/conda init bash && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate rosenv" >> ~/.bashrc && \
    echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc

# === [8] Install Python deps in rosenv ===
RUN /bin/bash -c "source activate rosenv && \
    pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir google-genai flask pillow requests"

# === [8.1] Install Python deps for system Python (for ROS nodes) ===
RUN /usr/bin/python3 -m pip install requests pillow flask

# === [9] Bootstrap rosdep ===
RUN rosdep init && \
    rosdep update --rosdistro $ROS_DISTRO
