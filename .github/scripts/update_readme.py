import os
import re
import sys
import time
import requests
from collections import defaultdict

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
USERNAME = os.environ.get("GH_USERNAME", "cha0cha0")
STARRED_LIMIT = int(os.environ.get("STARRED_LIMIT", "6"))
LANG_LIMIT = int(os.environ.get("LANG_LIMIT", "8"))

API = "https://api.github.com"
HEADERS = {
    # starred_at를 받으려면 아래 star+json을 쓰지만, 정렬은 최신순이라 기본 헤더로도 충분합니다.
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

README = "README.md"


def gh_get(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params or {})
    # 간단한 rate-limit 백오프
    if r.status_code == 403 and "rate limit" in r.text.lower():
        time.sleep(30)
        r = requests.get(url, headers=HEADERS, params=params or {})
    r.raise_for_status()
    return r.json()


def paginate(url, params=None, per_page=100, max_pages=10):
    params = dict(params or {})
    params.update({"per_page": per_page})
    page = 1
    while page <= max_pages:
        params["page"] = page
        data = gh_get(url, params=params)
        if not data:
            break
        for item in data:
            yield item
        if len(data) < per_page:
            break
        page += 1


def build_starred_md():
    """최근 Star한 저장소 상위 N개 목록 마크다운 생성"""
    items = []
    # /users/{username}/starred는 최신 Star 순으로 반환됩니다.
    for repo in paginate(f"{API}/users/{USERNAME}/starred", max_pages=5):
        full = repo.get("full_name") or ""
        desc = (repo.get("description") or "").strip().replace("\n", " ")
        stars = repo.get("stargazers_count", 0)
        lang = repo.get("language") or "-"
        url = repo.get("html_url")
        items.append((full, desc, stars, lang, url))

    items = items[:STARRED_LIMIT]

    if not items:
        return "> _No recent starred repositories._\n"

    lines = []
    for full, desc, stars, lang, url in items:
        badge = f"![stars](https://img.shields.io/badge/★-{stars}-brightgreen)"
        lang_b = f"![lang](https://img.shields.io/badge/lang-{str(lang).replace(' ', '%20')}-blue)"
        line = f"- **[{full}]({url})**  {badge} {lang_b}  \n  {desc if desc else '_No description_'}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def build_stack_md():
    """내 소유(포크 제외) 레포 전체 언어 바이트 합산 → 상위 N개를 배지로 출력"""
    lang_bytes = defaultdict(int)
    for repo in paginate(
        f"{API}/users/{USERNAME}/repos",
        params={"type": "owner", "sort": "updated"},
        max_pages=10,
    ):
        if repo.get("fork"):
            continue
        languages_url = repo.get("languages_url")
        if not languages_url:
            continue
        langs = gh_get(languages_url)
        for name, b in (langs or {}).items():
            lang_bytes[name] += int(b)

    if not lang_bytes:
        return "> _No repositories to analyze._\n"

    top = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)[:LANG_LIMIT]

    # 흔한 언어들에 컬러 부여(없으면 회색)
    colors = {
        "Java": "ED8B00", "Kotlin": "7F52FF", "Dart": "0175C2",
        "JavaScript": "F7DF1E", "TypeScript": "3178C6", "Python": "3776AB",
        "C": "A8B9CC", "C++": "00599C", "C#": "239120", "Go": "00ADD8",
        "HTML": "E34F26", "CSS": "1572B6", "Shell": "89e051",
        "SQL": "003B57", "Swift": "FA7343", "Scala": "DC322F",
        "Rust": "000000"
    }

    badges = []
    for name, _ in top:
        color = colors.get(name, "555555")
        label = name.replace(" ", "%20")
        badges.append(f"![{name}](https://img.shields.io/badge/{label}-{color}?style=for-the-badge)")
    return " ".join(badges) + "\n"


def replace_block(content, marker, new_md):
    """README 안의 <!-- MARKER:START --> ... <!-- MARKER:END --> 사이를 교체"""
    pattern = re.compile(
        rf"(<!--\s*{marker}:START\s*-->)(.*?)(<!--\s*{marker}:END\s*-->)",
        re.DOTALL | re.IGNORECASE,
    )
    if not pattern.search(content):
        # 마커가 없으면 맨 아래에 추가
        return content.rstrip() + f"\n\n<!-- {marker}:START -->\n{new_md}<!-- {marker}:END -->\n"
    return pattern.sub(rf"\1\n{new_md}\3", content)


def main():
    with open(README, "r", encoding="utf-8") as f:
        md = f.read()

    stack_md = build_stack_md()
    starred_md = build_starred_md()

    md2 = replace_block(md, "STACK", stack_md)
    md2 = replace_block(md2, "STARRED", starred_md)

    if md2 != md:
        with open(README, "w", encoding="utf-8") as f:
            f.write(md2)
    else:
        print("No changes.")


if __name__ == "__main__":
    if not GITHUB_TOKEN:
        print("Missing GITHUB_TOKEN", file=sys.stderr)
        sys.exit(1)
    main()
