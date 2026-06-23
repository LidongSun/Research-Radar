# Lab Radar

Lab Radar 是一个本地优先的研究情报助手，面向 AI 与机器人方向研究者。它会跟踪论文、开源项目和模型平台内容，根据你的研究画像进行相关性、时效性和行动价值评分，并生成精简的每日 Markdown 报告。

## 当前 MVP 功能

- arXiv 论文搜索
- GitHub 仓库搜索
- Hugging Face 模型搜索
- SQLite 本地缓存与去重
- 基于规则的相关性、新颖性和行动评分
- 每日 Markdown 报告生成
- 支持来源、类别和日期筛选的本地仪表盘
- 历史日报浏览
- 仪表盘内置开放学术索引检索
- 已保存、已读、待读文献库视图
- 研究想法和实验线索积压列表
- 将文献检索结果保存到本地文献库
- 通过 OpenAI 兼容 API 接入可选 LLM 摘要

## 快速开始

在仓库根目录运行：

```powershell
python main.py run-daily
```

生成的报告会写入：

```text
reports/YYYY-MM-DD.md
```

默认配置文件位于：

```text
config.yaml
```

## 可选 LLM 配置

Lab Radar 不依赖 LLM 也可以运行。如需启用 LLM 摘要，请设置以下环境变量：

```powershell
$env:LAB_RADAR_LLM_BASE_URL="https://api.openai.com/v1"
$env:LAB_RADAR_LLM_API_KEY="your_api_key"
$env:LAB_RADAR_LLM_MODEL="gpt-4.1-mini"
```

然后运行：

```powershell
python main.py run-daily --use-llm
```

## 常用命令

```powershell
python main.py run-daily
python main.py run-daily --date 2026-05-29
python main.py show-config
python main.py serve
```

- `run-daily`：抓取、评分、入库并生成每日报告。
- `show-config`：以 JSON 格式打印解析后的配置。
- `serve`：启动本地仪表盘。

## 文献检索

仪表盘包含集成的文献检索面板，可直接查询开放学术索引：

- arXiv
- OpenAlex
- Crossref
- Semantic Scholar
- PubMed
- Europe PMC

它也会生成外部检索链接，用于访问需要登录或 API Key 的来源：

- Google Scholar
- IEEE Xplore
- ScienceDirect
- ACM Digital Library
- SpringerLink
- Wiley Online Library
- DBLP
- Connected Papers

本地仪表盘地址：

```text
http://127.0.0.1:8765
```

在 Windows 上，也可以使用脚本启动并保持仪表盘窗口：

```powershell
.\run_dashboard.ps1
```

如果 `8765` 端口已被占用，请指定其他端口：

```powershell
.\run_dashboard.ps1 8766
```

## 说明

当前版本优先保持小而可靠的本地流程，而不是一次性构建复杂仪表盘。后续阶段计划加入 FastAPI + React 界面，用于阅读、筛选、保存内容以及维护研究想法积压列表。
