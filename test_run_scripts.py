import os
import stat
import unittest


class RunScriptsTest(unittest.TestCase):
    def test_start_and_stop_scripts_exist_and_are_executable(self):
        for path in ["start_all.sh", "stop_all.sh"]:
            self.assertTrue(os.path.exists(path), f"{path} should exist")
            mode = os.stat(path).st_mode
            self.assertTrue(mode & stat.S_IXUSR, f"{path} should be executable")


if __name__ == "__main__":
    unittest.main()
