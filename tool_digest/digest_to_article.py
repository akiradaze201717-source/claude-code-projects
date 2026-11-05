"""
digest_to_article.py
最新の tool-digest.md からスコア最上位の1件を選び、
日本語ブログ記事の下書き Markdown を同フォルダに生成する。

使い方:
  python digest_to_article.py
"""

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests が未インストールです: pip install requests")
    sys.exit(1)

try:
    from deep_translator import GoogleTranslator
except ImportError:
    print("deep-translator が未インストールです: pip install deep-translator")
    sys.exit(1)

CONFIG_PATH = Path(__file__).parent / "config.json"
JST = timezone(timedelta(hours=9))
REDDIT_HEADERS = {"User-Agent": "tool_digest/1.0 (personal blog research)"}


@dataclass
class Post:
    title: str
    source: str
    url: str
    amazon_url: str
    score: int
    comments: int


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"config.json が見つかりません: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def strip_obsidian_links(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\[\[([^\[\]]*)\]\]", r"\1", text)
    return text


def parse_digest(path: Path) -> list[Post]:
    raw = path.read_text(encoding="utf-8")
    text = strip_obsidian_links(raw)

    posts = []
    blocks = re.split(r"\n(?=## \d+\.)", text)

    for block in blocks:
        title_m = re.match(r"## \d+\.\s+(.+)", block)
        if not title_m:
            continue
        title = title_m.group(1).strip()

        source = _field(block, r"\*\*ソース\*\*[:：]\s*(.+)")
        url = _field(block, r"\*\*元URL\*\*[:：]\s*(\S+)")
        amazon = _field(block, r"\*\*Amazon検索\*\*[:：]\s*(\S+)")
        score_m = re.search(r"\*\*スコア\*\*[:：]\s*(\d+)", block)
        comments_m = re.search(r"\*\*コメント\*\*[:：]\s*(\d+)", block)

        posts.append(
            Post(
                title=title,
                source=source,
                url=url,
                amazon_url=amazon,
                score=int(score_m.group(1)) if score_m else 0,
                comments=int(comments_m.group(1)) if comments_m else 0,
            )
        )

    return posts


def _field(text: str, pattern: str) -> str:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""


def translate(text: str) -> str:
    if not text.strip():
        return ""
    try:
        time.sleep(0.3)
        return GoogleTranslator(source="en", target="ja").translate(text[:4500])
    except Exception as e:
        print(f"  翻訳失敗: {e}")
        return text


def fetch_reddit_details(url: str) -> tuple[str, list[str]]:
    if "reddit.com" not in url:
        return "", []

    json_url = url.rstrip("/") + ".json"
    try:
        resp = requests.get(json_url, headers=REDDIT_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Reddit JSON 取得失敗: {e}")
        return "", []

    try:
        post_data = data[0]["data"]["children"][0]["data"]
        selftext = post_data.get("selftext", "").strip()

        top_comments = []
        for child in data[1]["data"]["children"]:
            if child.get("kind") != "t1":
                continue
            body = child["data"].get("body", "").strip()
            if body and body not in ("[deleted]", "[removed]") and len(body) > 15:
                top_comments.append(body[:400])
            if len(top_comments) >= 5:
                break

        return selftext, top_comments
    except Exception as e:
        print(f"  Reddit JSON 解析失敗: {e}")
        return "", []


def generate_with_claude(
    post: Post, ja_title: str, selftext_en: str, comments_en: list[str]
) -> str:
    comments_block = (
        "\n".join(f"- {c}" for c in comments_en) if comments_en else "（コメント取得なし）"
    )
    selftext_block = selftext_en if selftext_en else "（本文なし・画像投稿）"

    prompt = f"""以下の Reddit 投稿情報をもとに、日本語の工具・DIY ブログ記事を書いてください。

【投稿情報】
タイトル（英語）: {post.title}
日本語タイトル: {ja_title}
投稿先: {post.source}
スコア: {post.score}点 / コメント: {post.comments}件
URL: {post.url}

【投稿本文（英語）】
{selftext_block}

【上位コメント（英語）】
{comments_block}

【記事の条件】
- 自分の意見・感想は一切入れない
- 事実とコミュニティの反応のみで構成する
- この技術・製品・話題が「何か」「なぜ注目されているか」を読者に分かりやすく説明する
- Markdown のセクション見出し（##）を使う
- 文字数: 600〜1000字程度
- フロントマターや投稿メモは不要（本文のみ出力する）
"""

    print("  claude で記事本文を生成中...")
    env = {
        **__import__("os").environ,
        "CLAUDE_CODE_GIT_BASH_PATH": r"D:\Git\usr\bin\bash.exe",
    }
    result = subprocess.run(
        [str(Path.home() / ".local" / "bin" / "claude.exe"), "-p", prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI エラー:\n{result.stderr}")
    return result.stdout.strip()


def build_post_memo(post: Post, ja_title: str) -> str:
    subreddit_clean = post.source.replace("r/", "")
    return "\n".join(
        [
            "## 投稿メモ",
            "",
            f"- はてなブログのカテゴリ: `工具` `DIY` `{subreddit_clean}`",
            "- タイトル候補:",
            f"  - 「{ja_title}——海外工具コミュニティの反応まとめ」",
            f"  - 「{post.title}とは——{subreddit_clean}で話題の投稿を解説」",
            f"- SEOキーワード: `{post.title.lower()}` `{ja_title}` `{subreddit_clean} 工具`",
            "- 文字数目安: 600〜1000字",
            "",
        ]
    )


def build_full_article(
    post: Post,
    ja_title: str,
    body: str,
    digest_filename: str,
    now: datetime,
) -> str:
    ts = now.strftime("%Y-%m-%dT%H:%M:%S")
    post_memo = build_post_memo(post, ja_title)

    lines = [
        "---",
        f"dateCreated: {ts}",
        "tags:",
        "  - blog-article",
        "  - tools",
        "status: 下書き",
        f"source_digest: {digest_filename}",
        "---",
        "",
        f"# {ja_title}",
        "",
        f"> **ネタ元**: {post.source} 「{post.title}」（スコア{post.score}, コメント{post.comments}件）",
        "",
        "---",
        "",
        body,
        "",
        "---",
        "",
        f"**元記事**: {post.url}",
        f"**Amazon で探す**: {post.amazon_url}",
        "",
        "---",
        "",
        post_memo,
    ]
    return "\n".join(lines)


def unique_path(folder: Path, stem: str, suffix: str = ".md") -> Path:
    candidate = folder / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    i = 2
    while True:
        candidate = folder / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def main() -> None:
    config = load_config()
    folder = Path(config["obsidian_path"])

    digest_files = sorted(folder.glob("*_tool-digest.md"), reverse=True)
    if not digest_files:
        print(f"digest ファイルが見つかりません: {folder}")
        sys.exit(1)

    latest = digest_files[0]
    print(f"対象ファイル: {latest.name}")

    posts = parse_digest(latest)
    if not posts:
        print("記事を1件も取得できませんでした。")
        sys.exit(1)

    top = max(posts, key=lambda p: p.score)
    print(f"選択記事: {top.title}（スコア: {top.score}）")

    print("タイトルを翻訳中...")
    ja_title = translate(top.title)
    print(f"日本語タイトル: {ja_title}")

    print("Reddit から詳細を取得中...")
    selftext_en, comments_en = fetch_reddit_details(top.url)

    body = generate_with_claude(top, ja_title, selftext_en, comments_en)

    now = datetime.now(JST)
    date_str = now.strftime("%Y-%m-%d")
    content = build_full_article(top, ja_title, body, latest.name, now)

    out_path = unique_path(folder, f"{date_str}_article")
    out_path.write_text(content, encoding="utf-8")
    print(f"保存しました: {out_path}")


if __name__ == "__main__":
    main()
