import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request


class RunScriptsTest(unittest.TestCase):
    def _base_env(self, **extra):
        state_dir = tempfile.mkdtemp(prefix="mstu-run-scripts-")
        return {
            **os.environ,
            "MSTU_TRADING_STATE_DIR": state_dir,
            **extra,
        }

    def test_start_and_stop_scripts_exist_and_are_executable(self):
        for path in ["start_all.sh", "stop_all.sh"]:
            self.assertTrue(os.path.exists(path), f"{path} should exist")
            mode = os.stat(path).st_mode
            self.assertTrue(mode & stat.S_IXUSR, f"{path} should be executable")

    def test_backtest_help_runs(self):
        result = subprocess.run(
            [sys.executable, "backtest.py", "--help"],
            cwd=os.getcwd(),
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: backtest.py", result.stdout)

    def test_optimize_backtest_help_runs(self):
        result = subprocess.run(
            [sys.executable, "optimize_backtest.py", "--help"],
            cwd=os.getcwd(),
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: optimize_backtest.py", result.stdout)

    def test_scheduler_help_runs(self):
        result = subprocess.run(
            [sys.executable, "scheduler.py", "--help"],
            cwd=os.getcwd(),
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: scheduler.py", result.stdout)

    def test_webhook_daemon_help_runs(self):
        result = subprocess.run(
            [sys.executable, "webhook_daemon.py", "--help"],
            cwd=os.getcwd(),
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: webhook_daemon.py", result.stdout)

    def test_web_app_boots_and_serves_health_endpoint(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        process = subprocess.Popen(
            [sys.executable, "web_app.py"],
            cwd=os.getcwd(),
            env=self._base_env(WEB_APP_PORT=str(port)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            deadline = time.time() + 10
            last_error = None
            while time.time() < deadline:
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    self.fail(
                        f"web_app.py exited early with code {process.returncode}\n"
                        f"stdout:\n{stdout}\n"
                        f"stderr:\n{stderr}"
                    )
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read().decode("utf-8"), '{"status":"ok"}\n')
                        return
                except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                    last_error = exc
                    time.sleep(0.2)

            self.fail(f"web_app.py did not become healthy before timeout: {last_error}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
