import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from affiliate_report.models import MonthRange
from affiliate_report.platforms.shopify import ShopifyPlatformClient
from affiliate_report.reconcile.dtc import (
    build_index, supplement_shopify_rows, select_shopify_affiliate_rows,
)
from affiliate_report.pipeline.shopify_sheets import build_shopify_workbook_sheets
from affiliate_report.preprocess.shopify import preprocess_shopify_attribution


def database_row(order_id, source):
    return dict(store_name='PETLIBRO', order_id=order_id, order_name='#2020' + order_id,
                last_visit_utm_source=source)


class ShopifySupplementUnionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            dict(orderId='1', order_utm_source='google', rowKind='order', netSales='100'),
            dict(orderId='1', order_utm_source='google', rowKind='refund', netSales='-20'),
            dict(orderId='2', order_utm_source='impact', rowKind='order', netSales='50'),
            dict(orderId='3', order_utm_source='impact', rowKind='order', netSales='60'),
            dict(orderId='4', order_utm_source=None, rowKind='order', netSales='70'),
            dict(orderId='5', order_utm_source='google', rowKind='order', netSales='80'),
        ]
        self.index = build_index([
            database_row('1', 'impact'), database_row('2', 'impact'),
            database_row('3', 'awin'), database_row('4', 'awin'),
        ])

    def supplement(self, rows, *, site):
        return supplement_shopify_rows(rows, site=site, index=self.index)

    def test_union_preserves_original_new_orders_refunds_and_no_duplicate_events(self):
        rows = self.supplement(self.rows, site='us')
        impact = select_shopify_affiliate_rows(rows, 'impact')
        awin = select_shopify_affiliate_rows(rows, 'awin')
        self.assertEqual([r['orderId'] for r in impact], ['1', '1', '2', '3'])
        self.assertEqual([r['orderId'] for r in awin], ['3', '4'])
        self.assertEqual(impact[0]['order_utm_source'], 'google')
        self.assertEqual(impact[1]['rowKind'], 'refund')
        self.assertEqual(impact[1]['netSales'], '-20')
        self.assertEqual(impact[3]['补充归因'], 'awin')
        self.assertNotIn('补充归因', self.rows[0])

    @patch('affiliate_report.pipeline.shopify_sheets.supplement_shopify_rows')
    def test_workbook_rebuilds_from_full_shopify_even_with_stale_filtered_files(self, supplement):
        supplement.side_effect = self.supplement
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            full = root / 'shopify/us/sales_attribution/sales_attribution_2026-11.json'
            full.parent.mkdir(parents=True)
            full.write_text(json.dumps(self.rows))
            stale = root / 'shopify/us/impact_shopify/impact_shopify_2026-11.json'
            stale.parent.mkdir(parents=True)
            stale.write_text('[]')
            with patch('affiliate_report.pipeline.shopify_sheets.RAW_DIR', root):
                sheets = build_shopify_workbook_sheets('2026-11')
            self.assertEqual(len(sheets['sales_attribution-us']), 6)
            self.assertEqual(len(sheets['impact-shopify']), 4)
            self.assertEqual(len(sheets['awin-shopify']), 2)
            self.assertEqual(sheets['impact-shopify']['orderId'].tolist(), ['1', '1', '2', '3'])
            self.assertEqual(sheets['impact-shopify']['补充归因'].tolist(), ['impact', 'impact', 'impact', 'awin'])
            supplement.assert_called_once()

    @patch('affiliate_report.platforms.shopify.supplement_shopify_rows')
    @patch('affiliate_report.platforms.shopify.ShopifyOrdersAPI')
    def test_fetch_exports_supplemented_union_and_preprocess_retains_column(self, api_type, supplement):
        supplement.side_effect = self.supplement
        api_type.return_value.list_attribution_rows_for_month.return_value = self.rows
        config = Mock()
        config.impact_utm.source = 'impact'
        config.awin_utm.source = 'awin'
        site = Mock(label='us')
        config.resolve_sites.return_value = [site]
        client = ShopifyPlatformClient(config=config)
        with tempfile.TemporaryDirectory() as directory, patch.object(client, '_http_client'):
            paths = client.fetch_monthly_reports_by_site(
                MonthRange(2026, 11), output_dir=Path(directory),
            )
            impact = json.loads(paths['us/impact-shopify'].read_text())
            awin = json.loads(paths['us/awin-shopify'].read_text())
            self.assertEqual(len(impact), 4)
            self.assertEqual(len(awin), 2)
            processed = preprocess_shopify_attribution(
                paths['us/impact-shopify'], '2026-11', report='impact-shopify', site='us',
            )
            self.assertEqual(processed['补充归因'].tolist(), ['impact', 'impact', 'impact', 'awin'])

    @patch('affiliate_report.reconcile.dtc.load_attribution')
    def test_queries_full_order_set_before_filtering(self, load):
        load.return_value = self.index
        rows = supplement_shopify_rows(self.rows, site='us')
        load.assert_called_once_with({'us': ['1', '1', '2', '3', '4', '5']}, key_type='order_id')
        self.assertEqual(rows[4]['补充归因'], 'awin')

    def test_custom_original_utm_filter_still_includes_canonical_supplement(self):
        rows = [{'order_utm_source': 'custom', '补充归因': ''},
                {'order_utm_source': 'google', '补充归因': 'impact'}]
        self.assertEqual(select_shopify_affiliate_rows(rows, 'impact', original_source='custom'), rows)


if __name__ == '__main__':
    unittest.main()
