"""Keep the a5xx shared-VM fix in the kernel patch stack.

Without it, a client closing a dma-buf handle unmaps the buffer for phoc too,
which caused the repeatable GPU translation faults (see patch 0014).
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SharedVmPatchTests(unittest.TestCase):
    def test_handle_close_keeps_global_vm_mappings(self):
        hunks = []
        for patch in sorted((ROOT / "kernel/patches").glob("*.patch")):
            match = re.search(r"^--- a/drivers/gpu/drm/msm/msm_gem\.c\n.*?(?=^--- |^diff |\Z)",
                              patch.read_text(), re.MULTILINE | re.DOTALL)
            if match:
                hunks.append(match.group())
        added = "\n".join(line for hunk in hunks for line in hunk.splitlines()
                          if line.startswith("+"))
        self.assertIn("if (ctx->vm == priv->gpu->vm)", added)


if __name__ == "__main__":
    unittest.main()
