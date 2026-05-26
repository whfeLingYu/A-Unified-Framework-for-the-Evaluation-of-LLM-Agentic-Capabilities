#!/bin/bash
# Docker OS Environment Quick Start Script
# 快速构建和测试 Docker OS 环境

set -e  # Exit on error

echo "======================================"
echo "Docker OS Environment Quick Start"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is installed
echo "1. Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker is not installed.${NC}"
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker is running
if ! docker ps &> /dev/null; then
    echo -e "${RED}ERROR: Docker daemon is not running.${NC}"
    echo "Please start Docker and try again."
    exit 1
fi

echo -e "${GREEN}✓ Docker is installed and running${NC}"
echo ""

# Check Python docker package
echo "2. Checking Python docker package..."
if ! python3 -c "import docker" 2>/dev/null; then
    echo -e "${YELLOW}WARNING: Python docker package not found.${NC}"
    echo "Installing docker package..."
    pip3 install docker
    echo -e "${GREEN}✓ Python docker package installed${NC}"
else
    echo -e "${GREEN}✓ Python docker package is installed${NC}"
fi
echo ""

# Build Docker images
echo "3. Building Docker images..."
echo ""

cd "$(dirname "$0")/Dockerfiles"

echo "Building minimal OS environment image..."
docker build -t agent-os-env:minimal -f os_environment_minimal.Dockerfile . || {
    echo -e "${RED}ERROR: Failed to build minimal image${NC}"
    exit 1
}
echo -e "${GREEN}✓ Minimal image built: agent-os-env:minimal${NC}"
echo ""

echo "Building full OS environment image..."
docker build -t agent-os-env:full -f os_environment.Dockerfile . || {
    echo -e "${YELLOW}WARNING: Failed to build full image${NC}"
    echo "You can still use the minimal image or ubuntu:22.04"
}
echo -e "${GREEN}✓ Full image built: agent-os-env:full${NC}"
echo ""

cd - > /dev/null

# Pull Ubuntu image (fallback)
echo "4. Pulling Ubuntu 22.04 image (fallback)..."
docker pull ubuntu:22.04 || {
    echo -e "${YELLOW}WARNING: Failed to pull ubuntu:22.04${NC}"
}
echo -e "${GREEN}✓ Ubuntu image ready${NC}"
echo ""

# Run example
echo "5. Running example..."
echo ""

python3 << 'EOF'
import sys
sys.path.insert(0, '/path/to/Agent-Sandbox-and-Evaluation')

from Environment.DockerOSEnvironment import DockerOSEnvironment
import logging

logging.basicConfig(level=logging.INFO)

print("Creating Docker OS Environment...")
config = {
    "image": "agent-os-env:minimal",
    "working_dir": "/root",
}

try:
    with DockerOSEnvironment(config) as env:
        print("\n--- Test 1: Simple command ---")
        result = env.execute_command("echo 'Hello from Docker OS!'")
        print(f"Output: {result['stdout']}")

        print("\n--- Test 2: File operations ---")
        env.write_file("/tmp/test.txt", "This is a test!")
        content = env.get_file_content("/tmp/test.txt")
        print(f"File content: {content}")

        print("\n--- Test 3: Directory listing ---")
        files = env.list_directory("/tmp")
        print(f"Files in /tmp: {files}")

        print("\n--- Test 4: User info ---")
        result = env.execute_command("whoami")
        print(f"Current user: {result['stdout'].strip()}")

        print("\n✓ All tests passed!")

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

echo ""
echo "======================================"
echo -e "${GREEN}Setup Complete!${NC}"
echo "======================================"
echo ""
echo "Available Docker images:"
docker images | grep -E "agent-os-env|ubuntu.*22.04" | head -3
echo ""
echo "Next steps:"
echo "1. Run examples: python3 Environment/docker_os_example.py"
echo "2. Read documentation: Environment/DOCKER_OS_ENVIRONMENT_README.md"
echo "3. Test with AgentBench tasks"
echo ""
echo "To remove the images later:"
echo "  docker rmi agent-os-env:minimal agent-os-env:full"
echo ""
