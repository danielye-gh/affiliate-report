import contextlib
import io
import unittest
from unittest.mock import patch, Mock

from affiliate_report.platforms.impact.client import ImpactClient, ImpactAPIError


class Clock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class ImpactJobWaitTests(unittest.TestCase):
    def run_poll(self, client, clock, **kwargs):
        with patch('affiliate_report.platforms.impact.client.time.monotonic', clock.monotonic), \
             patch('affiliate_report.platforms.impact.client.time.sleep', clock.sleep), \
             contextlib.redirect_stderr(io.StringIO()):
            return client.poll_job_until_complete('/Advertisers/test/Jobs/job-1', **kwargs)

    @patch.dict('os.environ', {'IMPACT_EXPORT_MAX_WAIT_SECONDS': '1800'})
    def test_job_can_complete_after_old_ten_minute_limit_without_new_export(self):
        clock = Clock()
        with ImpactClient('test', 'test') as client:
            client.get_json = Mock(side_effect=lambda path: {
                'Status': 'COMPLETED' if clock.now >= 900 else 'QUEUED',
                'ResultUri': '/Advertisers/test/Jobs/job-1/Download',
            })
            job = self.run_poll(client, clock, poll_interval=300)
            self.assertEqual(job['Status'], 'COMPLETED')
            self.assertEqual(clock.now, 900)
            self.assertTrue(all(call.args == ('/Advertisers/test/Jobs/job-1.json',)
                                for call in client.get_json.call_args_list))

    @patch.dict('os.environ', {'IMPACT_EXPORT_MAX_WAIT_SECONDS': '12'})
    def test_timeout_reports_last_state_and_resume_and_clamps_last_sleep(self):
        clock = Clock()
        with ImpactClient('test', 'test') as client:
            client.get_json = Mock(return_value={'Status': 'QUEUED'})
            with self.assertRaises(ImpactAPIError) as caught:
                self.run_poll(client, clock)
            self.assertEqual(clock.sleeps, [5, 5, 2])
            self.assertIn('QUEUED', str(caught.exception))
            self.assertIn('IMPACT_EXPORT_MAX_WAIT_SECONDS', str(caught.exception))
            self.assertIn('--queued-uri', str(caught.exception))
            self.assertEqual(caught.exception.body, {'Status': 'QUEUED'})

    def test_explicit_timeout_override_and_status_normalization(self):
        with ImpactClient('test', 'test', export_max_wait=30) as client:
            client.get_json = Mock(side_effect=[{'Status': ' queued '}, {'Status': ' completed '}])
            clock = Clock()
            self.assertEqual(self.run_poll(client, clock, max_wait=10)['Status'], ' completed ')
            self.assertEqual(clock.now, 5)

    def test_failed_job_is_not_treated_as_pending(self):
        with ImpactClient('test', 'test') as client:
            client.get_json = Mock(return_value={'Status': 'FAILED', 'StatusMessage': 'failed server job'})
            with self.assertRaisesRegex(ImpactAPIError, 'failed server job'):
                self.run_poll(client, Clock())

    def test_forbidden_is_still_actionable(self):
        with ImpactClient('test', 'test') as client:
            client.get_json = Mock(side_effect=ImpactAPIError('Forbidden', status_code=403))
            with self.assertRaisesRegex(ImpactAPIError, 'Jobs API returned 403'):
                self.run_poll(client, Clock())

    def test_invalid_env_settings_fail_before_http_client_creation(self):
        for value in ('0', '-1', 'nan', 'inf', 'abc'):
            with self.subTest(value=value), patch.dict('os.environ', {'IMPACT_EXPORT_MAX_WAIT_SECONDS': value}), \
                 patch('affiliate_report.platforms.impact.client.httpx.Client') as http:
                with self.assertRaisesRegex(ValueError, 'IMPACT_EXPORT_MAX_WAIT_SECONDS'):
                    ImpactClient('test', 'test')
                http.assert_not_called()


if __name__ == '__main__':
    unittest.main()
