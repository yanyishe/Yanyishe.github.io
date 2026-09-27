# -*- coding: utf-8 -*-
"""把答题从「首页上的浮层」拆成一个独立页面 quiz.html。

为什么做成脚本而不是手剪：
  题目/角色数据和 CSS、JS 三段是分开的，改动要同步；手剪一次之后下次改数据又会漏。
  脚本从 index.html 里按锚点抽出这三段，拼成 quiz.html，再把它们从 index.html 里删掉，
  首页只留一个到 quiz.html 的链接。重跑是幂等的 —— 已经拆过就跳过。

用法：
  python tools/build_quiz_page.py
"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, 'index.html')
QUIZ = os.path.join(ROOT, 'quiz.html')

# ---- 锚点 ----
CSS_BEGIN = '/* ========== 答题界面样式 ========== */'
# 这个文件被来回改过，注释标记有两种写法，两个都认（谁是先把谁当结尾）
CSS_END_CANDS = [
    '/* ========== 背景音乐播放器 ========== */',
    '/* ---- 背景音乐播放器 ----',
]
CSS_END = None
HTML_BEGIN = '<!-- ========== 答题界面（隐藏状态） ========== -->'
HTML_END_CANDS = [
    '<!-- 背景音乐播放器 -->',
    '<!-- 背景音乐播放器：曲目清单为空时整条不出现，所以页面上不会留空壳 -->',
]
HTML_END = None
JS_BEGIN_MARK = '  // 你提供的 8 个角色数据'
START_CLICK_MARK = '点击“签订契约”进入答题'
SCRIPT_END = '</script>'

TEMPLATE = u'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>签订契约 · 人格测试 | Persona 30th</title>
<link rel="icon" type="image/png" href="./images/favicon.png">
<link rel="apple-touch-icon" href="./images/favicon-180.png">
<meta name="description" content="24 道命运之问，找出与你灵魂共鸣的那一位 Persona 主角。">
<style>
%(style)s

/* ========== 独立页面：把「浮层」还原成正常文档流 ==========
   quiz.html 里这张卡片不再是盖在首页上的弹层，而是页面本身，
   所以固定定位、透明度过渡这些"弹窗属性"要抵掉，保留它的视觉外壳。 */
html, body { min-height: 100%%; }
body {
  background: #16141e;
  /* 天鹅绒房间那层暗红/紫的氛围，静态渐变就够，不引入 filter（省内存） */
  background-image:
    radial-gradient(circle at 20%% 12%%, rgba(201, 162, 74, 0.10), transparent 55%%),
    radial-gradient(circle at 82%% 88%%, rgba(139, 90, 154, 0.16), transparent 60%%);
  background-attachment: fixed;
}
.quiz-overlay {
  position: static;
  inset: auto;
  z-index: auto;
  display: flex;
  min-height: 100vh;
  padding: 72px 16px 40px;
  background: transparent;
  opacity: 1;
  pointer-events: auto;
  transition: none;
}
.quiz-container { transform: none; transition: none; }

/* 返回首页。放在卡片正上方，和卡片同一条中轴线上。 */
.quiz-back {
  position: fixed; top: 20px; left: 20px; z-index: 10;
  display: inline-flex; align-items: center; gap: 8px;
  padding: 9px 16px;
  border: 1px solid rgba(214, 166, 74, 0.4);
  border-radius: 999px;
  background: rgba(26, 24, 34, 0.86);
  color: #f6ebd2;
  font-size: 13px; font-weight: 600; letter-spacing: 0.04em;
  text-decoration: none;
  transition: border-color 0.3s ease, transform 0.3s cubic-bezier(0.2, 0.7, 0.3, 1);
}
.quiz-back:hover { border-color: rgba(214, 166, 74, 0.85); transform: translateX(-3px); }
.quiz-back svg { width: 14px; height: 14px; display: block; }

/* 窄屏：返回按钮收到左上，卡片留白收窄 */
@media (max-width: 620px) {
  .quiz-overlay { padding: 64px 12px 24px; }
  .quiz-container { padding: 26px 20px; }
}
</style>
</head>
<body>

<a class="quiz-back" href="./index.html">
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"
       stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M11 5l-7 7 7 7M19 5l-7 7 7 7" />
  </svg>
  <span>返回首页</span>
</a>

%(quiz_html)s

%(bgm_html)s

<script src="./music/manifest.js"></script>
<script>
%(quiz_js)s

%(bgm_js)s
</script>
</body>
</html>
'''


def cut(lines, begin, end, label):
    """抽出 [含 begin, 不含 end) 之间的行"""
    s = next((i for i, l in enumerate(lines) if begin in l), None)
    if s is None:
        raise SystemExit('找不到锚点: ' + label + ' -> ' + begin)
    e = next((i for i in range(s + 1, len(lines)) if end in lines[i]), None)
    if e is None:
        raise SystemExit('找不到结束锚点: ' + label + ' -> ' + end)
    return lines[s:e], s, e


def autostart(quiz_js):
    """把「点首页按钮才开始」换成「页面加载就开始」。

    这段原本绑在首页那个 #startQuizBtn 上；拆成独立页后页面上没有这个按钮，
    不换掉的话答题页会一直停在「加载中...」（探针就是这么抓出来的）。
    """
    lines = quiz_js.split('\n')
    s = next((i for i, l in enumerate(lines) if START_CLICK_MARK in l), None)
    if s is None:
        print('警告：没找到「点击签订契约」那段，可能结构变了，跳过改写')
        return quiz_js
    e = next(i for i in range(s, len(lines)) if lines[i] == '  }')
    boot = [
        '  // 独立答题页：进来就是答题，不需要先在首页点那个按钮。',
        '  // overlay.classList.add 保留着 —— 万一以后又把它嵌回首页当浮层，这段还能直接用。',
        '  overlay.classList.add("active");',
        '  resetQuiz();',
    ]
    lines[s:e + 1] = boot
    return '\n'.join(lines)


def main():
    raw = io.open(INDEX, encoding='utf-8').read()
    lines = raw.split('\n')

    globals()['CSS_END'] = next(c for c in CSS_END_CANDS if c in raw)
    globals()['HTML_END'] = next(c for c in HTML_END_CANDS if c in raw)

    if 'quiz-overlay' not in raw:
        print('index.html 里已经没有答题浮层了 —— 说明已经拆过，停止以免重复处理。')
        return

    # --- 1. 抽样式（答题专用那段）+ 公共样式 ---
    style_all = re.search(r'<style>(.*?)</style>', raw, re.S).group(1)
    quiz_css, _, _ = cut(lines, CSS_BEGIN, CSS_END, '答题 CSS')
    quiz_css = '\n'.join(quiz_css)
    style_public = style_all.replace(quiz_css, '')

    # --- 2. 抽浮层 HTML ---
    quiz_html, h0, h1 = cut(lines, HTML_BEGIN, HTML_END, '答题浮层 HTML')
    quiz_html = '\n'.join(quiz_html).rstrip()

    # --- 3. 抽播放器 HTML（跟着一起搬，答着题也能听歌） ---
    bgm_html, b0, b1 = cut(lines, HTML_END, '<script src="./music/manifest.js">', '播放器 HTML')
    bgm_html = '\n'.join(bgm_html).rstrip()

    # --- 4. 抽答题 JS 与播放器 JS（两个 IIFE） ---
    js_start = next(i for i, l in enumerate(lines) if JS_BEGIN_MARK in l)
    # 往前找到 IIFE 的开头 (function () {
    js_iife = next(i for i in range(js_start, -1, -1) if lines[i].strip() == '(function () {')
    js_end = next(i for i, l in enumerate(lines) if l.strip() == SCRIPT_END)
    tail = lines[js_iife:js_end]
    # 两个 IIFE 的分界：第二个 "// ==================== 背景音乐"
    bgm_split = next(i for i, l in enumerate(tail)
                     if '==================== 背景音乐' in l)
    # 背景音乐那句注释的前一行是前一个 IIFE 的收尾 "})();"
    quiz_js = '\n'.join(tail[:bgm_split - 1]).rstrip()
    quiz_js = autostart(quiz_js)
    bgm_js = '\n'.join(tail[bgm_split - 1:]).rstrip()

    # --- 5. 写出 quiz.html ---
    out = TEMPLATE % {
        # 公共样式 + 答题专属样式都要带上：少了后者，卡片就没有深色底、
        # 选项也不是那套按钮（从「窗口」改成整页时最容易漏这一步）
        'style': (style_public.strip('\n') + '\n\n' + quiz_css.strip('\n')),
        'quiz_html': quiz_html,
        'bgm_html': bgm_html,
        'quiz_js': quiz_js,
        'bgm_js': bgm_js,
    }
    io.open(QUIZ, 'w', encoding='utf-8', newline='\n').write(out)
    print('已生成 %s  (%.1f KB)' % (os.path.basename(QUIZ), os.path.getsize(QUIZ) / 1024))

    # --- 6. 首页瘦身：删掉答题 CSS / 浮层 / 答题 IIFE，按钮改成链接 ---
    keep = lines[:]
    # 只删答题那一个 IIFE —— 背景音乐的 IIFE 在同一个 <script> 里、排在它后面，
    # 删到 </script> 会把播放器逻辑一起带走（主页就没 BGM 了）。
    del keep[js_iife:js_iife + (bgm_split - 1)]
    del keep[h0:h1]                     # 浮层 HTML
    # CSS 段
    css0 = next(i for i, l in enumerate(keep) if CSS_BEGIN in l)
    css1 = next(i for i, l in enumerate(keep) if CSS_END in l)
    del keep[css0:css1]
    new_raw = '\n'.join(keep)
    # 把触发浮层的 <div> 换成普通链接
    new_raw = new_raw.replace(
        '<div class="explore-badge" id="startQuizBtn">',
        '<a class="explore-badge" id="startQuizBtn" href="./quiz.html">')
    # 这个 badge 的收尾 </div> —— 它紧跟在同一段 SVG 之后（下一个兄弟是 quote-mark）
    new_raw = re.sub(
        r'(<span>签订契约</span>\s*\n\s*</div>\s*\n)(\s*<div class="quote-mark">)',
        r'<span>签订契约</span>\n      </a>\n      \2',
        new_raw, count=1)
    if '/* 现在是 <a>，别让它带下划线 */' not in new_raw:
        new_raw = new_raw.replace(
            '.explore-badge {\n  position: relative;',
            '.explore-badge {\n  position: relative;\n'
            '  /* 现在是 <a>，别让它带下划线 */\n  text-decoration: none;', 1)

    io.open(INDEX, 'w', encoding='utf-8', newline='\n').write(new_raw)
    print('首页瘦身 %.1f KB -> %.1f KB（-%d 字节）'
          % (len(raw) / 1024, len(new_raw) / 1024, len(raw) - len(new_raw)))


if __name__ == '__main__':
    main()
