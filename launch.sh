#!/bin/bash

# launch.sh - Script to start the VLN system

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting VLN System...${NC}"

# 1. Source the setup file
echo -e "${YELLOW}Step 1: Sourcing ai_module/devel/setup.bash${NC}"
source ai_module/devel/setup.bash
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Setup sourced successfully${NC}"
else
    echo -e "${RED}✗ Failed to source setup file${NC}"
    exit 1
fi

# 2. Launch ROS node in background
echo -e "${YELLOW}Step 2: Launching ROS VLN agent${NC}"
roslaunch vln_module vln_agent.launch &
ROS_PID=$!

# Wait a bit for ROS to start up
sleep 3

# 3. Start the VLM server
echo -e "${YELLOW}Step 3: Starting VLM server${NC}"

# Initialize conda and activate rosenv environment
eval "$(/opt/conda/bin/conda shell.bash hook)"
conda activate rosenv

python ai_module/src/vln_module/src/vln_module/utils/vlm_server.py &
VLM_PID=$!

echo -e "${GREEN}All processes started:${NC}"
echo -e "  ROS Launch PID: $ROS_PID"
echo -e "  VLM Server PID: $VLM_PID"
echo -e "${YELLOW}Press Ctrl+C to stop all processes${NC}"

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Stopping all processes...${NC}"
    kill $VLM_PID 2>/dev/null
    kill $ROS_PID 2>/dev/null
    echo -e "${GREEN}All processes stopped${NC}"
    exit 0
}

# Trap Ctrl+C and cleanup
trap cleanup INT

# Wait for processes
wait