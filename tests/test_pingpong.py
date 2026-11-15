
import unittest

from aiori_pipeline.pingpong import detect_ping_pong


def ho(time, imsi, source, target, event="SUCCESS"):
    return {
        "time_s": str(time),
        "imsi": str(imsi),
        "source_cell_id": str(source),
        "target_cell_id": str(target),
        "event": event,
    }


class PingPongTests(unittest.TestCase):

    def test_valid_pingpong(self):
        rows = [ho(1.0, 1, 1, 2), ho(1.5, 1, 2, 1)]
        self.assertEqual(len(detect_ping_pong(rows)), 1)

    def test_late_return(self):
        rows = [ho(1.0, 1, 1, 2), ho(3.0, 1, 2, 1)]
        self.assertEqual(len(detect_ping_pong(rows)), 0)

    def test_different_users(self):
        rows = [ho(1.0, 1, 1, 2), ho(1.5, 2, 2, 1)]
        self.assertEqual(len(detect_ping_pong(rows)), 0)

    def test_failed_handover(self):
        rows = [
            ho(1.0, 1, 1, 2, "FAILURE"),
            ho(1.5, 1, 2, 1),
        ]
        self.assertEqual(len(detect_ping_pong(rows)), 0)

    def test_no_reversal(self):
        rows = [ho(1.0, 1, 1, 2), ho(1.5, 1, 2, 3)]
        self.assertEqual(len(detect_ping_pong(rows)), 0)

    def test_exact_threshold(self):
        rows = [ho(1.0, 1, 1, 2), ho(2.0, 1, 2, 1)]
        self.assertEqual(len(detect_ping_pong(rows)), 1)

    def test_multiple_reversals(self):
        rows = [
            ho(1.0, 1, 1, 2),
            ho(1.3, 1, 2, 1),
            ho(1.6, 1, 1, 2),
        ]
        self.assertEqual(len(detect_ping_pong(rows)), 2)

    def test_invalid_window(self):
        with self.assertRaises(ValueError):
            detect_ping_pong([], window_s=0)


if __name__ == "__main__":
    unittest.main()
