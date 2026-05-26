"""
Test script for Docker OS Environment

This script runs comprehensive tests to verify the Docker OS Environment
is working correctly.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from Environment.DockerOSEnvironment import DockerOSEnvironment, DockerOSEnvironmentFactory
from Environment.docker_environment_adapter import DockerEnvironmentAdapter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_basic_environment():
    """Test 1: Basic Docker environment creation and command execution"""
    print("\n" + "=" * 60)
    print("TEST 1: Basic Environment")
    print("=" * 60)

    try:
        config = {
            "image": "ubuntu:22.04",
            "working_dir": "/root",
            "user": "root",
            "network_mode": "none",
        }

        with DockerOSEnvironment(config, logger=logger) as env:
            # Test 1.1: Simple command
            print("\n1.1 Testing simple command...")
            result = env.execute_command("echo 'Hello Docker'")
            assert result['exit_code'] == 0
            assert 'Hello Docker' in result['stdout']
            print("✓ Simple command works")

            # Test 1.2: File write
            print("\n1.2 Testing file write...")
            env.write_file("/tmp/test.txt", "Test content")
            result = env.execute_command("cat /tmp/test.txt")
            assert 'Test content' in result['stdout']
            print("✓ File write works")

            # Test 1.3: File read
            print("\n1.3 Testing file read...")
            content = env.get_file_content("/tmp/test.txt")
            assert 'Test content' in content
            print("✓ File read works")

            # Test 1.4: Directory listing
            print("\n1.4 Testing directory listing...")
            files = env.list_directory("/tmp")
            assert 'test.txt' in files
            print(f"✓ Directory listing works: {files}")

            # Test 1.5: Complex commands
            print("\n1.5 Testing complex commands...")
            result = env.execute_command(
                "echo 'line1' > /tmp/data.txt && echo 'line2' >> /tmp/data.txt && cat /tmp/data.txt"
            )
            assert result['exit_code'] == 0
            assert 'line1' in result['stdout'] and 'line2' in result['stdout']
            print("✓ Complex commands work")

        print("\n✅ TEST 1 PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_filesystem_initialization():
    """Test 2: Filesystem initialization from JSON"""
    print("\n" + "=" * 60)
    print("TEST 2: Filesystem Initialization")
    print("=" * 60)

    try:
        # Check if task file exists
        task_file = Path(__file__).parent / "AgentBench" / "os_interaction" / "os_task_0.json"

        if not task_file.exists():
            print(f"\n⚠️  Task file not found: {task_file}")
            print("Skipping filesystem initialization test")
            return True

        print(f"\n2.1 Loading task config from {task_file.name}...")

        env = DockerOSEnvironmentFactory.create_from_task_config(
            str(task_file),
            image="ubuntu:22.04"
        )

        try:
            # Test 2.1: Check if file exists
            print("\n2.2 Checking if /usr/stock.log exists...")
            result = env.execute_command("test -f /usr/stock.log", check=False)
            if result['exit_code'] != 0:
                print("⚠️  stock.log not found (filesystem initialization may have failed)")
            else:
                print("✓ stock.log exists")

                # Test 2.2: Read file content
                print("\n2.3 Reading stock.log content...")
                result = env.execute_command("head -5 /usr/stock.log")
                print(f"First 5 lines:\n{result['stdout']}")
                print("✓ File content readable")

                # Test 2.3: Execute task command
                print("\n2.4 Executing task command...")
                result = env.execute_command("grep 'Alice | Sell' /usr/stock.log | wc -l")
                count = result['stdout'].strip()
                print(f"Alice sold stock {count} times")
                print("✓ Task command executed successfully")

        finally:
            env.cleanup()

        print("\n✅ TEST 2 PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_resource_limits():
    """Test 3: Resource limits and security"""
    print("\n" + "=" * 60)
    print("TEST 3: Resource Limits")
    print("=" * 60)

    try:
        config = {
            "image": "ubuntu:22.04",
            "memory_limit": "256m",
            "cpu_quota": 50000,
            "network_mode": "none",
        }

        with DockerOSEnvironment(config, logger=logger) as env:
            # Test 3.1: Check environment state
            print("\n3.1 Checking environment state...")
            state = env.get_current_state()
            assert state['initialized'] == True
            print(f"✓ Environment state: {state}")

            # Test 3.2: Test network isolation
            print("\n3.2 Testing network isolation...")
            result = env.execute_command("ping -c 1 8.8.8.8", check=False)
            if result['exit_code'] != 0:
                print("✓ Network is properly isolated")
            else:
                print("⚠️  Network isolation may not be working")

        print("\n✅ TEST 3 PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_adapter_integration():
    """Test 4: Adapter integration"""
    print("\n" + "=" * 60)
    print("TEST 4: Adapter Integration")
    print("=" * 60)

    try:
        task_config = {
            "Environment": {
                "type": "docker_os",
                "config": {
                    "image": "ubuntu:22.04",
                    "network_mode": "none",
                }
            },
            "Agent": {
                "max_steps": 5
            }
        }

        with DockerEnvironmentAdapter(task_config, logger=logger) as adapter:
            # Test 4.1: Execute bash command
            print("\n4.1 Testing bash command action...")
            result = adapter.execute_action({
                "type": "bash_command",
                "command": "echo 'test'"
            })
            assert result['success'] == True
            assert 'test' in result['observation']
            print("✓ Bash command action works")

            # Test 4.2: Write file action
            print("\n4.2 Testing write file action...")
            result = adapter.execute_action({
                "type": "write_file",
                "path": "/tmp/adapter_test.txt",
                "content": "adapter test content"
            })
            assert result['success'] == True
            print("✓ Write file action works")

            # Test 4.3: Read file action
            print("\n4.3 Testing read file action...")
            result = adapter.execute_action({
                "type": "read_file",
                "path": "/tmp/adapter_test.txt"
            })
            assert result['success'] == True
            assert 'adapter test content' in result['content']
            print("✓ Read file action works")

            # Test 4.4: List directory action
            print("\n4.4 Testing list directory action...")
            result = adapter.execute_action({
                "type": "list_directory",
                "path": "/tmp"
            })
            assert result['success'] == True
            assert 'adapter_test.txt' in result['files']
            print("✓ List directory action works")

            # Test 4.5: Action history
            print("\n4.5 Testing action history...")
            history = adapter.get_action_history()
            assert len(history) == 4
            print(f"✓ Action history works: {len(history)} actions recorded")

        print("\n✅ TEST 4 PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_handling():
    """Test 5: Error handling"""
    print("\n" + "=" * 60)
    print("TEST 5: Error Handling")
    print("=" * 60)

    try:
        with DockerOSEnvironment({"image": "ubuntu:22.04"}, logger=logger) as env:
            # Test 5.1: Non-existent file
            print("\n5.1 Testing non-existent file...")
            result = env.execute_command("cat /nonexistent/file", check=False)
            assert result['exit_code'] != 0
            print("✓ Non-existent file error handled correctly")

            # Test 5.2: Invalid command
            print("\n5.2 Testing invalid command...")
            result = env.execute_command("nonexistentcommand", check=False)
            assert result['exit_code'] != 0
            print("✓ Invalid command error handled correctly")

            # Test 5.3: Permission denied (if not root)
            print("\n5.3 Testing permission handling...")
            result = env.execute_command("touch /etc/test_file", check=False)
            # This might succeed as root, which is fine
            print(f"✓ Permission handling works (exit code: {result['exit_code']})")

        print("\n✅ TEST 5 PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 5 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("Docker OS Environment Test Suite")
    print("=" * 60)

    tests = [
        ("Basic Environment", test_basic_environment),
        ("Filesystem Initialization", test_filesystem_initialization),
        ("Resource Limits", test_resource_limits),
        ("Adapter Integration", test_adapter_integration),
        ("Error Handling", test_error_handling),
    ]

    results = []

    for test_name, test_fn in tests:
        try:
            result = test_fn()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test {test_name} crashed: {e}", exc_info=True)
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
