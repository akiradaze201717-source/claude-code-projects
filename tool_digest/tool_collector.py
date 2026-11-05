"""
工具・DIY系ブログネタ自動収集ツール
- Reddit公開JSON + RSSフィードから工具・DIY・機械加工の話題を収集
- Obsidianのブログ下書きフォルダにMarkdownで保存
- アカウント登録・APIキー不要・完全無料

使い方:
  python tool_collector.py           # Obsidianに保存
  python tool_collector.py --dry-run # 保存せずstdoutに出力
"""

import json
import logging
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 依存パッケージチェック ──────────────────────────────────
try:
    import requests
except ImportError:
    print("requests が未インストールです: pip install requests")
    sys.exit(1)

try:
    import feedparser
except ImportError:
    print("feedparser が未インストールです: pip install feedparser")
    sys.exit(1)

# ── 設定読み込み ────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"config.json が見つかりません: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── ロギング ────────────────────────────────────────────────
logging.basicConfig(
    filename=Path(__file__).parent / "tool_digest.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)

JST = timezone(timedelta(hours=9))

# ── キーワード（関連度スコアリング用）──────────────────────
TOOL_KEYWORDS = [
    "tool",
    "tools",
    "drill",
    "saw",
    "grinder",
    "lathe",
    "mill",
    "cnc",
    "wrench",
    "socket",
    "ratchet",
    "torque",
    "welder",
    "welding",
    "router",
    "jig",
    "clamp",
    "workbench",
    "vise",
    "bandsaw",
    "tablesaw",
    "dewalt",
    "makita",
    "milwaukee",
    "bosch",
    "festool",
    "snap-on",
    "harbor freight",
    "craftsman",
    "ridgid",
    "metabo",
    "手工具",
    "電動工具",
    "工具",
    "旋盤",
    "フライス",
    "溶接",
]


# ── データ構造 ──────────────────────────────────────────────
@dataclass
class Post:
    title: str
    url: str
    source: str
    score: int = 0
    comments: int = 0
    relevance: int = field(default=0, repr=False)

    def amazon_search_url(self) -> str:
        # タイトルから工具名を抽出してAmazon検索URLを生成
        words = re.findall(r"[A-Za-z0-9぀-鿿]+", self.title)
        query = " ".join(words[:5])
        return f"https://www.amazon.co.jp/s?k={urllib.parse.quote(query)}"


# ── Reddit収集 ─────────────────────────────────────────────
REDDIT_HEADERS = {"User-Agent": "tool_digest/1.0 (personal blog research)"}


def fetch_reddit(subreddit: str, limit: int, min_score: int) -> list[Post]:
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    try:
        resp = requests.get(url, headers=REDDIT_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.warning(f"Reddit r/{subreddit} 取得失敗: {e}")
        return []

    posts = []
    for item in data.get("data", {}).get("children", []):
        d = item.get("data", {})
        title = d.get("title", "")
        score = d.get("score", 0)
        if score < min_score:
            continue
        permalink = "https://www.reddit.com" + d.get("permalink", "")
        ext_url = d.get("url", permalink)
        # 外部リンクがある場合はそちらを優先、Reddit内リンクはpermalinkを使用
        link = ext_url if not ext_url.startswith("https://www.reddit.com/r/") else permalink
        post = Post(
            title=title,
            url=link,
            source=f"r/{subreddit}",
            score=score,
            comments=d.get("num_comments", 0),
            relevance=calc_relevance(title),
        )
        posts.append(post)

    time.sleep(1)  # Reddit レート制限対策
    return posts


# ── RSS収集 ────────────────────────────────────────────────
def fetch_rss(feed_url: str) -> list[Post]:
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        logging.warning(f"RSS取得失敗 {feed_url}: {e}")
        return []

    source = feed.feed.get("title", feed_url)
    posts = []
    for entry in feed.entries[:10]:
        title = entry.get("title", "")
        link = entry.get("link", "")
        relevance = calc_relevance(title)
        if relevance == 0:
            continue  # 工具と無関係な記事はRSSでは除外
        posts.append(
            Post(
                title=title,
                url=link,
                source=source,
                relevance=relevance,
            )
        )
    return posts


# ── 関連度スコア ────────────────────────────────────────────
def calc_relevance(text: str) -> int:
    lower = text.lower()
    return sum(1 for kw in TOOL_KEYWORDS if kw in lower)


# ── Obsidian Markdown生成 ───────────────────────────────────
def build_markdown(posts: list[Post], date: datetime) -> str:
    date_str = date.strftime("%Y-%m-%d")
    ts = date.strftime("%Y-%m-%dT%H:%M:%S")

    lines = [
        "---",
        f"dateCreated: {ts}",
        "tags:",
        "  - blog-draft",
        "  - tools",
        "status: 下書き",
        "---",
        "",
        f"# 【下書き】{date_str} 工具・DIY 注目ネタ",
        "",
        f"> 収集件数: {len(posts)}件  |  収集日時: {ts}",
        "> このファイルを元に自分の言葉でブログ記事を書いてください。",
        "",
        "---",
        "",
    ]

    for i, p in enumerate(posts, 1):
        lines += [
            f"## {i}. {p.title}",
            "",
            f"- **ソース**: {p.source}",
            f"- **元URL**: {p.url}",
            f"- **Amazon検索**: {p.amazon_search_url()}",
        ]
        if p.score > 0:
            lines += [
                f"- **スコア**: {p.score}  |  **コメント**: {p.comments}",
            ]
        lines += ["", "<!-- ここに自分のコメント・メモを書く -->", "", "---", ""]

    return "\n".join(lines)


# ── 保存 ───────────────────────────────────────────────────
def save_to_obsidian(content: str, obsidian_path: str, date: datetime) -> Path:
    folder = Path(obsidian_path)
    folder.mkdir(parents=True, exist_ok=True)
    filename = folder / f"{date.strftime('%Y-%m-%d')}_tool-digest.md"
    filename.write_text(content, encoding="utf-8")
    return filename


# ── メイン ─────────────────────────────────────────────────
def main() -> None:
    dry_run = "--dry-run" in sys.argv
    config = load_config()
    now = datetime.now(JST)

    all_posts: list[Post] = []

    # Reddit収集
    for sub in config.get("subreddits", []):
        posts = fetch_reddit(
            sub,
            limit=config.get("posts_per_sub", 15),
            min_score=config.get("min_score", 50),
        )
        logging.info(f"r/{sub}: {len(posts)}件取得")
        all_posts.extend(posts)

    # RSS収集
    for feed_url in config.get("rss_feeds", []):
        posts = fetch_rss(feed_url)
        logging.info(f"RSS {feed_url}: {len(posts)}件取得")
        all_posts.extend(posts)

    # 重複URL除去 → 関連度・スコア降順
    seen: set[str] = set()
    unique: list[Post] = []
    for p in all_posts:
        if p.url not in seen:
            seen.add(p.url)
            unique.append(p)

    unique.sort(key=lambda p: (p.relevance, p.score), reverse=True)

    if not unique:
        print("収集できた記事が0件でした。ネットワーク接続を確認してください。")
        logging.warning("収集結果0件")
        return

    content = build_markdown(unique, now)

    if dry_run:
        print(content)
        return

    saved_path = save_to_obsidian(content, config["obsidian_path"], now)
    print(f"保存しました: {saved_path}")
    print(f"収集件数: {len(unique)}件")
    logging.info(f"保存完了: {saved_path} ({len(unique)}件)")


if __name__ == "__main__":
    main()
