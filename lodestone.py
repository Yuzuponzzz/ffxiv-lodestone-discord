import json
import os
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

RSS_URL = "https://jp.finalfantasyxiv.com/lodestone/news/news.xml"
NEWS_URL = "https://jp.finalfantasyxiv.com/lodestone/news/"
SEEN_FILE = Path("seen.json")

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

HEADERS = {
    "User-Agent": "Mozilla/5.0 FFXIV-Lodestone-Discord-Notifier/1.0"
}


def load_seen():
    if not SEEN_FILE.exists():
        return []

    try:
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_seen(items):
    SEEN_FILE.write_text(
        json.dumps(items[-200:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def category_from_text(text):
    t = text.lower()

    if "メンテナンス" in text:
        return "🔧 メンテナンス"
    if "障害" in text:
        return "⚠️ 障害情報"
    if "アップデート" in text or "hotfix" in t or "パッチ" in text:
        return "🔄 アップデート"
    if "お知らせ" in text:
        return "ℹ️ お知らせ"

    return "📢 トピックス"


def get_from_rss():
    response = requests.get(
        RSS_URL,
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "xml")

    result = []

    for item in soup.find_all("item"):
        title = item.title.get_text(strip=True) if item.title else ""
        link = item.link.get_text(strip=True) if item.link else ""

        if not title or not link:
            continue

        result.append({
            "id": link,
            "title": title,
            "url": link,
            "category": category_from_text(title),
        })

    return result


def get_from_news_page():
    response = requests.get(
        NEWS_URL,
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    result = []
    used = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "/lodestone/news/detail/" not in href:
            continue

        title = a.get_text(" ", strip=True)

        if not title:
            continue

        if href.startswith("/"):
            url = "https://jp.finalfantasyxiv.com" + href
        else:
            url = href

        if url in used:
            continue

        used.add(url)

        result.append({
            "id": url,
            "title": title,
            "url": url,
            "category": category_from_text(title),
        })

    return result


def get_news():
    try:
        news = get_from_rss()

        if news:
            print(f"RSSから {len(news)} 件取得しました")
            return news

    except Exception as e:
        print(f"RSS取得失敗: {e}")

    print("ニュース一覧ページから取得します")

    news = get_from_news_page()

    print(f"ニュース一覧から {len(news)} 件取得しました")

    return news


def post_discord(item):
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL が設定されていません")

    message = (
        f"**{item['category']}**\n"
        f"**{item['title']}**\n\n"
        f"🔗 {item['url']}"
    )

    response = requests.post(
        WEBHOOK_URL,
        json={
            "content": message,
            "username": "FFXIV公式ニュース",
        },
        timeout=20,
    )

    response.raise_for_status()


def main():
    news = get_news()

    if not news:
        raise RuntimeError("Lodestoneからニュースを取得できませんでした")

    seen = load_seen()

    current_ids = [item["id"] for item in news]

    # 初回実行時は現在の記事を既読として保存するだけ。
    # 過去記事がDiscordへ大量投稿されるのを防ぐ。
    if not seen:
        print("初回実行です。現在の記事を既読として登録します。")
        save_seen(current_ids)
        return

    new_items = [
        item
        for item in news
        if item["id"] not in seen
    ]

    if not new_items:
        print("新着ニュースはありません")
        save_seen(list(dict.fromkeys(seen + current_ids)))
        return

    print(f"新着ニュース: {len(new_items)} 件")

    # 古いもの → 新しいもの の順に投稿
    for item in reversed(new_items):
        print(f"Discordへ投稿: {item['title']}")
        post_discord(item)
        time.sleep(1)

    save_seen(list(dict.fromkeys(seen + current_ids)))


if __name__ == "__main__":
    main()
