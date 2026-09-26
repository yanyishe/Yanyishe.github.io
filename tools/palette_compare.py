# -*- coding: utf-8 -*-
"""生成播放器配色对照页 preview/bgm-palette.html。

直接把 index.html 里的播放器 CSS 和 HTML 抠出来复用 —— 对照页和正式页面
永远同步，不会出现"对照图上是旧的"这种事。

每一套配色都在两种背景上各放一遍（米白纸质 / 深色塔罗牌），
因为控件是浮层，好不好看取决于它压在什么上面。
"""

import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "index.html")
OUT = os.path.join(ROOT, "preview", "bgm-palette.html")

# 三套配色。key 是自定义属性的后缀，值就是变量值。
# 只写「和默认不同」的那些也行，但这里写全，方便直接看一份完整配色。
VARIANTS = [
    {
        "id": "A",
        "name": "深墨 + 暖金",
        "note": "深色浮层压在米白纸上，对比最强；金色沿用站内已有的强调色，不引入新色系。",
        "vars": {
            "surface": "#1a1822",
            "edge": "rgba(214,166,74,0.32)",
            "edge-hi": "rgba(214,166,74,0.85)",
            "ink": "rgba(240,228,202,0.72)",
            "ink-hi": "#f6ebd2",
            "dim": "rgba(240,228,202,0.46)",
            "rail": "rgba(240,228,202,0.16)",
            "art-edge": "rgba(214,166,74,0.42)",
            "accent": "#c9a24a",
            "accent-hi": "#dcb75f",
            "on-accent": "#1a1822",
            "accent-glow": "rgba(201,162,74,0.5)",
            "shadow": "0 18px 40px -24px rgba(0,0,0,0.78)",
            "shadow-hi": "0 24px 52px -22px rgba(0,0,0,0.85)",
            "knob": "#1a1822",
        },
    },
    {
        "id": "B",
        "name": "红黑（呼应站里的 PERSONA 标志）",
        "note": "正红做主色，和页面顶部那个红黑 LOGO 成一脉；塔罗牌背也是深色，压得住。",
        "vars": {
            "surface": "#141414",
            "edge": "rgba(216,35,42,0.42)",
            "edge-hi": "rgba(230,60,66,0.9)",
            "ink": "rgba(245,240,238,0.74)",
            "ink-hi": "#fff6f4",
            "dim": "rgba(245,240,238,0.44)",
            "rail": "rgba(245,240,238,0.16)",
            "art-edge": "rgba(216,35,42,0.55)",
            "accent": "#d8232a",
            "accent-hi": "#e63c42",
            "on-accent": "#fff6f4",
            "accent-glow": "rgba(216,35,42,0.55)",
            "shadow": "0 18px 40px -24px rgba(0,0,0,0.8)",
            "shadow-hi": "0 24px 52px -22px rgba(0,0,0,0.88)",
            "knob": "#141414",
        },
    },
    {
        "id": "C",
        "name": "深蓝紫 + 冷金（跟塔罗牌背同一系）",
        "note": "取牌背那个深藏青当底，把手金调冷一点。整体更「夜」，和背景的牌更融合。",
        "vars": {
            "surface": "#1b1b33",
            "edge": "rgba(150,160,205,0.30)",
            "edge-hi": "rgba(180,190,235,0.85)",
            "ink": "rgba(226,230,248,0.74)",
            "ink-hi": "#eef0ff",
            "dim": "rgba(226,230,248,0.46)",
            "rail": "rgba(226,230,248,0.16)",
            "art-edge": "rgba(180,190,235,0.42)",
            "accent": "#cbb26a",
            "accent-hi": "#ddc47c",
            "on-accent": "#1b1b33",
            "accent-glow": "rgba(203,178,106,0.5)",
            "shadow": "0 18px 40px -24px rgba(0,0,0,0.7)",
            "shadow-hi": "0 24px 52px -22px rgba(0,0,0,0.8)",
            "knob": "#1b1b33",
        },
    },
]


def slice_block(src, start, end):
    i = src.index(start)
    j = src.index(end, i)
    return src[i:j]


def main():
    html = io.open(TARGET, encoding="utf-8", newline="").read()

    css = slice_block(html, "/* ---- 背景音乐播放器 ----", "/* 视口收窄到两侧塞不下")
    # 把 @media (max-width:620px) 那段摘掉：对照页要的是桌面形态
    css = css[:css.index("@media (max-width: 620px)")]

    markup = slice_block(html, '<!-- 背景音乐播放器', "<!-- 曲目清单：")

    # 静态化：填上真实内容，好判断真实观感
    def fill(m):
        m = m.replace('class="bgm-bar" id="bgmBar"', 'class="bgm-bar is-ready" id="bgmBar"')
        m = m.replace('id="bgmTitle">—', 'id="bgmTitle">ＭＡＰ珠閒瑠市')
        m = m.replace('id="bgmCount">01 / 01', 'id="bgmCount">03 / 08')
        m = m.replace('id="bgmTime">0:00 / 0:00', 'id="bgmTime">1:38 / 3:54')
        m = m.replace('<i id="bgmFill"></i>',
                      '<i id="bgmFill" style="transform:scaleX(0.42)"></i>')
        m = m.replace('<b class="bgm-knob" id="bgmKnob"></b>',
                      '<b class="bgm-knob" id="bgmKnob" style="transform:translateX(75px)"></b>')
        m = m.replace('<i id="bgmVolFill"></i>',
                      '<i id="bgmVolFill" style="transform:scaleX(0.65)"></i>')
        m = m.replace('<b class="bgm-knob bgm-knob-sm" id="bgmVolKnob"></b>',
                      '<b class="bgm-knob bgm-knob-sm" id="bgmVolKnob" style="transform:translateX(99px)"></b>')
        m = m.replace('data-playing="true"', 'data-playing="true"')
        return m

    art = fill(markup)
    # 有封面的形态：加上 .is-art 和真的图（用抽出来的那张）
    with_art = art.replace(
        '<span class="bgm-cover" id="bgmCover" aria-hidden="true"></span>',
        '<span class="bgm-cover is-art" id="bgmCover" aria-hidden="true" '
        'style="background-image:url(\'../music/03-ＭＡＰ珠閒瑠市.webp\')"></span>')

    overrides = []
    rows = []
    for v in VARIANTS:
        decl = "\n".join("    --bgm-%s: %s;" % (k, val) for k, val in v["vars"].items())
        overrides.append(".v-%s .bgm-bar {\n%s\n}" % (v["id"], decl))
        rows.append(
            '<section class="row v-%s">\n'
            '  <div class="meta">\n'
            '    <span class="tag">%s</span>\n'
            '    <b>%s</b>\n'
            '    <p>%s</p>\n'
            '  </div>\n'
            '  <div class="stage on-paper">%s<style>.v-%s .bgm-bar{position:static;display:flex}</style></div>\n'
            '  <div class="stage on-card">%s<style>.v-%s .bgm-bar{position:static;display:flex}</style></div>\n'
            '</section>' % (v["id"], v["id"], v["name"], v["note"],
                            with_art, v["id"], with_art, v["id"]))

    page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>播放器配色对照</title>
<style>
  body { margin: 0; padding: 26px; background: #efeae0;
         font-family: 'Inter', system-ui, -apple-system, "Microsoft YaHei", sans-serif; }
  h1 { font-size: 19px; color: #2b2418; margin: 0 0 4px; }
  .lead { font-size: 12.5px; color: #6d6353; margin: 0 0 22px; line-height: 1.7; }
  .row { display: flex; align-items: center; gap: 22px; margin-bottom: 20px; }
  .meta { width: 236px; flex: 0 0 auto; }
  .tag { display: inline-block; background: #2b2418; color: #f6efdf;
         font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px;
         letter-spacing: .08em; }
  .meta b { display: block; margin: 7px 0 5px; font-size: 13.5px; color: #2b2418; }
  .meta p { margin: 0; font-size: 11.5px; line-height: 1.65; color: #6d6353; }
  .stage { width: 346px; height: 160px; flex: 0 0 auto;
           display: flex; align-items: center; justify-content: center;
           border-radius: 10px; }
  /* 控件是浮层，好不好看取决于压在什么上面 —— 两种背景都要放一遍 */
  .on-paper { background: #f7f3ea; box-shadow: inset 0 0 0 1px #ded5c4; }
  .on-card  { background: #1a1a2e url('../images/tarot-back.webp') center/54% no-repeat;
              box-shadow: inset 0 0 0 1px #0e0e1c; }
  .stage .bgm-bar { transform: none; }

__CSS__

__OVERRIDES__
</style>
</head>
<body>
  <h1>播放器配色对照</h1>
  <p class="lead">三套都是照 index.html 里那份 CSS 实时渲染的，不是另画的示意图。<br>
     每套左右各一次：左边压在米白纸面上，右边压在深色塔罗牌上 —— 因为播放器是浮层，好不好看取决于它压在什么上面。</p>
__ROWS__
</body>
</html>
"""

    page = (page.replace("__CSS__", css.rstrip())
                .replace("__OVERRIDES__", "\n".join(overrides))
                .replace("__ROWS__", "\n".join(rows)))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(page)
    print("写入: %s  (%d 字节)" % (os.path.relpath(OUT, ROOT), len(page.encode("utf-8"))))


if __name__ == "__main__":
    main()
