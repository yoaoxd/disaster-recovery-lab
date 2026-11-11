import unittest
import lab


class RecoveryContracts(unittest.TestCase):
    def test_changed_archive_is_refused(self):
        original = b'original backup'
        with self.assertRaises(ValueError):
            lab.check_archive(b'corrupt', lab.digest(original))

    def test_unchanged_archive_is_accepted(self):
        lab.check_archive(b'backup', lab.digest(b'backup'))

    def test_rto_breach_fails_objectives(self):
        self.assertFalse(lab.metrics(121, 1, 1, 120, 60)['objectives_met'])

    def test_rpo_breach_fails_objectives(self):
        self.assertFalse(lab.metrics(1, 61, 1, 120, 60)['objectives_met'])

    def test_both_objectives_must_pass(self):
        self.assertTrue(lab.metrics(10, 2, 1, 120, 60)['objectives_met'])

    def test_invalid_targets_are_rejected(self):
        for value in ('nan', 'inf', '0', '-1'):
            with self.assertRaises(Exception):
                lab.positive(value)


if __name__ == '__main__':
    unittest.main()
