import unittest
from unittest.mock import Mock

from affiliate_report.models import MonthRange
from affiliate_report.platforms.impact.client import ImpactAPIError, ImpactClient
from affiliate_report.platforms.impact.reports import ImpactReportsAPI


class ImpactReportExportTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=ImpactClient)
        self.client._path.side_effect = lambda suffix: '/Advertisers/test' + suffix
        self.api = ImpactReportsAPI(self.client)
        self.queue_uri = '/Advertisers/test/Jobs/job-1'
        self.result_uri = self.queue_uri + '/Download'
        self.csv = b'OID,Status\n2020001,Pending\n'
        self.client.download_job_result.return_value = self.csv
        self.client.download.return_value = self.csv

    def export(self):
        return self.api.export_report_csv(
            'adv_action_listing_pm_only', MonthRange(2026, 11),
            program_id='19553', extra_params={'ACTION_STATUS': 'Approved,Pending'},
        )

    def test_cached_and_normal_exports_poll_then_download(self):
        for status in ('CACHED', 'QUEUED', 'OK', ' cached '):
            with self.subTest(status=status):
                self.client.reset_mock()
                self.client.get_json.return_value = {
                    'Status': status, 'QueuedUri': self.queue_uri, 'ResultUri': self.result_uri,
                }
                job = {'Status': 'COMPLETED', 'ResultUri': self.result_uri}
                self.client.poll_job_until_complete.return_value = job
                self.assertEqual(self.export(), self.csv)
                self.client.poll_job_until_complete.assert_called_once_with(self.queue_uri)
                self.client.download_job_result.assert_called_once_with(job)
                self.client.download.assert_not_called()
                params = self.client.get_json.call_args.kwargs['params']
                self.assertEqual(params['START_DATE'], '2026-11-01')
                self.assertEqual(params['END_DATE'], '2026-11-30')
                self.assertEqual(params['ACTION_STATUS'], 'Approved,Pending')

    def test_cached_result_only_uses_job_download_with_retry_support(self):
        response = {'Status': 'CACHED', 'ResultUri': 'https://api.impact.com' + self.result_uri}
        self.client.get_json.return_value = response
        self.assertEqual(self.export(), self.csv)
        self.client.download_job_result.assert_called_once_with(response)
        self.client.poll_job_until_complete.assert_not_called()

    def test_direct_result_still_downloads(self):
        self.client.get_json.return_value = {'Status': 'OK', 'ResultUri': '/reports/result.csv'}
        self.assertEqual(self.export(), self.csv)
        self.client.download.assert_called_once_with('/reports/result.csv')

    def test_failure_and_unknown_status_are_rejected(self):
        for status in ('FAILED', 'ERROR', 'UNKNOWN'):
            with self.subTest(status=status):
                self.client.get_json.return_value = {'Status': status, 'QueuedUri': self.queue_uri}
                with self.assertRaisesRegex(ImpactAPIError, 'Unexpected export queue status'):
                    self.export()
        self.client.download_job_result.assert_not_called()

    def test_missing_uris_are_rejected(self):
        self.client.get_json.return_value = {'Status': 'CACHED'}
        with self.assertRaisesRegex(ImpactAPIError, 'missing QueuedUri'):
            self.export()

    def test_cached_job_failure_does_not_download(self):
        self.client.get_json.return_value = {'Status': 'CACHED', 'QueuedUri': self.queue_uri}
        self.client.poll_job_until_complete.side_effect = ImpactAPIError('Impact job failed')
        with self.assertRaisesRegex(ImpactAPIError, 'job failed'):
            self.export()
        self.client.download_job_result.assert_not_called()


if __name__ == '__main__':
    unittest.main()
