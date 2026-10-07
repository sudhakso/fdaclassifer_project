import os
import tempfile
import unittest

from fda_classifier.train import _last_complete_checkpoint


class LastCompleteCheckpointTests(unittest.TestCase):
    def test_skips_a_checkpoint_that_was_cut_off_mid_save(self):
        with tempfile.TemporaryDirectory() as root:
            for step, complete in ((540, True), (1080, True), (1620, False)):
                directory = os.path.join(root, f"checkpoint-{step}")
                os.makedirs(directory)
                if complete:
                    with open(os.path.join(directory, "trainer_state.json"), "w", encoding="utf-8") as handle:
                        handle.write("{}")
            self.assertEqual(_last_complete_checkpoint(root), os.path.join(root, "checkpoint-1080"))

    def test_no_usable_checkpoint_means_a_fresh_start(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(_last_complete_checkpoint(root))
            os.makedirs(os.path.join(root, "checkpoint-540"))
            self.assertIsNone(_last_complete_checkpoint(root))
        self.assertIsNone(_last_complete_checkpoint(os.path.join(root, "missing")))


if __name__ == "__main__":
    unittest.main()
