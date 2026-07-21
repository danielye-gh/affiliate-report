# Affiliate Report — Windows 使用说明

简明指南：解压 → 安装一次 → 以后用 `report.bat` 出报告。  
也可以把本说明上传给 ChatGPT，让它根据你的中文描述告诉你该运行哪条命令。

---

## 你需要准备

1. **Windows 10/11**
2. **Python 3.9+**  
   下载：https://www.python.org/downloads/  
   安装时建议勾选 **「Add python.exe to PATH」**；未勾选时 Windows 仍可用 **`py`** 启动器（`setup.bat` 会自动识别 `py` 或 `python`）
3. **API 凭证**（`.env` 文件，由管理员单独发放或从 `.env.example` 填写）

---

## 第一次使用（只需做一次）

1. 解压收到的 `affiliate-report` 文件夹到任意位置（例如 `C:\Users\你的名字\affiliate-report`）
2. **确认文件夹里没有 `.venv` 目录**（虚拟环境不能从别人电脑拷贝，必须在本地重新创建）
3. 双击 **`setup.bat`**
4. 用记事本打开 **`.env`**，填入各平台 API 密钥（若管理员已放好可跳过）
5. 看到「安装完成」即可

---

## 生成月度报告

### 方式一：图形界面（推荐）

**直接双击 `report.bat`**，会弹出窗口：

1. 选择 **年份**、**月份**（默认上个月）
2. 如需跳过 API 拉取，勾选「跳过 API 拉取」
3. 点击 **生成报告**，在确认框中点「是」
4. 等待日志跑完；成功后可选 **打开所在文件夹**

#### 独家 Code 审批配置

- 本地文件：`data\config\exclusive_codes.csv`（可用 Excel / 记事本离线编辑；**含真实媒体与折扣码，不随公开仓库分发**）
- 首次运行若没有该文件，会从 `data\config\exclusive_codes.example.csv` 复制一份占位配置，请改成真实规则或用飞书同步覆盖
- GUI **打开配置CSV**：直接编辑本地表
- GUI **更新独家Code**：用飞书线上表覆盖本地 CSV（需在 `.env` 配置 `FEISHU_*`；不配也能离线用）

审批规则（仅 CSV 中列出的媒体）：匹配且未退款，或使用了独家 code → `通过`；否则 → `取消`。

### 方式二：命令行（高级）

在项目文件夹地址栏输入 `cmd` 回车，例如：

```bat
report.bat 2026 5
```

### 输出文件

```
data\reports\Affiliate_report_2026_05.xlsx
```

文件名规则：`Affiliate_report_年份_月份.xlsx`（月份两位，如 05）

### 已有原始数据、跳过 API 拉取

若 `data\raw\` 里已有当月数据，可加 `skip`：

```bat
report.bat 2026 5 skip
```

---

## 在线更新程序

程序更新后，无需重新下载整个压缩包：

- **图形界面**：双击 `report.bat`，点击 **在线更新** 按钮，确认后等待完成，然后重启程序
- **命令行**：`report.bat update`

更新会从 GitHub 下载最新代码覆盖本地程序文件，**不会改动**：

- `.env`（你的 API 密钥）
- `data\` 目录（报表、原始数据、独家Code配置）
- `.venv\` 虚拟环境

若依赖有变化会自动重新安装。更新失败时请检查网络，或联系管理员确认 `.env` 中的 `UPDATE_REPO` 配置。

---

## 和 ChatGPT 配合使用

ChatGPT **不能**在你的电脑上自动运行程序，但可以帮你「翻译」自然语言：

| 你说的话 | ChatGPT 应告诉你 |
|----------|------------------|
| 出 26 年 5 月报告 | 双击 `report.bat`，选 2026 年、5 月，点生成 |
| 生成 2026 年 5 月审单表 | 同上 |
| 5 月报告，数据已经有了 | 图形界面勾选「跳过 API 拉取」；或命令行 `report.bat 2026 5 skip` |

把本文件 + `README.md` 上传到 Custom GPT 的 Knowledge，效果更好。

---

## Excel 包含 14 个工作表

| Sheet | 内容 |
|-------|------|
| Impact-Summary | Impact 按 Partner 匹配汇总 |
| CJ-Summary | CJ 按 Website Name 匹配汇总 |
| Awin-DE-Summary | Awin DE 按 publisher 匹配汇总 |
| Awin-UK-Summary | Awin UK 按 publisher 匹配汇总 |
| Impact / CJ / Awin-DE / Awin-UK | 各平台对账明细 |
| sales_attribution-us/de/uk | Shopify 全量订单 |
| cj-shopify / impact-shopify / awin-shopify | 联盟订单 |

---

## 常见问题

### 提示「未找到 Python」

重新安装 Python，勾选 **Add python.exe to PATH**（或确认 `py --version` 有输出），然后重新打开 cmd 再运行 `setup.bat`。

### 提示「尚未安装」

先双击运行 `setup.bat`。

### 报告生成失败

- 检查 `.env` 里各平台密钥是否完整
- 确认电脑能访问外网（需调用 Impact / CJ / Awin / Shopify API）
- 把完整报错信息发给管理员

### 提示找不到 `C:\Users\某人\...\python.exe`（虚拟环境路径错误）

**原因：** 把整个项目文件夹（含 `.venv`）从另一台电脑拷贝过来了。虚拟环境里写死了那台电脑上的 Python 路径，换机器后不能用。

**处理：**

1. 删除项目里的 **`.venv` 文件夹**
2. 重新双击 **`setup.bat`**（会在本机用你自己的 Python 重建环境）

新版 `setup.bat` 也会自动检测并重建损坏的 `.venv`；若仍报错，手动删掉 `.venv` 再运行一次即可。

### setup.bat 安装时出现 SSL / pip 报错

多为访问 PyPI 官方源不稳定。`setup.bat` 已默认使用 **清华镜像**；若仍失败：

1. 确认能打开 https://pypi.tuna.tsinghua.edu.cn
2. 在公司网络/代理环境下，可能需要配置系统代理或联系 IT
3. 手动安装：在项目目录打开 cmd，执行：
   ```bat
   .venv\Scripts\python.exe -m pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

### zip 里应包含什么

- `src/`、`pyproject.toml`、`requirements.txt`
- `setup.bat`、`report.bat`、本说明、`README.md`
- `.env.example`（**不要**把含真实密钥的 `.env` 打进公开 zip）
- **不要**包含 `.venv/`（每台电脑本地运行 `setup.bat` 生成）

---

## 打包（管理员用）

> **维护批处理脚本：** `setup.bat` / `report.bat` 为纯英文 ASCII，避免 CMD 乱码。修改请编辑 `scripts/build-windows-bats.ps1` 后执行：
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File scripts\build-windows-bats.ps1
> ```

在 Mac 上打包示例：

```bash
cd affiliate-report
zip -r affiliate-report-windows.zip \
  src pyproject.toml requirements.txt README.md .env.example \
  setup.bat report.bat Windows使用说明.md scripts/build-windows-bats.ps1 \
  data/config/exclusive_codes.example.csv \
  -x "*.pyc" -x "*__pycache__*" -x "*.egg-info*" -x ".venv/*"
```

`.env` 与真实的 `data/config/exclusive_codes.csv` 通过安全渠道单独发送。
