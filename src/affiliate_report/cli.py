from __future__ import annotations

import argparse
import sys
from pathlib import Path

from affiliate_report.models import MonthRange
from affiliate_report.platforms.awin import AwinPlatformClient
from affiliate_report.platforms.cj import CJPlatformClient
from affiliate_report.platforms.impact import ImpactPlatformClient
from affiliate_report.platforms.shopify import ShopifyPlatformClient


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Also print response status codes (request URLs always print)",
    )

    parser = argparse.ArgumentParser(
        description="Fetch and preprocess affiliate platform monthly actions reports"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", parents=[common], help="Fetch monthly actions report")
    fetch.add_argument("platform", choices=["impact", "awin", "cj", "shopify"], help="Affiliate platform")
    fetch.add_argument("--year", type=int, required=True)
    fetch.add_argument("--month", type=int, required=True, choices=range(1, 13))
    fetch.add_argument(
        "--method",
        choices=["report", "report-sync", "actions"],
        default="report",
        help="Impact only: report (ReportExport+Jobs), report-sync (/Reports/...), actions (Actions API)",
    )
    fetch.add_argument(
        "--site",
        choices=["all", "us", "de", "uk"],
        default="all",
        help="Awin/Shopify: site filter (default: all configured sites)",
    )
    fetch.add_argument(
        "--report",
        choices=["all", "sales-attribution", "cj-shopify", "impact-shopify", "awin-shopify"],
        default="all",
        help="Shopify only: report type (default: all)",
    )
    fetch.add_argument("--report-handle", help="Impact report handle override")
    fetch.add_argument(
        "--no-preprocess",
        action="store_true",
        help="Skip preprocessing step",
    )

    impact_list = sub.add_parser("impact", parents=[common], help="Impact-specific commands")
    impact_sub = impact_list.add_subparsers(dest="impact_command", required=True)
    impact_sub.add_parser("list-reports", help="List API-accessible Impact reports")
    poll = impact_sub.add_parser("poll-job", help="Poll a ReportExport job and download CSV")
    poll.add_argument("--queued-uri", help="QueuedUri from ReportExport response")
    poll.add_argument("--job-id", help="Job UUID (alternative to --queued-uri)")
    poll.add_argument(
        "--output",
        help="Output CSV path (default: data/raw/impact/job_<id>.csv)",
    )

    awin_list = sub.add_parser("awin", parents=[common], help="Awin-specific commands")
    awin_sub = awin_list.add_subparsers(dest="awin_command", required=True)
    awin_sub.add_parser("list-accounts", help="List Awin accounts accessible by API token")

    cj_list = sub.add_parser("cj", parents=[common], help="CJ-specific commands")
    cj_sub = cj_list.add_subparsers(dest="cj_command", required=True)
    cj_probe = cj_sub.add_parser("probe", help="Verify CJ token + company ID access")
    cj_probe.add_argument("--company-id", help="Override CJ_COMPANY_ID for probe")

    process = sub.add_parser("process", parents=[common], help="Reconcile / enrich platform data")
    process.add_argument("platform", choices=["impact", "cj", "awin"], help="Platform to process")
    process.add_argument("--year", type=int, required=True)
    process.add_argument("--month", type=int, required=True, choices=range(1, 13))
    process.add_argument(
        "--shopify-site",
        choices=["all", "us", "uk", "de"],
        default="all",
        help="CJ only: Shopify site(s) for sales attribution lookup (default: all)",
    )
    process.add_argument("--impact-file", type=Path, help="Override Impact raw CSV path")
    process.add_argument("--cj-file", type=Path, help="Override CJ raw JSON path")
    process.add_argument("--awin-file", type=Path, help="Override Awin raw JSON path")
    process.add_argument(
        "--site",
        choices=["all", "de", "uk"],
        default="all",
        help="Awin only: site filter (default: all)",
    )
    process.add_argument("--shopify-file", type=Path, help="Override Shopify sales attribution JSON path")
    process.add_argument("--output", type=Path, help="Override output CSV path")

    report = sub.add_parser(
        "report",
        parents=[common],
        help="Fetch all platforms, reconcile, and export monthly Excel workbook",
    )
    report.add_argument("--year", type=int, required=True)
    report.add_argument("--month", type=int, required=True, choices=range(1, 13))
    report.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip API fetch; use existing raw data under data/raw/",
    )
    report.add_argument(
        "--output",
        type=Path,
        help="Output Excel path (default: data/reports/affiliate_report_YYYY-MM.xlsx)",
    )
    report.add_argument(
        "--method",
        choices=["report", "report-sync", "actions"],
        default="report",
        help="Impact fetch method (default: report)",
    )
    report.add_argument("--report-handle", help="Impact report handle override")

    codes = sub.add_parser(
        "exclusive-codes",
        parents=[common],
        help="Manage exclusive-code approval rules CSV",
    )
    codes_sub = codes.add_subparsers(dest="codes_command", required=True)
    codes_sub.add_parser("path", help="Print local exclusive_codes.csv path")
    codes_sub.add_parser(
        "sync",
        help="Pull Feishu sheet into data/config/exclusive_codes.csv (requires FEISHU_* env)",
    )

    args = parser.parse_args(argv)
    month = MonthRange(year=args.year, month=args.month) if hasattr(args, "year") else None

    try:
        if args.command == "fetch":
            return _cmd_fetch(args, month)  # type: ignore[arg-type]
        if args.command == "process":
            return _cmd_process(args, month)  # type: ignore[arg-type]
        if args.command == "report":
            return _cmd_report(args, month)  # type: ignore[arg-type]
        if args.command == "exclusive-codes" and args.codes_command == "path":
            return _cmd_exclusive_codes_path()
        if args.command == "exclusive-codes" and args.codes_command == "sync":
            return _cmd_exclusive_codes_sync(args)
        if args.command == "impact" and args.impact_command == "list-reports":
            return _cmd_impact_list_reports(args)
        if args.command == "impact" and args.impact_command == "poll-job":
            return _cmd_impact_poll_job(args)
        if args.command == "awin" and args.awin_command == "list-accounts":
            return _cmd_awin_list_accounts(args)
        if args.command == "cj" and args.cj_command == "probe":
            return _cmd_cj_probe(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        body = getattr(exc, "body", None)
        if body:
            print(f"Details: {body}", file=sys.stderr)
        status_code = getattr(exc, "status_code", None)
        if status_code == 403 and "Reports" in str(exc):
            print(
                "Hint: enable Reports (Run/Legacy) scope on your Impact API token, "
                "or use --method report (ReportExport) instead.",
                file=sys.stderr,
            )
        if "No authorized advertiser" in str(exc) or "No authorized publisher" in str(exc):
            print(
                "Hint: check CJ_COMPANY_ID matches your CJ dashboard CID, and "
                "CJ_ACCOUNT_TYPE is advertiser or publisher as appropriate.",
                file=sys.stderr,
            )
        if "Only registered publisher users" in str(exc):
            print(
                "Hint: your token is not a publisher account. Set CJ_ACCOUNT_TYPE=advertiser.",
                file=sys.stderr,
            )
        return 1

    parser.print_help()
    return 1


def _cmd_exclusive_codes_path() -> int:
    from affiliate_report.exclusive_codes import ensure_exclusive_codes_csv

    path = ensure_exclusive_codes_csv()
    print(path)
    return 0


def _cmd_exclusive_codes_sync(args: argparse.Namespace) -> int:
    from affiliate_report.exclusive_codes import sync_exclusive_codes_from_feishu

    path = sync_exclusive_codes_from_feishu()
    if args.verbose:
        print(f"Synced exclusive codes -> {path}")
    else:
        print(path)
    return 0


def _cmd_report(args: argparse.Namespace, month: MonthRange) -> int:
    from affiliate_report.pipeline.monthly_report import build_monthly_report

    result = build_monthly_report(
        month,
        output_path=args.output,
        skip_fetch=args.skip_fetch,
        verbose=args.verbose,
        impact_method=args.method,
        impact_report_handle=args.report_handle,
    )
    print(f"Monthly workbook saved: {result.output_path}")
    for sheet_name, source in result.sheet_sources.items():
        if isinstance(source, Path):
            print(f"  {sheet_name}: {source}")
        else:
            print(f"  {sheet_name}: ({len(source)} rows)")
    return 0


def _cmd_process(args: argparse.Namespace, month: MonthRange) -> int:
    if args.platform == "impact":
        from affiliate_report.reconcile.impact import process_impact_month

        out = process_impact_month(
            month.label,
            impact_path=args.impact_file,
            shopify_path=args.shopify_file,
            output_path=args.output,
        )
        print(f"Enriched Impact report saved: {out}")
        return 0

    if args.platform == "cj":
        from affiliate_report.reconcile.cj import process_cj_month

        out = process_cj_month(
            month.label,
            cj_path=args.cj_file,
            shopify_path=args.shopify_file,
            shopify_site=args.shopify_site,
            output_path=args.output,
        )
        print(f"Enriched CJ report saved: {out}")
        return 0

    if args.platform == "awin":
        from affiliate_report.reconcile.awin import process_awin_month

        paths = process_awin_month(
            month.label,
            site=args.site,
            awin_path=args.awin_file,
            shopify_path=args.shopify_file,
            output_path=args.output,
        )
        for site_label, path in sorted(paths.items()):
            print(f"Enriched Awin report saved ({site_label}): {path}")
        return 0

    print(f"Platform '{args.platform}' process not implemented yet.", file=sys.stderr)
    return 1


def _cmd_fetch(args: argparse.Namespace, month: MonthRange) -> int:
    if args.platform == "impact":
        return _cmd_fetch_impact(args, month)
    if args.platform == "awin":
        return _cmd_fetch_awin(args, month)
    if args.platform == "cj":
        return _cmd_fetch_cj(args, month)
    if args.platform == "shopify":
        return _cmd_fetch_shopify(args, month)
    print(f"Platform '{args.platform}' not implemented yet.", file=sys.stderr)
    return 1


def _cmd_fetch_impact(args: argparse.Namespace, month: MonthRange) -> int:
    client = ImpactPlatformClient(verbose=args.verbose)
    if args.no_preprocess:
        raw = client.fetch_monthly_actions(
            month,
            method=args.method,
            report_handle=args.report_handle,
        )
        print(f"Raw report saved: {raw}")
        return 0

    raw, processed = client.fetch_and_preprocess(
        month,
        method=args.method,
        report_handle=args.report_handle,
    )
    print(f"Raw report saved:      {raw}")
    print(f"Processed report saved: {processed}")
    return 0


def _cmd_fetch_awin(args: argparse.Namespace, month: MonthRange) -> int:
    site = None if args.site == "all" else args.site
    client = AwinPlatformClient(verbose=args.verbose)

    if args.no_preprocess:
        raw_paths = client.fetch_monthly_actions_by_site(month, site=site)
        for site_label, path in sorted(raw_paths.items()):
            print(f"Raw report saved ({site_label}): {path}")
        return 0

    raw_paths, processed_paths = client.fetch_and_preprocess(month, site=site)
    for site_label in sorted(raw_paths):
        print(f"Raw report saved ({site_label}):      {raw_paths[site_label]}")
        print(f"Processed report saved ({site_label}): {processed_paths[site_label]}")
    return 0


def _cmd_fetch_cj(args: argparse.Namespace, month: MonthRange) -> int:
    client = CJPlatformClient(verbose=args.verbose)

    if args.no_preprocess:
        raw = client.fetch_monthly_actions(month)
        print(f"Raw report saved: {raw}")
        return 0

    raw, processed = client.fetch_and_preprocess(month)
    print(f"Raw report saved:      {raw}")
    print(f"Processed report saved: {processed}")
    return 0


def _cmd_fetch_shopify(args: argparse.Namespace, month: MonthRange) -> int:
    site = None if args.site == "all" else args.site
    reports = (args.report,) if args.report != "all" else ("all",)
    client = ShopifyPlatformClient(verbose=args.verbose)

    if args.no_preprocess:
        raw_paths = client.fetch_monthly_reports_by_site(month, site=site, reports=reports)
        for key, path in sorted(raw_paths.items()):
            print(f"Raw report saved ({key}): {path}")
        return 0

    raw_paths, processed_paths = client.fetch_and_preprocess(month, site=site, reports=reports)
    for key in sorted(raw_paths):
        print(f"Raw report saved ({key}):      {raw_paths[key]}")
        print(f"Processed report saved ({key}): {processed_paths[key]}")
    return 0


def _cmd_cj_probe(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from affiliate_report.platforms.cj.config import CJConfig

    config = CJConfig.from_env(require_company_id=False)
    company_id = args.company_id or config.company_id
    if not company_id:
        print("Provide --company-id or set CJ_COMPANY_ID in .env", file=sys.stderr)
        return 1
    config = replace(config, company_id=company_id)

    client = CJPlatformClient(config=config, verbose=args.verbose)
    result = client.probe_access(company_id=company_id)
    print(f"Account type: {result['account_type']}")
    print(f"Company ID:   {result['company_id']}")
    print(f"Probe count:  {result['count']}")
    if result.get("sample_name"):
        print(f"Sample name:  {result['sample_name']}")
    if result["count"] == 0:
        print(
            "Token accepted but no records in probe window. "
            "CID may be wrong, or there were no commissions on 2026-01-01.",
        )
    return 0


def _cmd_impact_poll_job(args: argparse.Namespace) -> int:
    from pathlib import Path

    from affiliate_report.config import ImpactConfig, ensure_data_dirs
    from affiliate_report.platforms.impact.client import ImpactClient

    cfg = ImpactConfig.from_env()
    queued_uri = args.queued_uri
    if not queued_uri and args.job_id:
        prefix = "Advertisers" if cfg.account_type == "advertiser" else "Mediapartners"
        queued_uri = f"/{prefix}/{cfg.account_sid}/Jobs/{args.job_id}.json"
    if not queued_uri:
        print("Provide --queued-uri or --job-id", file=sys.stderr)
        return 1

    with ImpactClient(
        cfg.account_sid,
        cfg.auth_token,
        account_type=cfg.account_type,
        verbose=getattr(args, "verbose", False),
    ) as http:
        job = http.poll_job_until_complete(queued_uri)
        data = http.download_job_result(job)

    raw_dir, _ = ensure_data_dirs("impact")
    job_id = queued_uri.split("/Jobs/")[-1].replace(".json", "")
    out = Path(args.output) if args.output else raw_dir / f"job_{job_id}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"Downloaded: {out} ({len(data)} bytes)")
    return 0


def _cmd_impact_list_reports(args: argparse.Namespace) -> int:
    client = ImpactPlatformClient(verbose=args.verbose)
    reports = client.list_reports()
    if not reports:
        print("No API-accessible reports found.")
        return 0

    print(f"{'Handle':<40} {'Name'}")
    print("-" * 80)
    for report in sorted(reports, key=lambda r: r.get("Name", "")):
        handle = report.get("Id", "")
        name = report.get("Name", "")
        category = report.get("Category", "")
        suffix = f" [{category}]" if category else ""
        print(f"{handle:<40} {name}{suffix}")
    return 0


def _cmd_awin_list_accounts(args: argparse.Namespace) -> int:
    client = AwinPlatformClient(verbose=args.verbose)
    accounts = client.list_accounts()
    if not accounts:
        print("No Awin accounts found for this token.")
        return 0

    print(f"{'Account ID':<12} {'Type':<12} {'Name'}")
    print("-" * 72)
    for account in sorted(accounts, key=lambda a: a.get("accountName", "")):
        account_id = account.get("accountId", "")
        account_type = account.get("accountType", "")
        name = account.get("accountName", "")
        print(f"{account_id:<12} {account_type:<12} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
