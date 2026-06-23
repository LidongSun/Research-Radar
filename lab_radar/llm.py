from __future__ import annotations

import json
import os
import urllib.request

from lab_radar.items import RadarItem


def enrich_with_llm(item: RadarItem) -> RadarItem:
    api_key = os.getenv("LAB_RADAR_LLM_API_KEY")
    base_url = os.getenv("LAB_RADAR_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LAB_RADAR_LLM_MODEL", "gpt-4.1-mini")
    if not api_key:
        return item

    prompt = (
        "你是 AI/机器人科研情报助手。请用中文给下面条目生成："
        "1) 一句话摘要；2) 为什么值得或不值得关注；3) 今日行动建议。"
        "总字数控制在 160 字内。\n\n"
        f"来源: {item.source}\n标题: {item.title}\n作者/所有者: {item.authors_or_owner}\n"
        f"内容: {item.abstract_or_description[:2000]}"
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        item.reason = f"{item.reason}；LLM 摘要失败: {exc}"
        return item

    content = data["choices"][0]["message"]["content"].strip()
    item.summary = content
    return item
