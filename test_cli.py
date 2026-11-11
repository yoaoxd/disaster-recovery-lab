import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
import disaster_recovery_lab as dr


class CommandInterface(unittest.TestCase):
    def test_help_does_not_start_docker(self):
        with patch('disaster_recovery_lab.run') as run, redirect_stdout(StringIO()):
            with self.assertRaises(SystemExit) as result:
                dr.main(['--help'])
        self.assertEqual(result.exception.code, 0)
        run.assert_not_called()

    def test_arguments_and_exit_code(self):
        with patch('disaster_recovery_lab.run', return_value=1) as run:
            self.assertEqual(dr.main(['service-loss', '--rto-target', '180']), 1)
        self.assertEqual(run.call_args.args[0].scenario, 'service-loss')
        self.assertEqual(run.call_args.args[0].rto_target, 180)

    def test_public_checksum_contract(self):
        dr.check_archive(b'backup', dr.digest(b'backup'))


if __name__ == '__main__':
    unittest.main()
