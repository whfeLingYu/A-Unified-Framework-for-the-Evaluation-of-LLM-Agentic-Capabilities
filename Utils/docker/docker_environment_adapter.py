"""
Docker Environment Adapter

This module provides an adapter to integrate DockerOSEnvironment
into the existing evaluation framework.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from DockerOSEnvironment import DockerOSEnvironment, DockerOSEnvironmentFactory


class DockerEnvironmentAdapter:
    """
    Adapter to integrate DockerOSEnvironment with the existing framework.

    This adapter provides a unified interface that works with the
    existing runner.py and evaluation system.
    """

    def __init__(
        self,
        task_config: Dict[str, Any],
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the adapter.

        Args:
            task_config: Task configuration from YAML or task file
            logger: Optional logger
        """
        self.task_config = task_config
        self.logger = logger or logging.getLogger(__name__)
        self.env: Optional[DockerOSEnvironment] = None
        self.action_history: List[Dict[str, Any]] = []

    def setup(self) -> None:
        """
        Set up the Docker environment based on task configuration.

        Reads environment configuration from task_config and initializes
        the Docker container.
        """
        # Extract Docker environment config
        env_config = self.task_config.get("Environment", {})

        if env_config.get("type") != "docker_os":
            raise ValueError(
                f"Invalid environment type: {env_config.get('type')}. "
                "Expected 'docker_os'"
            )

        docker_config = env_config.get("config", {})

        # Check if filesystem config is provided in task
        filesystem_config = None
        if "filesystem_config" in self.task_config:
            filesystem_config = self.task_config["filesystem_config"]
        elif "environment_path" in self.task_config:
            # Support legacy naming
            filesystem_config = self.task_config["environment_path"]

        if filesystem_config:
            docker_config["filesystem_config"] = filesystem_config

        # Create environment
        self.env = DockerOSEnvironment(docker_config, logger=self.logger)
        self.env.initialize()

        self.logger.info("Docker OS Environment set up successfully")

    def execute_action(
        self,
        action: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute an agent action in the environment.

        Args:
            action: Action dictionary with:
                - type: Action type (e.g., "bash_command")
                - command: Command to execute
                - arguments: Optional arguments

        Returns:
            Result dictionary with:
                - success: Whether action succeeded
                - observation: Observation from environment
                - stdout: Command stdout
                - stderr: Command stderr
                - exit_code: Command exit code
        """
        if not self.env or not self.env._is_initialized:
            raise RuntimeError("Environment not initialized. Call setup() first.")

        action_type = action.get("type", "bash_command")

        if action_type == "bash_command":
            command = action.get("command")
            if not command:
                return {
                    "success": False,
                    "observation": "No command provided",
                    "error": "Missing command"
                }

            # Execute command
            result = self.env.execute_command(command, check=False)

            # Record action
            self.action_history.append({
                "action": action,
                "result": result
            })

            return {
                "success": result["exit_code"] == 0,
                "observation": result.get("stdout", ""),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "exit_code": result["exit_code"]
            }

        elif action_type == "read_file":
            file_path = action.get("path")
            try:
                content = self.env.get_file_content(file_path)
                return {
                    "success": True,
                    "observation": content,
                    "content": content
                }
            except Exception as e:
                return {
                    "success": False,
                    "observation": f"Error reading file: {e}",
                    "error": str(e)
                }

        elif action_type == "write_file":
            file_path = action.get("path")
            content = action.get("content", "")
            try:
                self.env.write_file(file_path, content)
                return {
                    "success": True,
                    "observation": f"File written: {file_path}"
                }
            except Exception as e:
                return {
                    "success": False,
                    "observation": f"Error writing file: {e}",
                    "error": str(e)
                }

        elif action_type == "list_directory":
            dir_path = action.get("path", ".")
            try:
                files = self.env.list_directory(dir_path)
                return {
                    "success": True,
                    "observation": "\n".join(files),
                    "files": files
                }
            except Exception as e:
                return {
                    "success": False,
                    "observation": f"Error listing directory: {e}",
                    "error": str(e)
                }

        else:
            return {
                "success": False,
                "observation": f"Unknown action type: {action_type}",
                "error": f"Unknown action type: {action_type}"
            }

    def get_observation(self) -> str:
        """
        Get current observation from the environment.

        Returns:
            Current working directory and status
        """
        if not self.env or not self.env._is_initialized:
            return "Environment not initialized"

        result = self.env.execute_command("pwd", check=False)
        current_dir = result.get("stdout", "").strip()

        return f"Current directory: {current_dir}"

    def get_state(self) -> Dict[str, Any]:
        """
        Get current environment state.

        Returns:
            Environment state dictionary
        """
        if not self.env:
            return {"initialized": False}

        return self.env.get_current_state()

    def get_action_history(self) -> List[Dict[str, Any]]:
        """
        Get history of all actions executed.

        Returns:
            List of action-result pairs
        """
        return self.action_history

    def reset(self) -> None:
        """
        Reset the environment to initial state.

        Note: This recreates the container from scratch.
        """
        if self.env:
            self.env.cleanup()

        self.action_history = []
        self.setup()

    def cleanup(self) -> None:
        """
        Clean up the environment.
        """
        if self.env:
            self.env.cleanup()
            self.env = None

    def __enter__(self):
        """Context manager entry."""
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()


def create_docker_environment_from_config(
    config_path: str,
    logger: Optional[logging.Logger] = None
) -> DockerEnvironmentAdapter:
    """
    Create a DockerEnvironmentAdapter from a YAML config file.

    Args:
        config_path: Path to YAML config file
        logger: Optional logger

    Returns:
        Initialized DockerEnvironmentAdapter
    """
    import yaml

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    adapter = DockerEnvironmentAdapter(config, logger=logger)
    adapter.setup()

    return adapter


def run_task_with_docker_environment(
    task_data: Dict[str, Any],
    agent_fn,
    docker_config: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None
) -> Dict[str, Any]:
    """
    Run a single task with Docker environment.

    Args:
        task_data: Task data dictionary (from JSONL)
        agent_fn: Agent function that takes (observation, env_state) and returns action
        docker_config: Optional Docker configuration (overrides task config)
        logger: Optional logger

    Returns:
        Task result dictionary with:
            - task_id: Task identifier
            - success: Whether task succeeded
            - actions: List of actions taken
            - final_observation: Final observation
            - metrics: Evaluation metrics
    """
    logger = logger or logging.getLogger(__name__)

    # Merge configs
    task_config = task_data.copy()
    if docker_config:
        task_config["Environment"] = {
            "type": "docker_os",
            "config": docker_config
        }

    # Create environment
    adapter = DockerEnvironmentAdapter(task_config, logger=logger)

    try:
        adapter.setup()

        # Get initial observation
        observation = adapter.get_observation()
        logger.info(f"Initial observation: {observation}")

        # Run agent
        max_steps = task_config.get("Agent", {}).get("max_steps", 10)
        success = False

        for step in range(max_steps):
            logger.info(f"Step {step + 1}/{max_steps}")

            # Agent decides action
            env_state = adapter.get_state()
            action = agent_fn(observation, env_state)

            if action is None or action.get("type") == "done":
                logger.info("Agent signaled completion")
                success = True
                break

            # Execute action
            result = adapter.execute_action(action)
            observation = result.get("observation", "")

            logger.info(f"Action: {action.get('command', action.get('type'))}")
            logger.info(f"Result: {result.get('success')}")

            if not result.get("success"):
                logger.warning(f"Action failed: {result.get('error')}")

        # Get results
        action_history = adapter.get_action_history()

        return {
            "task_id": task_data.get("task_id", "unknown"),
            "success": success,
            "actions": action_history,
            "final_observation": observation,
            "num_steps": len(action_history),
            "metrics": {
                "steps_used": len(action_history),
                "max_steps": max_steps,
                "success_rate": 1.0 if success else 0.0
            }
        }

    except Exception as e:
        logger.error(f"Task failed with error: {e}", exc_info=True)
        return {
            "task_id": task_data.get("task_id", "unknown"),
            "success": False,
            "error": str(e),
            "metrics": {"success_rate": 0.0}
        }

    finally:
        adapter.cleanup()
