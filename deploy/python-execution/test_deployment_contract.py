import re
import unittest
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent


class PythonExecutionDeploymentContractTests(unittest.TestCase):
    def test_bside_override_and_documented_recreate_target_python_execution(self) -> None:
        override = (DIRECTORY / "management.override.yaml").read_text(encoding="utf-8")
        bside = re.search(r"(?ms)^  bside:\n(?P<body>.*?)(?=^  [a-zA-Z]|\Z)", override)
        self.assertIsNotNone(bside)
        assert bside is not None
        self.assertIn('A2FLOW_ENGINE_RPC_TARGET: "127.0.0.1:8794"', bside.group("body"))

        instructions = (DIRECTORY / "README.zh-CN.md").read_text(encoding="utf-8")
        self.assertIn("-f ./management.override.yaml", instructions)
        self.assertIn("A2FLOW_ENGINE_RPC_TARGET=127.0.0.1:8794", instructions)
        self.assertIn("--no-deps --force-recreate bside", instructions)


if __name__ == "__main__":
    unittest.main()
