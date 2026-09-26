
(function () {
  'use strict';

  var layerEl = document.getElementById('tarotLayer');
  var bgLogo = document.querySelector('.bg-logo');
  var bgHero = document.querySelector('.bg-hero');
  var banner = document.querySelector('.hero-banner');

  // ---- 预先缓存 DOM 引用和数值，循环里不再查询 DOM / 解析 dataset ----
  var cards = Array.prototype.map.call(
    document.querySelectorAll('.tarot-wrap'),
    function (wrap) {
      // 静态起始倾角只在初始化时写一次 CSS 变量。
      // 之后 .tarot-card 的 transform 全权交给 CSS（见样式表），
      // 脚本不再逐帧覆写它 —— 翻牌因此不依赖 rAF 是否在跑。
      var rot = parseFloat(wrap.dataset.rotate) || 0;
      wrap.style.setProperty('--rot', rot + 'deg');
      return {
        el: wrap,
        card: wrap.querySelector('.tarot-card'),
        front: wrap.querySelector('.tarot-front'),
        depth: parseFloat(wrap.dataset.depth) || 0.5,
        floatAmp: parseFloat(wrap.dataset.float) || 1,
        hoverScale: wrap.dataset.layer === 'front' ? 1.12
                  : wrap.dataset.layer === 'mid' ? 1.10 : 1.08,
        frontSrc: wrap.dataset.front || '',
        frontApplied: false,
        hovered: false,
        flipped: false,
        pressed: false,
        // 悬停 / 点击动效的插值状态：放大 / 抬升 / 朝鼠标倾斜 / 点击弹跳
        sCur: 1, lift: 0, tiltX: 0, tiltY: 0, pulse: 0,
        rectX: 0, rectY: 0, rectW: 1, rectH: 1,
        // 上次写入的值，用于跳过无变化的样式写入
        lx: NaN, ly: NaN, ls: NaN, ltx: NaN, lty: NaN
      };
    }
  );

  // 卡片正面只在需要时应用：初始只下载共用的牌背
  function ensureFront(item) {
    if (item.frontApplied || !item.frontSrc) return;
    item.frontApplied = true;
    item.front.style.backgroundImage = 'url("' + item.frontSrc + '")';
  }

  var targetX = 0, targetY = 0;
  var smoothX = 0, smoothY = 0;
  // 指针的视口坐标，用于计算卡片内部的相对位置（倾斜方向）
  var mouseX = 0, mouseY = 0;
  var idlePhase = 0;
  var lastMoveTime = performance.now();
  var IDLE_DELAY = 1200;
  var currentLayout = 'top';
  var running = false;
  var rafId = 0;

  window.addEventListener('mousemove', function (e) {
    var cx = window.innerWidth / 2;
    var cy = window.innerHeight / 2;
    targetX = (e.clientX - cx) / cx;
    targetY = (e.clientY - cy) / cy;
    mouseX = e.clientX;
    mouseY = e.clientY;
    lastMoveTime = performance.now();
  }, { passive: true });

  window.addEventListener('mouseleave', function () {
    targetX = 0; targetY = 0;
  }, { passive: true });

  // ==================== 音效 ====================
  // 全部用 Web Audio 现场合成，不引入任何音频文件。
  // 理由：站点传输体积刚压到 ~900KB，一个 mp3 动辄 30~80KB，占得比整张塔罗牌还多；
  // 而"翻纸声"本质就是一段快速衰减的带通噪声，合成比采样更小、更可控，
  // 也能让"悬停"和"翻牌"共用同一段噪声源，只在滤波和包络上分家。
  var sfxCtx = null, sfxNoise = null, sfxReady = false;
  var lastTickAt = 0;

  // 音效常开。原来有个右下角的浮动喇叭开关，但它和播放器里的音量条挤在一起、
  // 两个喇叭图标容易被当成同一个东西，已经移除（见 CSS 里那段注释）。

  // 浏览器不允许在用户手势之前出声，所以 AudioContext 一直等到第一次
  // 按下 / 触摸 / 按键才创建。在此之前悬停是静音的 —— 这是正常的，
  // 用户第一次点牌时声音会准时出现。
  // resume() 返回的是 Promise，极少数情况下会 reject（音频设备被独占等）。
  // 不接住的话控制台会冒出 unhandled rejection，排查真问题时很干扰。
  function sfxSafeResume() {
    if (!sfxCtx || !sfxCtx.resume) return;
    var p = sfxCtx.resume();
    if (p && p.catch) p.catch(function () {});
  }

  function sfxUnlock() {
    if (sfxCtx) {
      if (sfxCtx.state === 'suspended') sfxSafeResume();
      return;
    }
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    try { sfxCtx = new AC(); } catch (err) { sfxCtx = null; return; }

    // 噪声缓冲只生成一次（0.4s 白噪），之后每次发声都是复用它，
    // 避免每次点击都现算几万个随机数造成卡顿。
    var n = Math.floor(sfxCtx.sampleRate * 0.4);
    sfxNoise = sfxCtx.createBuffer(1, n, sfxCtx.sampleRate);
    var d = sfxNoise.getChannelData(0);
    for (var i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;

    sfxReady = true;
    sfxSafeResume();
  }

  // 噪声 → 带通 → 增益包络，是这两个音效共用的骨架
  function sfxNoiseBurst(freqFrom, freqTo, q, peak, dur, rate, delay) {
    var ac = sfxCtx, t = ac.currentTime + (delay || 0);
    var src = ac.createBufferSource();
    src.buffer = sfxNoise;
    if (rate) src.playbackRate.value = rate;
    var bp = ac.createBiquadFilter();
    bp.type = 'bandpass';
    bp.Q.value = q;
    bp.frequency.setValueAtTime(freqFrom, t);
    if (freqTo && freqTo !== freqFrom) {
      // 频率扫动是"纸牌被掀起"的关键：低→高，像牌面从牌堆里被抽离
      bp.frequency.exponentialRampToValueAtTime(freqTo, t + dur * 0.7);
    }
    var g = ac.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(peak, t + Math.min(0.012, dur * 0.3));
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(bp); bp.connect(g); g.connect(ac.destination);
    src.start(t); src.stop(t + dur + 0.02);
  }

  // 翻牌：两段叠在一起 ——
  //   ① 900→3400Hz 的扫频噪声 = 牌被掀起来的"唰"
  //   ② 230→118Hz 的弱正弦   = 牌落定的那一下"闷"
  // 只有①会显得像撕纸，只有②又不像牌；两个一起才有"翻"的重量。
  function sfxFlip() {
    if (!sfxReady) return;
    sfxNoiseBurst(900, 3400, 1.1, 0.17, 0.16, 1, 0);

    var ac = sfxCtx, t = ac.currentTime + 0.04;
    var o = ac.createOscillator();
    o.type = 'sine';
    o.frequency.setValueAtTime(230, t);
    o.frequency.exponentialRampToValueAtTime(118, t + 0.11);
    var og = ac.createGain();
    og.gain.setValueAtTime(0.0001, t);
    og.gain.exponentialRampToValueAtTime(0.075, t + 0.022);
    og.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
    o.connect(og); og.connect(ac.destination);
    o.start(t); o.stop(t + 0.18);
  }

  // 悬停：只有 50ms 的高频碎响，音量压到 0.05 ——
  // 目的是让人"听见牌的存在"，而不是听见音效本身。
  function sfxTick() {
    if (!sfxReady) return;
    var now = performance.now();
    if (now - lastTickAt < 70) return;   // 快速横扫时别连成一片噪声
    lastTickAt = now;
    sfxNoiseBurst(2600, 2600, 1.6, 0.05, 0.05, 1.6, 0);
  }

  // 首次手势解锁（捕获阶段挂，保证早于卡片自身的 click 处理）
  function sfxFirstGesture() {
    sfxUnlock();
    window.removeEventListener('pointerdown', sfxFirstGesture, true);
    window.removeEventListener('keydown', sfxFirstGesture, true);
    window.removeEventListener('touchstart', sfxFirstGesture, true);
  }
  window.addEventListener('pointerdown', sfxFirstGesture, true);
  window.addEventListener('keydown', sfxFirstGesture, true);
  window.addEventListener('touchstart', sfxFirstGesture, true);

  // 切到后台就把音频线程挂起，回到前台再唤醒：
  // 看不见的标签页不该继续占着音频通道（和"离屏即停 rAF"是同一个思路）。
  document.addEventListener('visibilitychange', function () {
    if (!sfxCtx) return;
    if (document.hidden) {
      if (sfxCtx.suspend) {
        var sp = sfxCtx.suspend();
        if (sp && sp.catch) sp.catch(function () {});
      }
    } else if (sfxCtx.state === 'suspended') {
      sfxSafeResume();
    }
  }, { passive: true });

  // 点击翻牌 + 悬停预热（用事件替代每帧 matches(':hover')）
  cards.forEach(function (item) {
    item.el.addEventListener('mouseenter', function (e) {
      item.hovered = true;
      // 只在进入时读一次几何信息，之后每帧只用缓存值算倾斜，不触发重排
      var r = item.el.getBoundingClientRect();
      item.rectX = r.left; item.rectY = r.top;
      item.rectW = r.width || 1; item.rectH = r.height || 1;
      // 触屏等没有 mousemove 的场景，用进入事件的坐标兜底
      if (e.clientX) { mouseX = e.clientX; mouseY = e.clientY; }
      ensureFront(item);
      sfxTick();
    }, { passive: true });

    item.el.addEventListener('mouseleave', function () {
      item.hovered = false;
    }, { passive: true });

    // 按下时轻微回压，松开弹回
    item.el.addEventListener('mousedown', function () {
      item.pressed = true;
    }, { passive: true });

    item.el.addEventListener('click', function (e) {
      e.stopPropagation();
      // 正面在首次翻开时才写入，首屏只需下载共用的牌背
      ensureFront(item);
      item.flipped = !item.flipped;
      item.pulse = 1;                                  // 触发一次翻开弹跳
      item.el.classList.toggle('flipped', item.flipped);
      sfxFlip();
      // 触屏上的"触感"：8ms 的一下轻震，和音效共用一个开关
      if (navigator.vibrate) {
        try { navigator.vibrate(8); } catch (err) {}
      }
    });
  });

  // 指针在卡片外松开也要复位，避免"卡住按下状态"
  window.addEventListener('mouseup', function () {
    for (var i = 0; i < cards.length; i++) cards[i].pressed = false;
  }, { passive: true });

  // 布局切换
  var lastLayoutCheck = 0;
  function updateLayout() {
    if (!banner) return;
    var next = (window.scrollY || window.pageYOffset) > banner.offsetHeight * 0.7
      ? 'scrolled' : 'top';
    if (next !== currentLayout) {
      currentLayout = next;
      document.body.classList.toggle('layout-top', next === 'top');
      document.body.classList.toggle('layout-scrolled', next === 'scrolled');
      idlePhase = 0;
      lastMoveTime = performance.now();
    }
  }
  window.addEventListener('scroll', function () {
    // 节流到 100ms，避免每次滚动都读取 offsetHeight 触发布局
    var now = performance.now();
    if (now - lastLayoutCheck < 100) return;
    lastLayoutCheck = now;
    updateLayout();
  }, { passive: true });
  window.addEventListener('resize', updateLayout, { passive: true });
  updateLayout();

  // ---- 牌层高度 = 正文真实高度 ----
  // 层高写死 200vh，而页面实际约 250vh，底部那一截一张牌都没有，
  // 是"背景空"的一半原因。这里直接量 banner + 内容区的总高写进 --layer-h，
  // 槽位百分比就永远铺满整页；层是绝对定位、不参与布局，所以不会回调递归。
  function syncLayerHeight() {
    var cwEl = document.querySelector('.content-wrap');
    var h = 0;
    if (banner) h = Math.max(h, banner.offsetTop + banner.offsetHeight);
    if (cwEl)   h = Math.max(h, cwEl.offsetTop + cwEl.offsetHeight);
    h = Math.max(h, window.innerHeight);
    document.documentElement.style.setProperty('--layer-h', h + 'px');
  }
  syncLayerHeight();
  window.addEventListener('load', syncLayerHeight, { passive: true });
  window.addEventListener('resize', syncLayerHeight, { passive: true });
  if ('ResizeObserver' in window) {
    new ResizeObserver(syncLayerHeight).observe(
      document.querySelector('.content-wrap') || document.body);
  }

  // ---- 动画循环 ----
  function frame() {
    var now = performance.now();
    var isIdle = now - lastMoveTime > IDLE_DELAY;

    if (isIdle) {
      idlePhase += 0.012;
      targetX = Math.sin(idlePhase * 0.8) * 0.45;
      targetY = Math.cos(idlePhase * 0.6) * 0.35;
    }

    smoothX += (targetX - smoothX) * 0.06;
    smoothY += (targetY - smoothY) * 0.06;

    for (var i = 0; i < cards.length; i++) {
      var item = cards[i];
      var d = item.depth;

      // ---- 悬停细节：朝指针方向倾斜 ----
      // 用进入时缓存的卡片矩形算归一化位置，避免每帧读 DOM。
      // 指针偏向哪一边，那一边就微微抬起（像用指尖顶起牌角），
      // 而不是被指针推倒——配合抬升和扫光才是一套"拿起来看"的动作。
      var ttx = 0, tty = 0;
      if (item.hovered && !item.flipped) {
        var nx = (mouseX - item.rectX) / item.rectW * 2 - 1;
        var ny = (mouseY - item.rectY) / item.rectH * 2 - 1;
        nx = nx < -1 ? -1 : (nx > 1 ? 1 : nx);
        ny = ny < -1 ? -1 : (ny > 1 ? 1 : ny);
        ttx = ny * 14;    // 指针偏下 → 下边缘向前抬起
        tty = -nx * 16;   // 指针偏右 → 右边缘向前抬起
      }

      // 点击弹跳：一个快速衰减的额外缩放，让"翻"这个动作有手感
      item.pulse *= 0.86;
      if (item.pulse < 0.01) item.pulse = 0;

      // 翻开的牌在 CSS 层已经有了"上浮 + 沿 Z 推进"的放大，
      // 这里不再叠加（叠乘会大得压到邻牌），只保留按下时的一次弹跳。
      var sTarget = (item.hovered && !item.flipped ? item.hoverScale : 1)
                  + item.pulse * 0.12;
      if (item.pressed) sTarget *= 0.94;
      var liftTarget = item.hovered ? (item.pressed ? 5 : 8) : 0;

      // 全部走插值，让进入 / 离开都是连续过渡而非硬切换
      item.tiltX += (ttx - item.tiltX) * 0.16;
      item.tiltY += (tty - item.tiltY) * 0.16;
      item.lift += (liftTarget - item.lift) * 0.18;
      item.sCur += (sTarget - item.sCur) * 0.18;

      var tiltX = round1(item.tiltX - smoothY * 5 * d);   // 悬停倾斜 + 视差，合成到 wrap 一层
      var tiltY = round1(item.tiltY);
      var px = round2(-smoothX * 18 * d);
      var py = round2(-smoothY * 14 * d - item.lift
        + (isIdle
            ? Math.sin(idlePhase * 1.8 + d * 4) * 6 * item.floatAmp
            : Math.sin(idlePhase * 1.0 + d * 3) * 2 * item.floatAmp));
      var scale = round3(item.sCur);

      // 全都没变就跳过写入 —— 收敛后每帧零 DOM 操作。
      // 翻转角度不在这里判断：它由 CSS 类驱动，与本循环无关。
      if (px === item.lx && py === item.ly && scale === item.ls &&
          tiltX === item.ltx && tiltY === item.lty) {
        continue;
      }

      item.lx = px; item.ly = py; item.ls = scale;
      item.ltx = tiltX; item.lty = tiltY;
      item.el.style.transform =
        'translate3d(' + px + 'px,' + py + 'px,0) scale(' + scale + ')' +
        (tiltX || tiltY
          ? ' rotateX(' + tiltX + 'deg) rotateY(' + tiltY + 'deg)'
          : '');
    }

    if (bgLogo) {
      bgLogo.style.transform =
        'rotate(-8deg) translate3d(' + round2(-smoothX * 8) + 'px,' + round2(-smoothY * 6) + 'px,0)';
    }
    if (bgHero) {
      bgHero.style.transform =
        'rotate(6deg) translate3d(' + round2(-smoothX * 10) + 'px,' + round2(-smoothY * 8) + 'px,0)';
    }

    rafId = requestAnimationFrame(frame);
  }

  function round2(v) { return Math.round(v * 100) / 100; }
  function round1(v) { return Math.round(v * 10) / 10; }
  function round3(v) { return Math.round(v * 1000) / 1000; }

  function start() {
    if (running) return;
    running = true;
    rafId = requestAnimationFrame(frame);
  }
  function stop() {
    if (!running) return;
    running = false;
    cancelAnimationFrame(rafId);
  }

  // 页面不可见、或塔罗牌层离开视口时，完全停止动画循环
  var heroVisible = true;
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) stop();
    else if (heroVisible) start();
  }, { passive: true });

  if (layerEl && 'IntersectionObserver' in window) {
    new IntersectionObserver(function (entries) {
      heroVisible = entries[0].isIntersecting;
      if (heroVisible && !document.hidden) start();
      else stop();
    }, { rootMargin: '100px' }).observe(layerEl);
  }

  start();

  // ---- 首屏之后，空闲时把卡片正面预取进缓存，首次翻牌无需等待 ----
  // 这里只预热浏览器缓存，不写 background-image，避免一上来就解码 22 张图
  function warmup() {
    cards.forEach(function (item) {
      if (!item.frontSrc) return;
      var img = new Image();
      img.decoding = 'async';
      img.src = item.frontSrc;
    });
  }
  if ('requestIdleCallback' in window) {
    requestIdleCallback(warmup, { timeout: 3000 });
  } else {
    window.addEventListener('load', function () { setTimeout(warmup, 1200); });
  }
})();

// ==================== 背景音乐 ====================
// 曲目清单在 music/manifest.js，由 tools/gen_music_manifest.py 扫描 music/ 目录生成：
// 想把歌加进来，就把文件丢进 music/ 再跑一次那个脚本，不必碰这个文件。
//
// 关于「进站即响」——
// 浏览器（Chrome / Safari / Edge / Firefox 都一样）禁止页面在用户做出任何交互之前
// 播放有声的音频，这是规范层面的硬规则，没有可靠的绕法。所以这里做的是
// 「能播就直接播，被拒就等第一个手势」：用户点一下、按一下键、碰一下屏幕，
// 音乐立刻起身，并做 1.4s 淡入，不会「啪」地砸出来。
(function () {
  'use strict';

  var bar = document.getElementById('bgmBar');
  if (!bar) return;
  var titleEl   = document.getElementById('bgmTitle');
  var coverEl   = document.getElementById('bgmCover');
  var btnMin    = document.getElementById('bgmMin');
  var btnMini   = document.getElementById('bgmMini');
  var miniLabel = document.getElementById('bgmMiniLabel');
  var countEl   = document.getElementById('bgmCount');
  var timeEl    = document.getElementById('bgmTime');
  var fillEl    = document.getElementById('bgmFill');
  var knobEl    = document.getElementById('bgmKnob');
  var seekEl    = document.getElementById('bgmSeek');
  var btnPrev   = document.getElementById('bgmPrev');
  var btnPlay   = document.getElementById('bgmPlay');
  var btnNext   = document.getElementById('bgmNext');
  var btnMute   = document.getElementById('bgmMute');
  var volEl     = document.getElementById('bgmVol');
  var volFillEl = document.getElementById('bgmVolFill');
  var volKnobEl = document.getElementById('bgmVolKnob');

  // 稳态音量：听得见，但不跟人抢注意力 —— 背景音乐不该比翻牌声更抢戏
  var VOL_DEFAULT = 0.4;
  var FADE_IN  = 1400;
  var FADE_OUT = 320;

  var tracks = (window.YYS_TRACKS || []).filter(function (t) {
    return t && typeof t.file === 'string' && t.file;
  });
  // 还没放歌：控制条不出现，也不额外发一个请求出去
  if (!tracks.length) return;

  var el = null;
  var idx = 0;
  var fadeTimer = 0;
  var armed = false;
  var resumeAfterHidden = false;
  var failStreak = 0;
  // 音量基准值。淡入淡出只在「当前音量」和「这个基准」之间插值 ——
  // 淡入淡出改了 el.volume，但用户设的基准不能跟着被冲掉，否则下一首又从 0.4 起。
  var vol = VOL_DEFAULT;
  var muted = false;

  // 淡入淡出要去的目标：静音就是 0
  function targetVol() { return muted ? 0 : vol; }

  // 能解锁音频的事件。这里刻意不含 scroll / wheel ——
  // 它们常伴随真实交互，但按规范不算「用户激活」，解锁不了音频。
  var GESTURES = ['pointerdown', 'pointerup', 'click', 'keydown', 'touchend'];

  // ---- 音量渐变 ----
  // 用 setInterval 而不是 requestAnimationFrame：rAF 在后台标签页会停摆，
  // 音量会卡在半路（切歌时正好切走标签页就会撞上）。
  function fadeTo(to, ms, done) {
    clearInterval(fadeTimer);
    if (!el) { if (done) done(); return; }
    var from = el.volume;
    var steps = Math.max(1, Math.round(ms / 40));
    var i = 0;
    fadeTimer = setInterval(function () {
      i++;
      el.volume = Math.max(0, Math.min(1, from + (to - from) * (i / steps)));
      if (i >= steps) {
        clearInterval(fadeTimer);
        el.volume = to;
        if (done) done();
      }
    }, 40);
  }

  // 封面：清单里给了 cover 就用它，否则清掉行内样式退回 CSS 里那张面具牌背。
  // 用行内 backgroundImage 而不是换 <img>：铺法（居中裁切）由 CSS 的
  // .bgm-cover / .is-art 两条规则管，JS 只负责换图。
  // 展开态的封面、收起态唱片中央的标贴，共用同一张图，所以一起设。
  function paintArt(el, url) {
    if (!el) return;
    if (url) {
      el.style.backgroundImage = 'url("' + encodeURI(url) + '")';
      el.classList.add('is-art');
    } else {
      el.style.backgroundImage = '';
      el.classList.remove('is-art');
    }
  }
  function setCover(url) {
    paintArt(coverEl, url);
    paintArt(miniLabel, url);
  }

  function paint() {
    var t = tracks[idx];
    if (titleEl) titleEl.textContent = t.title || t.file;
    if (countEl) countEl.textContent = pad2(idx + 1) + ' / ' + pad2(tracks.length);
    setCover(t.cover);
    // 收起后圆钮上没有文字，只能靠 title / aria 告诉读屏用户现在在放什么
    if (btnMini) {
      var mn = '展开播放器：' + (t.title || t.file);
      btnMini.setAttribute('aria-label', mn);
      btnMini.setAttribute('title', mn);
    }
    var playing = !!el && !el.paused;
    // 播放态同时写在小按钮和整条上：小按钮切图标，整条给封面/配色用。
    // 状态只有 DOM 这一份，样式和验证脚本都只认它，不会和 JS 变量走失。
    btnPlay.setAttribute('data-playing', playing ? 'true' : 'false');
    bar.setAttribute('data-playing', playing ? 'true' : 'false');
    // 收起态那张唱片的旋转也认这个状态：在播就转，暂停就停
    if (btnMini) btnMini.setAttribute('data-playing', playing ? 'true' : 'false');
    var label = playing ? '暂停' : '播放';
    btnPlay.setAttribute('aria-label', label);
    btnPlay.setAttribute('title', label);
    paintVol();
    tickTime();
  }

  function remember() {
    try {
      localStorage.setItem('yys-bgm', String(idx));
      localStorage.setItem('yys-bgm-off', (el && el.paused) ? '1' : '0');
      localStorage.setItem('yys-bgm-vol', vol.toFixed(2));
      localStorage.setItem('yys-bgm-mute', muted ? '1' : '0');
    } catch (err) {}
  }

  function tickProgress() {
    if (!el) return;
    var d = el.duration;
    var r = (d && isFinite(d) && d > 0) ? (el.currentTime / d) : 0;
    paintTrack(fillEl && fillEl.parentNode, fillEl, knobEl, r);
    if (seekEl) seekEl.setAttribute('aria-valuenow', Math.round(clamp01(r) * 100));
    tickTime();
  }

  // ---- 小工具 ----
  function clamp01(v) { return v > 1 ? 1 : v < 0 ? 0 : (isFinite(v) ? v : 0); }
  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  // 秒 -> m:ss。duration 在元数据到位前是 NaN，不兜住就会渲染出 "NaN:NaN"
  function fmt(s) {
    if (!isFinite(s) || s < 0) s = 0;
    s = Math.floor(s);
    return Math.floor(s / 60) + ':' + pad2(s % 60);
  }

  // 把 0~1 的比例画到「已播段 + 把手」上。
  // 已播段走 scaleX、把手走 translateX —— 都只碰合成属性，不逐帧触发布局。
  // 把手必须放在被 scale 的元素之外：缩放过的手柄会被压成椭圆。
  function paintTrack(rail, fill, knob, r) {
    r = clamp01(r);
    if (fill) fill.style.transform = 'scaleX(' + r.toFixed(4) + ')';
    if (knob && rail) knob.style.transform = 'translateX(' + (r * rail.clientWidth).toFixed(1) + 'px)';
    return r;
  }

  function paintVol() {
    var rail = volFillEl && volFillEl.parentNode;
    var r = paintTrack(rail, volFillEl, volKnobEl, muted ? 0 : vol);
    if (btnMute) {
      btnMute.setAttribute('data-muted', muted ? 'true' : 'false');
      var l = muted ? '取消静音' : '静音';
      btnMute.setAttribute('aria-label', l);
      btnMute.setAttribute('title', l);
    }
    if (volEl) volEl.setAttribute('aria-valuenow', Math.round(r * 100));
  }

  function tickTime() {
    if (!timeEl || !el) return;
    timeEl.textContent = fmt(el.currentTime) + ' / ' + fmt(el.duration);
  }

  // ---- 进度 / 音量的拖动定位 ----
  // 用 pointer 事件而不是 mousedown：一套代码同时覆盖鼠标、触屏和手写笔。
  // setPointerCapture 保证指针移出控件之后还能接着拖。
  function bindDrag(trackEl, opts) {
    if (!trackEl) return;
    var dragging = false;
    function ratioOf(ev) {
      var r = trackEl.getBoundingClientRect();
      if (!r.width) return 0;
      return clamp01((ev.clientX - r.left) / r.width);
    }
    trackEl.addEventListener('pointerdown', function (ev) {
      dragging = true;
      try { trackEl.setPointerCapture(ev.pointerId); } catch (e) {}
      opts.set(ratioOf(ev));
      ev.preventDefault();   // 别顺手把页面文字选中
    });
    trackEl.addEventListener('pointermove', function (ev) {
      if (dragging) opts.set(ratioOf(ev));
    });
    function end(ev) {
      if (!dragging) return;
      dragging = false;
      try { trackEl.releasePointerCapture(ev.pointerId); } catch (e) {}
      if (opts.done) opts.done();
    }
    trackEl.addEventListener('pointerup', end);
    trackEl.addEventListener('pointercancel', end);
    // 键盘也要能用：Tab 进来后左右键微调，Shift 加速，Home/End 到两端
    trackEl.addEventListener('keydown', function (ev) {
      var step = ev.shiftKey ? 0.1 : 0.02;
      var now = opts.get ? opts.get() : 0;
      var next;
      if (ev.key === 'ArrowRight' || ev.key === 'ArrowUp') next = now + step;
      else if (ev.key === 'ArrowLeft' || ev.key === 'ArrowDown') next = now - step;
      else if (ev.key === 'Home') next = 0;
      else if (ev.key === 'End') next = 1;
      else return;
      ev.preventDefault();
      opts.set(clamp01(next));
      if (opts.done) opts.done();
    });
  }

  // ---- 起播：先试，被拒就等手势 ----
  function start() {
    if (!el || !el.paused) return;
    el.volume = 0;
    var p = el.play();
    if (!p || !p.then) { fadeTo(targetVol(), FADE_IN); paint(); return; }
    p.then(function () {
      failStreak = 0;
      fadeTo(targetVol(), FADE_IN);
      paint();
    }).catch(function () {
      // 被拦下不是错误，是「还没人碰过这个页面」—— 挂上第一个手势等着
      arm();
    });
  }

  function arm() {
    if (armed) return;
    armed = true;
    for (var i = 0; i < GESTURES.length; i++) {
      window.addEventListener(GESTURES[i], kick, true);
    }
  }

  function kick(e) {
    for (var i = 0; i < GESTURES.length; i++) {
      window.removeEventListener(GESTURES[i], kick, true);
    }
    armed = false;
    // 手势落在控制条上时不要抢跑，交给按钮自己的处理器。
    // 否则这里先 el.play()（el.paused 立刻变 false），紧接着按钮那一下 click
    // 判断「正在播」就走了暂停分支 —— 一次点击被自己抵消掉。
    // 表现是「首次交互直接点播放键没反应，再点一下才开始」，之后整体错位一格，
    // 也就是用户看到的「暂停键不好使」。
    if (e && e.target && bar.contains(e.target)) return;
    start();
  }

  // ---- 切歌：先淡出，换源，再淡入。硬切会有一声明显的爆音 ----
  function switchTo(i) {
    var n = tracks.length;
    idx = ((i % n) + n) % n;
    var t = tracks[idx];

    fadeTo(0, FADE_OUT, function () {
      el.src = encodeURI('./music/' + t.file);
      el.load();
      el.volume = 0;
      tickProgress();
      paint();
      remember();
      var p = el.play();
      if (!p || !p.then) { fadeTo(targetVol(), 700); paint(); return; }
      p.then(function () { failStreak = 0; fadeTo(targetVol(), 700); paint(); })
       .catch(function () { arm(); });
    });
  }

  // ---- 初始化 ----
  var savedIdx = 0, wantOff = false;
  try {
    savedIdx = parseInt(localStorage.getItem('yys-bgm'), 10) || 0;
    wantOff = localStorage.getItem('yys-bgm-off') === '1';
    var savedVol = parseFloat(localStorage.getItem('yys-bgm-vol'));
    if (isFinite(savedVol) && savedVol >= 0 && savedVol <= 1) vol = savedVol;
    muted = localStorage.getItem('yys-bgm-mute') === '1';
  } catch (err) {}
  idx = (savedIdx >= 0 && savedIdx < tracks.length) ? savedIdx : 0;

  el = new Audio();
  el.preload = 'auto';
  el.volume = 0;
  el.src = encodeURI('./music/' + tracks[idx].file);

  el.addEventListener('timeupdate', tickProgress);
  el.addEventListener('loadstart', tickProgress);
  el.addEventListener('ended', function () { switchTo(idx + 1); });  // 播完自动下一首
  el.addEventListener('play', paint);
  el.addEventListener('pause', paint);
  el.addEventListener('error', function () {
    // 某个文件缺了或没传上去：跳过它，别把整条链卡死。
    // 但也要防止「全都坏了」时无限空转 —— 转够一圈就收摊。
    failStreak++;
    if (failStreak >= tracks.length) {
      bar.classList.remove('is-ready');
      return;
    }
    switchTo(idx + 1);
  });

  btnPlay.addEventListener('click', function () {
    if (el.paused) {
      start();
    } else {
      // 暂停也走淡出：硬切会有一声明显的爆音
      fadeTo(0, 400, function () { el.pause(); paint(); remember(); });
    }
  });
  btnPrev.addEventListener('click', function () { switchTo(idx - 1); });
  btnNext.addEventListener('click', function () { switchTo(idx + 1); });
  btnMute.addEventListener('click', function () {
    muted = !muted;
    // 静音只改音量，不动暂停态 —— 取消静音后音乐从原处接着往下走
    fadeTo(targetVol(), 220);
    paintVol();
    remember();
  });

  // ---- 收起 / 展开 ----
  // 状态只挂在 <body> 的类上（CSS 据此切换谁显示），JS 不另存一份布尔值 ——
  // 两份状态迟早会走失。刻意不写 localStorage：需求是"每次进站都是展开的"。
  function setCollapsed(on) {
    document.body.classList.toggle('bgm-min', !!on);
    // 焦点跟着一起搬，否则用键盘的人收起之后焦点会掉到 body 上
    var target = on ? btnMini : btnMin;
    if (target && target.focus) {
      try { target.focus({ preventScroll: true }); } catch (err) { target.focus(); }
    }
  }
  btnMin.addEventListener('click', function () { setCollapsed(true); });
  btnMini.addEventListener('click', function () { setCollapsed(false); });

  // 进度拖拽：元数据没到位时 duration 是 NaN，这时不给定位
  bindDrag(seekEl, {
    set: function (r) {
      var d = el && el.duration;
      if (!d || !isFinite(d) || d <= 0) return;
      el.currentTime = r * d;
      tickProgress();
    },
    get: function () {
      var d = el && el.duration;
      return (d && isFinite(d) && d > 0) ? el.currentTime / d : 0;
    },
  });

  bindDrag(volEl, {
    set: function (r) {
      // 拖动期间要把正在跑的淡入淡出停掉，否则它每 40ms 覆盖一次 el.volume，
      // 手感就是「拖不动」
      clearInterval(fadeTimer);
      vol = r;
      if (r > 0) muted = false;    // 从静音里一拖就顺带解除静音
      if (el) el.volume = targetVol();
      paintVol();
    },
    get: function () { return muted ? 0 : vol; },
    done: remember,
  });

  // 窗口尺寸变了，把手的位置要按新的轨道宽度重算
  window.addEventListener('resize', function () { tickProgress(); paintVol(); }, { passive: true });

  // 切到后台就停。这是页面的背景音乐，人不在这个页面就不必让它继续占着音频通道，
  // 也省流量省电 —— 和「离屏即停 rAF」是同一个取舍。
  // 这里刻意不淡出：标签页已经看不见了，淡不淡没人听得出来，反而拖着一个
  // 定时器在后台空跑。
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      if (!el.paused) {
        resumeAfterHidden = true;
        el.pause();
        paint();
      }
    } else if (resumeAfterHidden) {
      resumeAfterHidden = false;
      start();
    }
  }, { passive: true });

  bar.classList.add('is-ready');
  paint();
  tickProgress();

  // 上次是用户自己按的暂停，这次就别擅自响起来
  if (!wantOff) start();
})();
