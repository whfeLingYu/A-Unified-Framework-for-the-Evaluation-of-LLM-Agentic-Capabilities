"""
Example usage of DockerOSEnvironment

This script demonstrates how to use the DockerOSEnvironment class
to create a real OS environment for agent evaluation.
"""

import logging
from pathlib import Path
from DockerOSEnvironment import DockerOSEnvironment, DockerOSEnvironmentFactory

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_1_basic_usage():
    """Example 1: Basic usage with context manager"""
    print("\n=== Example 1: Basic Usage ===\n")

    config = {
        "image": "ubuntu:22.04",
        "working_dir": "/root",
        "user": "root",
        "network_mode": "none",  # No network for security
    }

    with DockerOSEnvironment(config, logger=logger) as env:
        # Execute a simple command
        result = env.execute_command("echo 'Hello from Docker!'")
        print(f"Output: {result['stdout']}")

        # Create a file
        env.write_file("/tmp/test.txt", "This is a test file")

        # Read the file
        content = env.get_file_content("/tmp/test.txt")
        print(f"File content: {content}")

        # List directory
        files = env.list_directory("/tmp")
        print(f"Files in /tmp: {files}")


def example_2_from_task_config():
    """Example 2: Initialize from AgentBench task config"""
    print("\n=== Example 2: From Task Config ===\n")

    # Path to an OS task JSON file
    task_config_path = Path(__file__).parent / "AgentBench" / "os_interaction" / "os_task_0.json"

    if not task_config_path.exists():
        print(f"Task config not found: {task_config_path}")
        print("Using minimal environment instead")

        env = DockerOSEnvironmentFactory.create_minimal()
    else:
        env = DockerOSEnvironmentFactory.create_from_task_config(
            str(task_config_path),
            image="ubuntu:22.04"
        )

    try:
        # The filesystem from the JSON is now real!
        result = env.execute_command("ls -la /usr/stock.log", check=False)
        if result['exit_code'] == 0:
            print("stock.log exists!")
            print(f"First 5 lines:")
            head_result = env.execute_command("head -5 /usr/stock.log")
            print(head_result['stdout'])
        else:
            print("stock.log not found (expected if task config doesn't exist)")

        # Execute the task command
        result = env.execute_command(
            "grep 'Alice | Sell' /usr/stock.log | wc -l",
            check=False
        )
        if result['exit_code'] == 0:
            print(f"\nNumber of times Alice sold stock: {result['stdout'].strip()}")

    finally:
        env.cleanup()


def example_3_with_resource_limits():
    """Example 3: Environment with resource limits"""
    print("\n=== Example 3: With Resource Limits ===\n")

    config = {
        "image": "ubuntu:22.04",
        "working_dir": "/home/alice",
        "user": "alice",
        "memory_limit": "256m",  # Limit to 256MB RAM
        "cpu_quota": 50000,  # Limit to 50% CPU
        "network_mode": "none",  # No network access
    }

    env = DockerOSEnvironment(config, logger=logger)
    env.initialize()

    try:
        # Run as alice user
        result = env.execute_command("whoami")
        print(f"Current user: {result['stdout'].strip()}")

        # Check memory limit (requires /proc)
        result = env.execute_command(
            "cat /sys/fs/cgroup/memory/memory.limit_in_bytes",
            check=False
        )
        if result['exit_code'] == 0:
            limit_bytes = int(result['stdout'].strip())
            limit_mb = limit_bytes / (1024 * 1024)
            print(f"Memory limit: {limit_mb:.0f} MB")

        # Get environment state
        state = env.get_current_state()
        print(f"\nEnvironment state: {state}")

    finally:
        env.cleanup()


def example_4_batch_commands():
    """Example 4: Running batch commands (like a real agent)"""
    print("\n=== Example 4: Batch Commands ===\n")

    with DockerOSEnvironment({"image": "ubuntu:22.04"}, logger=logger) as env:
        # Simulate an agent solving a task
        commands = [
            "mkdir -p /tmp/workspace",
            "echo 'data1' > /tmp/workspace/file1.txt",
            "echo 'data2' > /tmp/workspace/file2.txt",
            "echo 'data3' > /tmp/workspace/file3.txt",
            "ls -l /tmp/workspace",
            "cat /tmp/workspace/file*.txt | wc -l",
        ]

        for cmd in commands:
            print(f"\nExecuting: {cmd}")
            result = env.execute_command(cmd)
            if result.get('stdout'):
                print(f"Output: {result['stdout']}")


def example_5_error_handling():
    """Example 5: Error handling"""
    print("\n=== Example 5: Error Handling ===\n")

    with DockerOSEnvironment({"image": "ubuntu:22.04"}, logger=logger) as env:
        # This will succeed
        result = env.execute_command("echo 'success'")
        print(f"Success: {result['stdout']}")

        # This will fail but not raise exception (check=False)
        result = env.execute_command("cat /nonexistent/file", check=False)
        print(f"Failed command exit code: {result['exit_code']}")
        print(f"Error message: {result.get('stderr', 'N/A')}")

        # This would raise an exception (check=True, default)
        try:
            env.execute_command("cat /nonexistent/file")
        except Exception as e:
            print(f"Exception caught: {type(e).__name__}")


if __name__ == "__main__":
    print("DockerOSEnvironment Examples")
    print("=" * 50)

    # Run examples
    try:
        example_1_basic_usage()
        example_2_from_task_config()
        example_3_with_resource_limits()
        example_4_batch_commands()
        example_5_error_handling()

        print("\n" + "=" * 50)
        print("All examples completed!")

    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
