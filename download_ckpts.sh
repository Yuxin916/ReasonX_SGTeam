#!/bin/bash
# One-shot script to download RoboRefer and DepthAnything checkpoints
set -e

# Save the original directory
ORIG_DIR="$(pwd)"

# 1. Create checkpoints directory
mkdir -p ai_module/src/RoboRefer/ckpts
cd ai_module/src/RoboRefer/ckpts

# 2. Install git-lfs if not already installed
if ! command -v git-lfs &> /dev/null; then
    echo "git-lfs not found. Please install git-lfs manually."
    exit 1
fi
git lfs install

# 3. Clone RoboRefer-8B-SFT weights
if [ ! -d "RoboRefer-8B-SFT" ]; then
    git clone https://huggingface.co/Zhoues/RoboRefer-8B-SFT
else
    echo "RoboRefer-8B-SFT already exists. Skipping clone."
fi

# 4. Download Depth Anything V2 Large checkpoint
DEPTH_CKPT="depth_anything_v2_vitl.pth"
if [ ! -f "$DEPTH_CKPT" ]; then
    wget -O $DEPTH_CKPT "https://huggingface.co/depth-anything/Depth-Anything-V2-Large/resolve/main/depth_anything_v2_vitl.pth?download=true"
else
    echo "$DEPTH_CKPT already exists. Skipping download."
fi

# Return to the original directory
cd "$ORIG_DIR"
echo "All checkpoints downloaded successfully."
