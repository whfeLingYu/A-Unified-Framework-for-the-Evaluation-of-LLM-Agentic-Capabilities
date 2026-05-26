"""
Docker-based OS Environment for Agent Evaluation

This module provides a Docker-based OS environment that allows agents to execute
real bash commands and file system operations in an isolated container.

Features:
- Real Linux OS environment in Docker
- File system initialization from JSON configuration
- Command execution via Docker exec
- Automatic container lifecycle management
- Resource cleanup and isolation
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import docker
    from docker.models.containers import Container
    from docker.errors import DockerException, ImageNotFound, ContainerError
except ImportError:
    raise ImportError(
        "Docker support requires the 'docker' package. "
        "Install it with: pip install docker"
    )


class DockerOSEnvironment:
    """
    A Docker-based OS environment for running agent tasks.

    This environment creates a real Linux container where agents can execute
    bash commands, manipulate files, and interact with a real OS.

    Example usage:
        config = {
            "image": "ubuntu:22.04",
            "filesystem_config": "/path/to/os_task_0.json",
            "working_dir": "/home/alice",
            "user": "alice"
        }
        env = DockerOSEnvironment(config)
        result = env.execute_command("ls -la /home/alice")
        env.cleanup()
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Optional[logging.Logger] = None,
        container_name: Optional[str] = None,
    ):
        """
        Initialize the Docker OS Environment.

        Args:
            config: Configuration dictionary with the following keys:
                - image: Docker image to use (default: "ubuntu:22.04")
                - filesystem_config: Path to JSON file with filesystem structure
                - working_dir: Working directory in container (default: "/root")
                - user: User to run commands as (default: "root")
                - memory_limit: Memory limit (e.g., "512m")
                - cpu_quota: CPU quota (e.g., 50000 for 50%)
                - network_mode: Network mode (default: "none" for isolation)
                - auto_remove: Auto-remove container on exit (default: False)
            logger: Optional logger instance
            container_name: Optional container name (auto-generated if None)
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.container_name = container_name or f"os-env-{int(time.time() * 1000)}"

        # Docker configuration
        self.image = config.get("image", "ubuntu:22.04")
        self.filesystem_config_path = config.get("filesystem_config")
        self.working_dir = config.get("working_dir", "/root")
        self.user = config.get("user", "root")
        self.memory_limit = config.get("memory_limit")
        self.cpu_quota = config.get("cpu_quota")
        self.network_mode = config.get("network_mode", "none")
        self.auto_remove = config.get("auto_remove", False)

        # Initialize Docker client
        try:
            self.client = docker.from_env()
            self.logger.info("Docker client initialized successfully")
        except DockerException as e:
            raise RuntimeError(
                f"Failed to connect to Docker daemon. "
                f"Make sure Docker is running. Error: {e}"
            )

        self.container: Optional[Container] = None
        self._is_initialized = False

    def initialize(self) -> None:
        """
        Initialize the Docker container and set up the environment.

        This method:
        1. Pulls the Docker image if needed
        2. Creates and starts the container
        3. Initializes the filesystem from config (if provided)
        4. Sets up users and permissions
        """
        if self._is_initialized:
            self.logger.warning("Environment already initialized")
            return

        # Step 1: Ensure image exists
        self._ensure_image()

        # Step 2: Create and start container
        self._create_container()

        # Step 3: Initialize filesystem from config
        if self.filesystem_config_path:
            self._initialize_filesystem()

        # Step 4: Setup users if needed
        if self.user != "root":
            self._setup_user()

        self._is_initialized = True
        self.logger.info(f"Docker OS Environment initialized: {self.container_name}")

    def _ensure_image(self) -> None:
        """Ensure the Docker image exists, pull if necessary."""
        try:
            self.client.images.get(self.image)
            self.logger.info(f"Docker image '{self.image}' found")
        except ImageNotFound:
            self.logger.info(f"Pulling Docker image '{self.image}'...")
            self.client.images.pull(self.image)
            self.logger.info(f"Docker image '{self.image}' pulled successfully")

    def _create_container(self) -> None:
        """Create and start the Docker container."""
        container_kwargs = {
            "image": self.image,
            "name": self.container_name,
            "detach": True,
            "tty": True,
            "stdin_open": True,
            "working_dir": self.working_dir,
            "network_mode": self.network_mode,
            "auto_remove": self.auto_remove,
            # Keep container running
            "command": "/bin/bash",
        }

        # Add resource limits if specified
        if self.memory_limit:
            container_kwargs["mem_limit"] = self.memory_limit
        if self.cpu_quota:
            container_kwargs["cpu_quota"] = self.cpu_quota

        try:
            self.container = self.client.containers.run(**container_kwargs)
            self.logger.info(f"Container '{self.container_name}' created and started")

            # Wait for container to be ready
            time.sleep(0.5)
            self.container.reload()

            if self.container.status != "running":
                raise RuntimeError(
                    f"Container failed to start. Status: {self.container.status}"
                )
        except Exception as e:
            self.logger.error(f"Failed to create container: {e}")
            raise

    def _initialize_filesystem(self) -> None:
        """
        Initialize the filesystem from a JSON configuration file.

        The JSON file should have a structure like:
        {
            "filesystem": {
                "home": {
                    "type": "directory",
                    "children": {
                        "alice": {
                            "type": "directory",
                            "children": {...}
                        }
                    }
                },
                "usr": {
                    "type": "directory",
                    "children": {
                        "stock.log": {
                            "type": "file",
                            "content": "..."
                        }
                    }
                }
            }
        }
        """
        if not self.filesystem_config_path:
            return

        config_path = Path(self.filesystem_config_path)
        if not config_path.exists():
            self.logger.warning(f"Filesystem config not found: {config_path}")
            return

        self.logger.info(f"Initializing filesystem from: {config_path}")

        with open(config_path, 'r') as f:
            config = json.load(f)

        filesystem = config.get("filesystem", {})
        self._create_filesystem_structure("/", filesystem)

        self.logger.info("Filesystem initialized successfully")

    def _create_filesystem_structure(
        self,
        base_path: str,
        structure: Dict[str, Any]
    ) -> None:
        """
        Recursively create filesystem structure in the container.

        Args:
            base_path: Base path in the container
            structure: Dictionary representing the filesystem structure
        """
        for name, item in structure.items():
            item_path = os.path.join(base_path, name)
            item_type = item.get("type", "directory")

            if item_type == "directory":
                # Create directory
                self.execute_command(f"mkdir -p {item_path}", check=False)

                # Recursively create children
                children = item.get("children", {})
                if children:
                    self._create_filesystem_structure(item_path, children)

            elif item_type == "file":
                # Create file with content
                content = item.get("content", "")

                # Ensure parent directory exists
                parent_dir = os.path.dirname(item_path)
                self.execute_command(f"mkdir -p {parent_dir}", check=False)

                # Write content to file using a temporary file and copy
                self._write_file_to_container(item_path, content)

    def _write_file_to_container(self, container_path: str, content: str) -> None:
        """
        Write content to a file in the container.

        Args:
            container_path: Path to file in container
            content: Content to write
        """
        # Create a temporary file with the content
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        try:
            # Copy file to container
            with open(tmp_file_path, 'rb') as f:
                data = f.read()

            # Use docker cp equivalent - put_archive
            import tarfile
            from io import BytesIO

            tar_stream = BytesIO()
            tar = tarfile.TarFile(fileobj=tar_stream, mode='w')

            # Add file to tar
            tarinfo = tarfile.TarInfo(name=os.path.basename(container_path))
            tarinfo.size = len(data)
            tar.addfile(tarinfo, BytesIO(data))
            tar.close()

            # Put tar into container
            tar_stream.seek(0)
            container_dir = os.path.dirname(container_path)
            if not container_dir:
                container_dir = "/"

            self.container.put_archive(container_dir, tar_stream.read())
        finally:
            # Clean up temporary file
            os.unlink(tmp_file_path)

    def _setup_user(self) -> None:
        """Set up the specified user in the container."""
        if self.user == "root":
            return

        # Check if user exists
        result = self.execute_command(
            f"id -u {self.user}",
            check=False,
            capture_output=True
        )

        if result.get("exit_code", 0) != 0:
            # User doesn't exist, create it
            self.logger.info(f"Creating user '{self.user}'")
            self.execute_command(
                f"useradd -m -s /bin/bash {self.user}",
                check=False
            )

    def execute_command(
        self,
        command: str,
        user: Optional[str] = None,
        working_dir: Optional[str] = None,
        check: bool = True,
        capture_output: bool = True,
        timeout: Optional[int] = 30,
    ) -> Dict[str, Any]:
        """
        Execute a command in the Docker container.

        Args:
            command: Shell command to execute
            user: User to run command as (default: self.user)
            working_dir: Working directory (default: self.working_dir)
            check: Raise exception on non-zero exit code
            capture_output: Whether to capture stdout/stderr
            timeout: Command timeout in seconds (None for no timeout)

        Returns:
            Dictionary with:
                - exit_code: Command exit code
                - stdout: Standard output (if capture_output=True)
                - stderr: Standard error (if capture_output=True)

        Raises:
            RuntimeError: If container is not initialized
            ContainerError: If command fails and check=True
        """
        if not self._is_initialized or not self.container:
            raise RuntimeError("Environment not initialized. Call initialize() first.")

        user = user or self.user
        working_dir = working_dir or self.working_dir

        try:
            exec_result = self.container.exec_run(
                command,
                user=user,
                workdir=working_dir,
                demux=capture_output,
                tty=not capture_output,
            )

            exit_code = exec_result.exit_code

            result = {"exit_code": exit_code}

            if capture_output:
                stdout, stderr = exec_result.output
                result["stdout"] = stdout.decode('utf-8') if stdout else ""
                result["stderr"] = stderr.decode('utf-8') if stderr else ""

            if check and exit_code != 0:
                error_msg = f"Command failed with exit code {exit_code}: {command}"
                if capture_output and result.get("stderr"):
                    error_msg += f"\nStderr: {result['stderr']}"
                raise ContainerError(
                    self.container,
                    exit_code,
                    command,
                    self.image,
                    result.get("stderr", "")
                )

            return result

        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            if check:
                raise
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e)
            }

    def get_file_content(self, file_path: str) -> str:
        """
        Get the content of a file from the container.

        Args:
            file_path: Path to file in container

        Returns:
            File content as string
        """
        result = self.execute_command(f"cat {file_path}", capture_output=True)
        return result.get("stdout", "")

    def write_file(self, file_path: str, content: str) -> None:
        """
        Write content to a file in the container.

        Args:
            file_path: Path to file in container
            content: Content to write
        """
        self._write_file_to_container(file_path, content)

    def list_directory(self, dir_path: str = ".") -> List[str]:
        """
        List files in a directory.

        Args:
            dir_path: Directory path

        Returns:
            List of file/directory names
        """
        result = self.execute_command(f"ls -1 {dir_path}", capture_output=True)
        stdout = result.get("stdout", "")
        return [line.strip() for line in stdout.split("\n") if line.strip()]

    def get_current_state(self) -> Dict[str, Any]:
        """
        Get the current state of the environment.

        Returns:
            Dictionary with environment state information
        """
        if not self._is_initialized:
            return {"initialized": False}

        return {
            "initialized": True,
            "container_name": self.container_name,
            "container_id": self.container.short_id if self.container else None,
            "container_status": self.container.status if self.container else None,
            "image": self.image,
            "user": self.user,
            "working_dir": self.working_dir,
        }

    def cleanup(self) -> None:
        """
        Clean up the Docker container and resources.

        This method stops and removes the container.
        """
        if not self.container:
            self.logger.info("No container to clean up")
            return

        try:
            self.logger.info(f"Cleaning up container '{self.container_name}'")

            # Stop container
            self.container.stop(timeout=5)
            self.logger.info(f"Container '{self.container_name}' stopped")

            # Remove container (if not auto_remove)
            if not self.auto_remove:
                self.container.remove()
                self.logger.info(f"Container '{self.container_name}' removed")

            self.container = None
            self._is_initialized = False

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            # Try force removal
            try:
                self.container.remove(force=True)
            except Exception as e2:
                self.logger.error(f"Force removal failed: {e2}")

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()

    def __del__(self):
        """Destructor - ensure cleanup."""
        if hasattr(self, 'container') and self.container:
            try:
                self.cleanup()
            except:
                pass


class DockerOSEnvironmentFactory:
    """
    Factory for creating DockerOSEnvironment instances.

    This factory manages environment lifecycle and provides
    convenient methods for common use cases.
    """

    @staticmethod
    def create_from_task_config(
        task_config_path: str,
        image: str = "ubuntu:22.04",
        **kwargs
    ) -> DockerOSEnvironment:
        """
        Create an environment from an AgentBench task config file.

        Args:
            task_config_path: Path to task JSON file (e.g., os_task_0.json)
            image: Docker image to use
            **kwargs: Additional config options

        Returns:
            Initialized DockerOSEnvironment
        """
        config = {
            "image": image,
            "filesystem_config": task_config_path,
            **kwargs
        }

        env = DockerOSEnvironment(config)
        env.initialize()
        return env

    @staticmethod
    def create_minimal(
        image: str = "ubuntu:22.04",
        working_dir: str = "/root",
        **kwargs
    ) -> DockerOSEnvironment:
        """
        Create a minimal environment without filesystem initialization.

        Args:
            image: Docker image to use
            working_dir: Working directory
            **kwargs: Additional config options

        Returns:
            Initialized DockerOSEnvironment
        """
        config = {
            "image": image,
            "working_dir": working_dir,
            **kwargs
        }

        env = DockerOSEnvironment(config)
        env.initialize()
        return env
