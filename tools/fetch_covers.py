# -*- coding: utf-8 -*-
"""给 music/ 里没有封面的歌，从 QQ 音乐按歌名查到专辑封面并下载。

用法（在项目根目录）：
    python tools/fetch_covers.py --dry     # 只查不下载，先看匹配对不对
    python tools/fetch_covers.py           # 下载还缺封面的
    python tools/fetch_covers.py --force   # 连已有封面的也重下

下载后存成 music/<同名>.webp（512px），于是就和「同名图片即封面」的约定接上了，
跑一次 gen_music_manifest.py 就能用。

为什么走 QQ 音乐：
    这台机器上国外的封面源基本都不可达（coverartarchive.org 的图存在 archive.org 上，
    那个域名被挡；pixabay / discogs / spotify 的图床都是 403）。
    实测 y.gtimg.cn（QQ 音乐封面 CDN）可以直接取图。

匹配策略：搜到的结果里优先选专辑名带「ペルソナ / Persona / サウンドトラック」的，
按歌名相似度排序。**匹配不一定对，所以加 --dry 先看一眼再下。**

版权：封面版权属于原发行方。这里是给自己看的粉丝站用的，请自行斟酌用途。
"""

import io
import json
import os
import re
import subprocess
import sys
import unicodedata
from urllib.parse import quote

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(ROOT, "music")

MAX_EDGE = 512
WEBP_QUALITY = 82
IMAGE_EXT = {".webp", ".jpg", ".jpeg", ".png", ".avif", ".gif"}

# 用旧的 json 接口：字段是平铺的（albummid 直接在顶层）。
# 加上 new_json=1 会改成嵌套结构，albummid 就取不到了。
SEARCH = ("https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
          "?w={q}&format=json&n={n}&p=1")
COVER = "https://y.gtimg.cn/music/photo_new/T002R{sz}x{sz}M000{mid}.jpg"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# 有些歌名太通用，直接搜会match到完全无关的东西 —— 这里手工兜底
QUERY = {
    "School Days": "Persona 3 School Days",
    "Map I": "Persona 3 Map I",
    "ＭＡＰ珠閒瑠市": "MAP 珠閒瑠市",
    "Heartbeat, Heartbreak": "Heartbeat Heartbreak Persona 4",
    "全人类的灵魂之诗": "全ての人の魂の詩",
}
# 自动匹配错了、或者几首候选分不出高下时，在这里钉死要用哪张专辑。
# 值是专辑名的一个片段，匹配到的那个候选直接胜出。
PIN = {
    # 「全ての人の魂の詩」在 P3 / P4 / P5 三张 OST 上时长都是 5:38，
    # 光靠歌名和时长分不开（P1 的原版是 4:48，本地是 5:39，所以不是 P1）。
    # 这份歌单是按发售顺序排的（P1→P2→P2→P3R→P3P→P4→P5），第 1 首取 P3。
    "全人类的灵魂之诗": "PERSONA3 オリジナル・サウンドトラック",
}
# 专辑名里出现这些词，说明八成是同系列 OST，加分
ALBUM_BONUS = ["ペルソナ", "persona", "サウンドトラック", "soundtrack",
               "オリジナル", "original", "ost"]
# 官方专辑的演唱/制作署名。搜索结果里翻录版常常排在官方版前面
# （实测「School Days」第一名是个网友翻录，官方版排第二），
# 靠这一列把官方版提上来。
OFFICIAL = ["目黒将司", "アトラス", "atlus", "小宮知子", "lyn", "平田志穂子",
            "高橋あず美", "藤田真由美", "川村ゆみ", "喜多條敦志", "本間昭光"]
# 翻录 / 合集：降权
REMAKE = ["cover", "カバー", "コレクション", "collection", "remix album",
          "piano", "アレンジ"]


def curl(url, binary=False, timeout=25):
    cmd = ["curl", "-s", "-L", "--max-time", str(timeout),
           "-H", "Referer: https://y.qq.com/", "-H", "User-Agent: " + UA, url]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    except Exception:
        return None
    if out.returncode != 0 or not out.stdout:
        return None
    return out.stdout if binary else out.stdout.decode("utf-8", "replace")


def norm(s):
    """全角转半角 + 去掉标点空白，用来做歌名相似度比较。"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s\-_,.'’()\[\]:：·、。!！?？]+", "", s)


def score(song_name, album_name, singer, query):
    s = 0
    a = (album_name or "").lower()
    p = (singer or "").lower()
    # 官方署名是最可靠的信号：官方 OST 往往不是搜索结果的第一个
    if any(w in p or w in a for w in OFFICIAL):
        s += 25
    # 官方原声专辑
    if any(w in a for w in ALBUM_BONUS):
        s += 10
    # 翻录 / 钢琴改编 / 合集，压下去
    if any(w in a or w in p for w in REMAKE):
        s -= 18
    q, n = norm(query), norm(song_name)
    if q == n:
        s += 20
    elif q and (q in n or n in q):
        s += 10
    elif q and n and len(q) > 4:
        # 逐字符重合度，够粗糙但够用
        hit = sum(1 for c in set(q) if c in n)
        s += int(6.0 * hit / max(1, len(set(q))))
    return s


def search(query, n=8):
    raw = curl(SEARCH.format(q=quote(query), n=n))
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    lst = ((data.get("data") or {}).get("song") or {}).get("list") or []
    out = []
    for it in lst:
        out.append({
            "song": it.get("songname") or it.get("title") or "",
            "album": it.get("albumname") or "",
            "mid": it.get("albummid") or "",
            "sec": it.get("interval") or 0,
            "singer": "、".join(s.get("name", "") for s in (it.get("singer") or [])),
        })
    return out


def pick(cands, query, pin=None):
    """pin 是专辑名片段；命中就直接胜出，不看分数。"""
    pool = [c for c in cands if c["mid"]]
    if pin:
        for c in pool:
            if pin.lower() in (c["album"] or "").lower():
                return [(999, c)] + [(score(c2["song"], c2["album"], c2["singer"], query), c2)
                                     for c2 in pool if c2 is not c]
    scored = [(score(c["song"], c["album"], c["singer"], query), c) for c in pool]
    scored.sort(key=lambda x: -x[0])
    return scored


def existing(stem, listing):
    for name in listing:
        if (os.path.splitext(name)[0].lower() == stem.lower()
                and os.path.splitext(name)[1].lower() in IMAGE_EXT):
            return name
    return None


def main():
    dry = "--dry" in sys.argv
    force = "--force" in sys.argv
    only = None
    for i, a in enumerate(sys.argv):
        if a == "--only" and i + 1 < len(sys.argv):
            only = sys.argv[i + 1]
    try:
        from PIL import Image
    except ImportError:
        sys.exit("需要 Pillow。")

    listing = os.listdir(MUSIC_DIR)
    tracks = sorted(n for n in listing if n.lower().endswith(".mp3"))
    if only:
        tracks = [n for n in tracks if only in n]
        if not tracks:
            sys.exit("--only %s 没匹配到任何曲目" % only)

    print("%s%d 首   (%s)\n" % ("【只查不下载】" if dry else "",
                                len(tracks), "覆盖已有封面" if force else "跳过已有封面"))

    got = skip = fail = 0
    for name in tracks:
        stem = os.path.splitext(name)[0]
        if existing(stem, listing) and not force:
            print("  %-44s 跳过（已有封面）" % stem[:44])
            skip += 1
            continue

        title = re.sub(r"^\d{1,3}\s*[-_.、\s]+\s*", "", stem).strip()
        query = QUERY.get(title, title)
        pin = PIN.get(title)
        cands = search(query)
        if not cands:
            print("  %-44s ✗ 搜不到（query=%s）" % (stem[:44], query))
            fail += 1
            continue

        ranked = pick(cands, query, pin)
        if not ranked:
            print("  %-44s ✗ 结果里没有 albummid" % stem[:44])
            fail += 1
            continue

        best_score, best = ranked[0]
        print("  %-44s 查「%s」%s" % (stem[:44], query, "  [已钉死专辑]" if pin else ""))
        for sc, c in ranked[:3]:
            mark = " ←选" if c is best else ""
            tag = "钉 " if sc >= 999 else "%2d " % sc
            print("        [%s] %-28s %5s | %-32s | %s%s"
                  % (tag, c["song"][:28],
                     "%d:%02d" % (c["sec"] // 60, c["sec"] % 60) if c["sec"] else "  -  ",
                     c["album"][:32], c["singer"][:16], mark))

        if dry:
            continue

        raw = curl(COVER.format(sz=500, mid=best["mid"]), binary=True)
        if not raw:
            print("        ✗ 封面下载失败 (mid=%s)" % best["mid"])
            fail += 1
            continue
        try:
            im = Image.open(io.BytesIO(raw))
            im.load()
            if max(im.size) > MAX_EDGE:
                sc = MAX_EDGE / float(max(im.size))
                im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))),
                               Image.LANCZOS)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            out = os.path.join(MUSIC_DIR, stem + ".webp")
            im.save(out, format="WEBP", quality=WEBP_QUALITY, method=6)
        except Exception as e:
            print("        ✗ 解不出图：%s" % e)
            fail += 1
            continue

        print("        ✓ 存为 %s.webp  %dx%d  %dKB -> %dKB"
              % (stem[:30], im.width, im.height, len(raw) // 1024,
                 os.path.getsize(out) // 1024))
        got += 1

    print()
    if dry:
        print("以上只是匹配结果，确认没问题再去掉 --dry 真下载。")
    else:
        print("下载 %d 首  跳过 %d 首  失败 %d 首" % (got, skip, fail))
        if got:
            print("下一步：python tools/gen_music_manifest.py")


if __name__ == "__main__":
    main()
