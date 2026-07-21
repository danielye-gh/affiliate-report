from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import tkinter as tk
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk

from affiliate_report.config import DATA_DIR, PROJECT_ROOT
from affiliate_report.exclusive_codes import EXCLUSIVE_CODES_CSV, ensure_exclusive_codes_csv
from affiliate_report.models import MonthRange


class _GuiLogStream(io.TextIOBase):
    """Stream stdout/stderr to the GUI log widget in real time."""

    def __init__(self, append_fn) -> None:
        self._append = append_fn

    def write(self, text: str) -> int:
        if text:
            self._append(text)
        return len(text)

    def flush(self) -> None:
        pass


def default_report_period() -> tuple[int, int]:
    """Default to previous calendar month (typical affiliate close)."""
    today = date.today()
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def report_output_path(year: int, month: int) -> Path:
    return DATA_DIR / "reports" / f"Affiliate_report_{year}_{month:02d}.xlsx"


def open_path(path: Path) -> None:
    target = str(path.resolve())
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", target], check=False)
    else:
        subprocess.run(["xdg-open", target], check=False)


def open_folder(path: Path) -> None:
    open_path(path if path.is_dir() else path.parent)


class ReportApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("联盟审单报告")
        self.resizable(False, False)
        self._running = False

        default_year, default_month = default_report_period()

        pad = {"padx": 12, "pady": 6}
        frame = ttk.Frame(self, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="选择报告月份", font=("", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Label(frame, text="年份").grid(row=1, column=0, sticky="w", **pad)
        self.year_var = tk.StringVar(value=str(default_year))
        years = [str(y) for y in range(date.today().year - 3, date.today().year + 2)]
        ttk.Combobox(
            frame,
            textvariable=self.year_var,
            values=years,
            width=10,
            state="readonly",
        ).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(frame, text="月份").grid(row=2, column=0, sticky="w", **pad)
        self.month_var = tk.StringVar(value=str(default_month))
        ttk.Combobox(
            frame,
            textvariable=self.month_var,
            values=[str(m) for m in range(1, 13)],
            width=10,
            state="readonly",
        ).grid(row=2, column=1, sticky="w", **pad)

        self.skip_fetch_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="跳过 API 拉取（使用已有 data/raw 数据）",
            variable=self.skip_fetch_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=4)

        self.output_label = ttk.Label(frame, text="", foreground="gray")
        self.output_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=12)
        self._refresh_output_hint()

        self.config_label = ttk.Label(frame, text="", foreground="gray")
        self.config_label.grid(row=5, column=0, columnspan=2, sticky="w", padx=12)
        self._refresh_config_hint()

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=6, column=0, columnspan=2, pady=(12, 8))
        self.run_btn = ttk.Button(btn_row, text="生成报告", command=self._on_generate)
        self.run_btn.pack(side=tk.LEFT, padx=4)
        self.sync_btn = ttk.Button(
            btn_row, text="更新独家Code", command=self._on_sync_exclusive_codes
        )
        self.sync_btn.pack(side=tk.LEFT, padx=4)
        self.open_csv_btn = ttk.Button(
            btn_row, text="打开配置CSV", command=self._on_open_exclusive_codes
        )
        self.open_csv_btn.pack(side=tk.LEFT, padx=4)
        self.update_btn = ttk.Button(btn_row, text="在线更新", command=self._on_update)
        self.update_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="关闭", command=self.destroy).pack(side=tk.LEFT, padx=4)

        ttk.Label(frame, text="运行日志").grid(row=7, column=0, columnspan=2, sticky="w", padx=12)
        self.log = tk.Text(frame, width=58, height=12, state=tk.DISABLED, wrap=tk.WORD)
        self.log.grid(row=8, column=0, columnspan=2, padx=12, pady=(4, 0))

        self.year_var.trace_add("write", lambda *_: self._refresh_output_hint())
        self.month_var.trace_add("write", lambda *_: self._refresh_output_hint())

    def _refresh_output_hint(self) -> None:
        year, month = self._parse_period()
        if year is None or month is None:
            self.output_label.config(text="")
            return
        path = report_output_path(year, month)
        self.output_label.config(text=f"输出：{path.relative_to(PROJECT_ROOT)}")

    def _refresh_config_hint(self) -> None:
        path = ensure_exclusive_codes_csv()
        try:
            rel = path.relative_to(PROJECT_ROOT)
        except ValueError:
            rel = path
        self.config_label.config(text=f"独家Code配置：{rel}（可离线编辑）")

    def _parse_period(self) -> tuple[int | None, int | None]:
        try:
            year = int(self.year_var.get())
            month = int(self.month_var.get())
        except ValueError:
            return None, None
        if not (1 <= month <= 12):
            return None, None
        return year, month

    def _append_log(self, text: str) -> None:
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _append_log_threadsafe(self, text: str) -> None:
        self.after(0, lambda t=text: self._append_log(t))

    def _set_running(self, running: bool) -> None:
        self._running = running
        state = tk.DISABLED if running else tk.NORMAL
        self.run_btn.config(state=state)
        self.sync_btn.config(state=state)
        self.open_csv_btn.config(state=state)
        self.update_btn.config(state=state)

    def _on_open_exclusive_codes(self) -> None:
        path = ensure_exclusive_codes_csv()
        open_path(path)

    def _on_sync_exclusive_codes(self) -> None:
        if self._running:
            return
        if not messagebox.askyesno(
            "更新独家Code",
            "将用飞书线上表格覆盖本地 CSV：\n"
            f"{EXCLUSIVE_CODES_CSV.relative_to(PROJECT_ROOT)}\n\n"
            "未配置飞书凭证时可直接编辑该 CSV。是否继续？",
        ):
            return

        self._set_running(True)
        self._append_log("开始从飞书更新独家Code配置...\n")
        thread = threading.Thread(target=self._run_sync_exclusive_codes, daemon=True)
        thread.start()

    def _run_sync_exclusive_codes(self) -> None:
        from affiliate_report.exclusive_codes import sync_exclusive_codes_from_feishu

        stream = _GuiLogStream(self._append_log_threadsafe)
        exit_code = 0
        result_path: Path | None = None
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                result_path = sync_exclusive_codes_from_feishu()
                print(f"Updated: {result_path}")
        except Exception as exc:
            exit_code = 1
            self._append_log_threadsafe(f"\nError: {exc}\n")

        self.after(0, lambda: self._on_sync_finished(exit_code, result_path))

    def _on_sync_finished(self, exit_code: int, result_path: Path | None) -> None:
        self._set_running(False)
        self._refresh_config_hint()
        if exit_code == 0 and result_path is not None:
            self._append_log(f"\n独家Code已更新：{result_path}\n")
            messagebox.showinfo("更新成功", f"已写入本地 CSV：\n{result_path}")
        else:
            self._append_log("\n更新失败。可离线编辑 data/config/exclusive_codes.csv。\n")
            messagebox.showerror(
                "更新失败",
                "飞书同步失败。请检查 .env 中 FEISHU_APP_ID / FEISHU_APP_SECRET / "
                "FEISHU_EXCLUSIVE_CODES_URL，以及表格是否已分享给该应用。\n\n"
                "也可直接编辑 data/config/exclusive_codes.csv 后生成报告。",
            )

    def _on_update(self) -> None:
        if self._running:
            return
        if not messagebox.askyesno(
            "在线更新",
            "将从 GitHub 下载最新版本并覆盖本地程序文件。\n\n"
            "不会改动：.env 凭证、data 目录（报表、原始数据、独家Code配置）。\n\n"
            "是否继续？",
        ):
            return

        self._set_running(True)
        self._append_log("开始在线更新...\n")
        thread = threading.Thread(target=self._run_update, daemon=True)
        thread.start()

    def _run_update(self) -> None:
        from affiliate_report.updater import run_update

        stream = _GuiLogStream(self._append_log_threadsafe)
        exit_code = 0
        changed_count = 0
        error_msg = ""
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                changed_count = len(run_update(log=stream.write))
        except Exception as exc:
            exit_code = 1
            error_msg = str(exc)
            self._append_log_threadsafe(f"\nError: {exc}\n")

        self.after(0, lambda: self._on_update_finished(exit_code, changed_count, error_msg))

    def _on_update_finished(self, exit_code: int, changed_count: int, error_msg: str) -> None:
        self._set_running(False)
        if exit_code != 0:
            messagebox.showerror(
                "更新失败",
                f"在线更新失败：\n{error_msg}\n\n"
                "请检查网络连接，或联系管理员。",
            )
        elif changed_count == 0:
            messagebox.showinfo("已是最新", "本地已是最新版本，无需更新。")
        else:
            messagebox.showinfo(
                "更新完成",
                f"已更新 {changed_count} 个文件。\n\n"
                "请关闭本窗口后重新打开 report.bat 以使用新版本。",
            )

    def _on_generate(self) -> None:
        if self._running:
            return

        year, month = self._parse_period()
        if year is None or month is None:
            messagebox.showerror("输入错误", "请选择有效的年份和月份（1–12）。")
            return

        output = report_output_path(year, month)
        skip = self.skip_fetch_var.get()
        mode = "跳过拉取，仅对账导出" if skip else "拉取各平台数据 + 对账 + 导出"
        if not messagebox.askyesno(
            "确认生成",
            f"即将生成 {year} 年 {month} 月报告。\n\n"
            f"模式：{mode}\n"
            f"输出：{output.name}\n\n"
            "是否继续？",
        ):
            return

        self.log.config(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.config(state=tk.DISABLED)
        self._set_running(True)
        self._append_log(f"开始生成 {year}-{month:02d} 报告...\n\n")

        thread = threading.Thread(
            target=self._run_report,
            args=(year, month, output, skip),
            daemon=True,
        )
        thread.start()

    def _run_report(self, year: int, month: int, output: Path, skip_fetch: bool) -> None:
        from affiliate_report.pipeline.monthly_report import build_monthly_report

        ensure_exclusive_codes_csv()
        output.parent.mkdir(parents=True, exist_ok=True)
        stream = _GuiLogStream(self._append_log_threadsafe)
        exit_code = 0
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                build_monthly_report(
                    MonthRange(year=year, month=month),
                    output_path=output,
                    skip_fetch=skip_fetch,
                    verbose=True,
                )
        except Exception as exc:
            exit_code = 1
            self._append_log_threadsafe(f"\nError: {exc}\n")

        self.after(0, lambda: self._on_finished(exit_code, output))

    def _on_finished(self, exit_code: int, output: Path) -> None:
        self._set_running(False)

        if exit_code == 0 and output.is_file():
            self._append_log(f"\n完成：{output}\n")
            if messagebox.askyesno("生成成功", f"报告已保存：\n{output}\n\n是否打开所在文件夹？"):
                open_folder(output.parent)
        else:
            self._append_log("\n生成失败，请查看上方日志。\n")
            messagebox.showerror(
                "生成失败",
                "报告生成失败。请检查 .env 凭证、网络连接及日志中的错误信息。",
            )


def _preflight() -> str | None:
    if not (PROJECT_ROOT / ".env").is_file():
        return "未找到 .env 配置文件。\n请先运行 setup.bat 并填入 API 凭证。"
    return None


def main() -> int:
    err = _preflight()
    if err:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("无法启动", err)
        return 1

    ensure_exclusive_codes_csv()
    app = ReportApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
