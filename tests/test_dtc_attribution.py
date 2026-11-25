import json
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pymysql

from affiliate_report.reconcile.dtc import build_index, load_attribution, DtcIndex
from affiliate_report.reconcile.impact import _match_row as impact_match, enrich_impact_with_shopify
from affiliate_report.reconcile.awin import _match_row as awin_match, enrich_awin_with_shopify
from affiliate_report.reconcile.shopify import ShopifyOidMatch, ShopifyOrderIdMatch
from affiliate_report.pipeline.match_summary import build_match_summary_sheets


def record(source="impact", store="PETLIBRO", order_id="100", oid="2020001", stamp="2026-11-25 01:00:00"):
    return dict(store_name=store, order_id=order_id, order_name="#" + oid,
                last_visit_utm_source=source, _etl_loaded_at=stamp,
                sale_happened_at=stamp, order_updated_date=stamp[:10])


class AttributionTests(unittest.TestCase):
    def test_index_deduplicates_latest_valid_and_rejects_conflict(self):
        index = build_index([record(), record(), record(" AWIN ", stamp="2026-11-25 02:00:00"), record("google")])
        self.assertEqual(index.by_oid["PETLIBRO", "2020001"].source, "awin")
        with self.assertRaisesRegex(ValueError, "conflict"):
            build_index([record(), record("awin")])

    def test_new_non_affiliate_or_blank_snapshot_clears_old_supplement(self):
        shop = {"us": {"2020001": ShopifyOidMatch("2020001", "100", "google", False)}}
        for source in ("google", "", None):
            with self.subTest(source=source):
                index = build_index([record(), record(source, stamp="2026-11-25 02:00:00")])
                self.assertFalse(index.by_order_id)
                row = impact_match("2020001", shop, utm_source="impact", dtc_index=index)
                self.assertEqual((row['补充归因'], row['匹配情况']), ('', ''))

    def test_store_isolation(self):
        index = build_index([record("awin", store="PETLIBRO UK")])
        self.assertEqual(awin_match("100", {}, utm_source="awin", site="de", dtc_index=index)["补充归因"], "")

    def test_impact_override_and_cross_network(self):
        shop = {"us": {"2020001": ShopifyOidMatch("2020001", "100", "google", False)}}
        row = impact_match("#2020001", shop, utm_source="impact", dtc_index=build_index([record()]))
        self.assertEqual((row["attribution"], row["补充归因"], row["匹配情况"]), ("google", "impact", "匹配"))
        row = impact_match("2020001", shop, utm_source="impact", dtc_index=build_index([record("awin")]))
        self.assertEqual((row["补充归因"], row["匹配情况"]), ("awin", ""))

    def test_fallback_to_shopify(self):
        shop = {"us": {"2020001": ShopifyOidMatch("2020001", "100", "IMPACT", False)}}
        row = impact_match("2020001", shop, utm_source="impact", dtc_index=DtcIndex())
        self.assertEqual((row["补充归因"], row["匹配情况"]), ("", "匹配"))

    def test_database_only_order(self):
        row = impact_match("2020001", {}, utm_source="impact", dtc_index=build_index([record()]))
        self.assertEqual((row["匹配情况"], row["shopify是否退款"]), ("匹配", ""))
        index = build_index([record("awin", store="PETLIBRO UK", oid="2220001")])
        row = awin_match("100", {}, utm_source="awin", site="uk", dtc_index=index)
        self.assertEqual((row["补充归因"], row["shopify匹配"]), ("awin", "2220001"))

    def test_awin_cross_network_overrides_original_match(self):
        shop = {"100": ShopifyOrderIdMatch("100", "2220001", "awin", False)}
        row = awin_match("100", shop, utm_source="awin", site="uk",
                         dtc_index=build_index([record("impact", store="PETLIBRO UK", oid="2220001")]))
        self.assertEqual((row["Attribution"], row["补充归因"], row["匹配情况"]), ("awin", "impact", ""))

    def test_pipeline_columns_refunds_amounts_and_summary(self):
        # Six rows per partner avoid unrelated small-partner approval rules.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            impact = path / "impact.csv"
            pd.DataFrame([{"OID": "2020001", "Action Cost": "10", "Revenue": "100", "Partner": "test"}] * 6).to_csv(impact, index=False)
            shop = {"us": {"2020001": ShopifyOidMatch("2020001", "100", "google", True, refund_status="1")}}
            result = enrich_impact_with_shopify(impact, shop, dtc_index=build_index([record()]))
            self.assertEqual(len(result), 6)
            self.assertTrue((result["Revenue"] == "100.00").all())
            self.assertTrue((result["Action"] == "取消").all())
            self.assertTrue((result["补充归因"] == "impact").all())
            summary = build_match_summary_sheets({"Impact": result})["Impact-Summary"]
            self.assertEqual(int(summary.iloc[0]["匹配"]), 6)
            awin = path / "awin.json"
            awin.write_text(json.dumps([{"id": str(i), "orderRef": "100", "publisherId": "1", "saleAmount": {"amount": 100}, "commissionAmount": {"amount": 10}} for i in range(6)]))
            index = build_index([record("awin", store="PETLIBRO UK", oid="2220001")])
            result = enrich_awin_with_shopify(awin, {}, site="uk", dtc_index=index)
            self.assertEqual(len(result), 6)
            self.assertTrue((result["Action"] == "通过").all())
            self.assertTrue((result["sale_amount"] == "100.00").all())
            self.assertIn("补充归因", result.columns)

    def test_full_decision_pipeline_uses_supplement_before_original_attribution(self):
        # Run through final Action, not only the matching helper. Keep partner
        # volume above five so this verifies attribution rather than volume exceptions.
        for platform in ('impact', 'awin'):
            other = 'awin' if platform == 'impact' else 'impact'
            cases = [
                ('google', platform, '0', '10', '匹配', '通过'),
                (platform, other, '0', '10', '', '取消'),
                (platform, None, '0', '10', '匹配', '通过'),
                ('google', None, '0', '10', '', '取消'),
                ('google', platform, '1', '10', '匹配', '取消'),
                ('google', platform, '2', '10', '匹配', '取消'),
                (platform, other, '0', '0', '', '通过'),
            ]
            for original, supplemental, refund, commission, matched, action in cases:
                with self.subTest(platform=platform, original=original, supplemental=supplemental,
                                  refund=refund, commission=commission), tempfile.TemporaryDirectory() as directory:
                    path = Path(directory)
                    if platform == 'impact':
                        raw = path / 'impact.csv'
                        pd.DataFrame([{'OID': '2020001', 'Action Cost': commission,
                                       'Revenue': '100', 'Partner': 'test'}] * 6).to_csv(raw, index=False)
                        shop = {'us': {'2020001': ShopifyOidMatch('2020001', '100', original,
                                 refund in ('1', '2'), refund_status=refund)}}
                        index = build_index([record(supplemental)]) if supplemental else DtcIndex()
                        result = enrich_impact_with_shopify(raw, shop, dtc_index=index)
                    else:
                        raw = path / 'awin.json'
                        raw.write_text(json.dumps([{'id': str(i), 'orderRef': '100', 'publisherId': '1',
                            'saleAmount': {'amount': 100}, 'commissionAmount': {'amount': commission}}
                            for i in range(6)]))
                        shop = {'100': ShopifyOrderIdMatch('100', '2220001', original,
                                refund in ('1', '2'), refund_status=refund)}
                        index = build_index([record(supplemental, store='PETLIBRO UK', oid='2220001')]) if supplemental else DtcIndex()
                        result = enrich_awin_with_shopify(raw, shop, site='uk', dtc_index=index)
                    self.assertTrue((result['匹配情况'] == matched).all())
                    self.assertTrue((result['Action'] == action).all())
                    self.assertTrue((result['补充归因'] == (supplemental or '')).all())
                    summary_key = 'Impact' if platform == 'impact' else 'Awin-UK'
                    summary = build_match_summary_sheets({summary_key: result})[summary_key + '-Summary']
                    self.assertEqual(int(summary.iloc[0]['匹配']), 6 if matched else 0)

    def test_existing_small_partner_exception_is_separate_from_attribution(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / 'impact.csv'
            pd.DataFrame([{'OID': '2020001', 'Action Cost': '10', 'Partner': 'test'}]).to_csv(raw, index=False)
            shop = {'us': {'2020001': ShopifyOidMatch('2020001', '100', 'impact', False)}}
            result = enrich_impact_with_shopify(raw, shop, dtc_index=build_index([record('awin')]))
            self.assertEqual(result.iloc[0]['匹配情况'], '')
            self.assertEqual(result.iloc[0]['Action'], '通过')

    @patch("affiliate_report.reconcile.dtc.pymysql.connect")
    @patch.dict("os.environ", {"DTC_DATABASE_USER": "test-user", "DTC_DATABASE_PASSWORD": "test-password"})
    def test_query_is_parameterized_and_uses_env_tls_and_no_date_cutoff(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [record()]
        index = load_attribution({"us": ["2020001", "2020001"]}, key_type="oid")
        sql, params = cursor.execute.call_args.args
        self.assertNotIn("2020001", sql)
        self.assertIn("#2020001", params)
        self.assertEqual(params[0], "PETLIBRO")
        self.assertNotIn("order_updated_date >=", sql)
        self.assertNotIn("TRIM(last_visit_utm_source)", sql)
        self.assertEqual(connect.call_args.kwargs["user"], "test-user")
        self.assertEqual(connect.call_args.kwargs["ssl"].verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(len(index.by_order_id), 1)

    @patch("affiliate_report.reconcile.dtc.pymysql.connect", side_effect=pymysql.OperationalError(1045, "test-password test-user"))
    @patch.dict("os.environ", {"DTC_DATABASE_USER": "test-user", "DTC_DATABASE_PASSWORD": "test-password"})
    def test_connection_failure_is_not_silently_ignored_or_logged_with_secrets(self, connect):
        with self.assertRaises(RuntimeError) as caught:
            load_attribution({"uk": ["100"]}, key_type="order_id")
        self.assertNotIn("test-password", str(caught.exception))
        self.assertNotIn("test-user", str(caught.exception))

    @patch("affiliate_report.reconcile.dtc.pymysql.connect")
    def test_empty_input_does_not_connect(self, connect):
        self.assertEqual(load_attribution({}, key_type="oid"), DtcIndex())
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
