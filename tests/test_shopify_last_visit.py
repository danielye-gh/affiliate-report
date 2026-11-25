import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from affiliate_report.platforms.shopify.orders import _extract_utm, _order_to_attribution_rows, ORDERS_QUERY
from affiliate_report.reconcile.shopify import load_shopify_oid_index, load_shopify_order_id_index
from affiliate_report.reconcile.impact import _match_row as impact_match
from affiliate_report.reconcile.awin import _match_row as awin_match
from affiliate_report.reconcile.dtc import DtcIndex, select_shopify_affiliate_rows, supplement_shopify_rows
from affiliate_report.shopify_attribution import read_order_utm_source


class ShopifyLastVisitTests(unittest.TestCase):
    def order(self, last, first):
        return {
            'legacyResourceId': '100', 'name': '#2020001', 'createdAt': '2026-11-25T00:00:00Z',
            'currentSubtotalPriceSet': {'shopMoney': {'amount': '100'}},
            'customerJourneySummary': {
                'lastVisit': {'utmParameters': last} if last is not None else None,
                'firstVisit': {'utmParameters': first},
            },
            'refunds': [{'createdAt': '2026-11-25T01:00:00Z',
                         'totalRefundedSet': {'shopMoney': {'amount': '20'}}}],
        }

    def test_empty_last_visit_does_not_fall_back_to_affiliate_first_visit(self):
        for last in (None, {}, {'source': None}, {'medium': 'cpc'}):
            with self.subTest(last=last):
                order = self.order(last, {'source': 'impact', 'medium': 'affiliate'})
                rows = _order_to_attribution_rows(order, ZoneInfo('Asia/Shanghai'))
                self.assertTrue(all(r['order_utm_source'] is None for r in rows))
                self.assertEqual(select_shopify_affiliate_rows(rows, 'impact'), [])
                self.assertNotIn('orderUtmSource', rows[0])
        self.assertNotIn('firstVisit', ORDERS_QUERY)

    def test_last_visit_drives_both_indexes_matching_and_refund_rows(self):
        rows = _order_to_attribution_rows(self.order(
            {'source': 'awin', 'medium': 'affiliate', 'campaign': 'last'},
            {'source': 'impact', 'campaign': 'first'},
        ), ZoneInfo('Asia/Shanghai'))
        self.assertEqual([r['order_utm_source'] for r in rows], ['awin', 'awin'])
        self.assertEqual(rows[0]['orderUtmCampaign'], 'last')
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / 'orders.json'
            raw.write_text(json.dumps(rows))
            oid = load_shopify_oid_index(raw)
            numeric = load_shopify_order_id_index(raw)
            self.assertEqual(oid['2020001'].order_utm_source, 'awin')
            self.assertEqual(numeric['100'].order_utm_source, 'awin')
            self.assertEqual(impact_match('2020001', {'us': oid}, utm_source='impact', dtc_index=DtcIndex())['匹配情况'], '')
            self.assertEqual(awin_match('100', numeric, utm_source='awin', site='us', dtc_index=DtcIndex())['匹配情况'], '匹配')
            self.assertEqual(numeric['100'].refund_status, '2')

    def test_legacy_source_is_rejected_before_querying_database(self):
        legacy = [{'orderId': '100', 'orderUtmSource': 'impact', 'oid': '2020001'}]
        with patch('affiliate_report.reconcile.dtc.load_attribution') as load:
            with self.assertRaisesRegex(ValueError, '重新拉取'):
                supplement_shopify_rows(legacy, site='us')
            load.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / 'legacy.json'
            raw.write_text(json.dumps(legacy))
            for loader in (load_shopify_oid_index, load_shopify_order_id_index):
                with self.assertRaisesRegex(ValueError, 'order_utm_source'):
                    loader(raw)

    def test_canonical_source_is_authoritative_even_when_blank(self):
        row = {'order_utm_source': None, 'orderUtmSource': 'impact'}
        self.assertIsNone(read_order_utm_source(row))
        self.assertEqual(select_shopify_affiliate_rows([row], 'impact'), [])


if __name__ == '__main__':
    unittest.main()
