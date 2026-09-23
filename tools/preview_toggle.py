# -*- coding: utf-8 -*-
"""
生成音效开关的规格预览页。

不重新写一套按钮样式 —— 直接从 index.html 里抽出 <style> 和按钮的真实标记，
只覆盖 position/scale 把两态并排放大。这样规格图和线上是同一份 CSS，
不会出现"图上好看、页面上不一样"的漂移。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, '_preview_toggle.html')

src = io.open(SRC, encoding='utf-8').read()

style = re.search(r'<style>(.*?)</style>', src, re.S).group(1)
button = re.search(r'<button class="sfx-toggle".*?</button>', src, re.S).group(0)

# 同一份按钮标记摆两次，第二份标成已静音 —— 图标切换靠 aria-pressed，不需要改标记
btn_on = button
btn_off = button.replace('aria-pressed="false"', 'aria-pressed="true"',
                         ).replace('aria-label="关闭音效"', 'aria-label="开启音效"',
                                   ).replace('title="关闭音效"', 'title="开启音效"')

EXTRA = """
<style>
  /* 只用在这一张规格图上：把 fixed 的按钮摆到台面上放大 */
  body {
    display: flex; align-items: center; justify-content: center;
    gap: 140px; min-height: 100vh; margin: 0;
    background: #faf8f4;
  }
  .spec-cell { text-align: center; }
  .spec-cell .sfx-toggle {
    position: static; opacity: 1;
    transform: scale(2.6); transform-origin: center;
    margin-bottom: 48px;
  }
  .spec-cell .spec-label {
    font: 500 14px/1.6 'Inter', system-ui, sans-serif;
    color: #6b6578; letter-spacing: 0.08em;
  }
  .spec-cell .spec-note {
    font: 400 12px/1.7 'Inter', system-ui, sans-serif;
    color: #a9a29a; letter-spacing: 0.04em;
  }
  .spec-title {
    position: fixed; top: 56px; left: 0; right: 0; text-align: center;
    font: 600 20px/1.4 'Inter', system-ui, sans-serif; color: #1a1a1f;
    letter-spacing: 0.02em;
  }
</style>
"""

BODY = """
<div class="spec-title">音效开关 · 两态</div>
<div class="spec-cell">
  __ON__
  <div class="spec-label">音效开启</div>
  <div class="spec-note">默认状态：翻牌有声、悬停有声</div>
</div>
<div class="spec-cell">
  __OFF__
  <div class="spec-label">已静音</div>
  <div class="spec-note">点击后写入 localStorage，下次打开仍是静音</div>
</div>
""".replace('__ON__', btn_on).replace('__OFF__', btn_off)

html = (
    '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n'
    '<title>音效开关规格</title>\n<style>' + style + '</style>' + EXTRA +
    '</head>\n<body>\n' + BODY + '\n</body>\n</html>\n'
)

io.open(OUT, 'w', encoding='utf-8').write(html)
print('preview -> ' + OUT)
