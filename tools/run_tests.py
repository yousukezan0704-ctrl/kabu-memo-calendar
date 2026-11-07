"""全テストを1コマンドで実行する（cd や複合コマンドを使わず、許可済みの形 python -X utf8 tools/run_tests.py で呼べる）。"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "collector", "tests")
sys.path[:0] = [TESTS, os.path.join(ROOT, "collector"), os.path.join(ROOT, "tools")]

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(TESTS, pattern="test_*.py")
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if res.wasSuccessful() else 1)
