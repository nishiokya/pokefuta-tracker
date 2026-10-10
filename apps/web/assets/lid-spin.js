/*
 * スマホだけ、蓋の画像を指で回せるようにする（離すと慣性で回って止まる）。PC とマウスでは何もしない。
 * 404 ページのヤドンの蓋で使う。写真館（nishiokya/pokefuta の src/lib/lid-spin.ts）に同じ処理の写しがある。
 * 片方を変えたらもう片方も揃え、lid-spin.test.js（写真館は tests/lid-spin.test.ts）も通すこと。
 *
 * 決まり:
 * - 動くのは pointer: coarse の端末の、1本目の指（isPrimary）だけ。2本目以降は無視する
 * - TAP_LIMIT 度以上回したら、直後のタッチ由来のクリックだけ止める（蓋を包むリンクを開かず、計測にも数えない）。
 *   ブラウザがクリック自体を出さないこともあるので、止めるのは CLICK_WINDOW ms 以内だけ。
 *   キーボードや読み上げのクリック（detail 0）は止めない
 * - pointercancel（スクロールやピンチでブラウザが操作を引き取った）は、回さず・数えず・何も止めない
 * - 中心付近は角度が定まらない（数 px で半回転に見える）ので、DEAD_ZONE の内側の動きは数えない
 */
(function (root) {
  'use strict';

  var FRICTION = 0.998;     // 1ms あたりの減衰。小さいほど早く止まる
  var MIN_SPEED = 0.02;     // 度/ms。これを下回ったら止める
  var TAP_LIMIT = 8;        // 度。これ以上回したらタップではない
  var DEAD_ZONE = 0.25;     // 蓋の半径に対する割合。この内側の動きは数えない
  var CLICK_WINDOW = 600;   // ms。回し終えてからこの間のクリックだけ止める
  var STILL_MS = 80;        // ms。指を止めてからこれ以上たって離したら慣性を付けない

  function bind(lid, link, onFirstSpin, env) {
    env = env || root;
    if (!env.matchMedia || !env.matchMedia('(pointer: coarse)').matches) return function () {};
    var reduce = env.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var angle = 0, velocity = 0, lastAngle = null, lastTime = 0, moved = 0;
    var pointer = null, frame = 0, spun = false, swallowUntil = 0;

    function now() { return env.performance.now(); }
    function polar(e) {
      var r = lid.getBoundingClientRect();
      var dx = e.clientX - (r.left + r.width / 2);
      var dy = e.clientY - (r.top + r.height / 2);
      return {
        angle: Math.atan2(dy, dx) * 180 / Math.PI,
        inner: Math.sqrt(dx * dx + dy * dy) < Math.min(r.width, r.height) / 2 * DEAD_ZONE
      };
    }
    function draw() { lid.style.transform = 'rotate(' + angle + 'deg)'; }
    function stopInertia() {
      if (frame) env.cancelAnimationFrame(frame);
      frame = 0;
    }

    function onDown(e) {
      if (e.pointerType !== 'touch' || !e.isPrimary || pointer !== null) return;
      pointer = e.pointerId;
      stopInertia();
      velocity = 0; moved = 0; swallowUntil = 0;
      var p = polar(e);
      lastAngle = p.inner ? null : p.angle;
      lastTime = e.timeStamp;
      try { lid.setPointerCapture(e.pointerId); } catch (err) { /* 合成イベントなど */ }
    }
    function onMove(e) {
      if (e.pointerId !== pointer) return;
      var p = polar(e);
      if (p.inner) { lastAngle = null; return; }
      if (lastAngle === null) { lastAngle = p.angle; lastTime = e.timeStamp; return; }
      var d = p.angle - lastAngle;
      if (d > 180) d -= 360; else if (d < -180) d += 360;
      var dt = Math.max(1, e.timeStamp - lastTime);
      angle += d;
      moved += Math.abs(d);
      velocity = velocity * 0.6 + (d / dt) * 0.4;
      lastAngle = p.angle;
      lastTime = e.timeStamp;
      draw();
    }
    function onUp(e) {
      if (e.pointerId !== pointer) return;
      pointer = null;
      if (moved < TAP_LIMIT) return; // タップ。クリックはそのまま通す
      swallowUntil = now() + CLICK_WINDOW;
      if (!spun) { spun = true; onFirstSpin(); }
      if (reduce || e.timeStamp - lastTime > STILL_MS) return;
      var prev = now();
      frame = env.requestAnimationFrame(function step(t) {
        var dt = t - prev;
        prev = t;
        velocity *= Math.pow(FRICTION, dt);
        if (Math.abs(velocity) < MIN_SPEED) { frame = 0; return; }
        angle += velocity * dt;
        draw();
        frame = env.requestAnimationFrame(step);
      });
    }
    function onCancel(e) {
      if (e.pointerId !== pointer) return;
      pointer = null;
      velocity = 0;
      swallowUntil = 0;
    }
    function onClick(e) {
      if (swallowUntil && e.detail !== 0 && now() < swallowUntil) {
        // 遷移もクリック計測（document への委譲や React の onClick）も止める
        e.preventDefault();
        e.stopPropagation();
      }
      swallowUntil = 0;
    }
    function onContextMenu(e) { e.preventDefault(); } // Android の長押しメニュー（iOS は CSS の touch-callout）

    lid.addEventListener('pointerdown', onDown);
    lid.addEventListener('pointermove', onMove);
    lid.addEventListener('pointerup', onUp);
    lid.addEventListener('pointercancel', onCancel);
    lid.addEventListener('contextmenu', onContextMenu);
    link.addEventListener('click', onClick);
    return function unbind() {
      stopInertia();
      lid.removeEventListener('pointerdown', onDown);
      lid.removeEventListener('pointermove', onMove);
      lid.removeEventListener('pointerup', onUp);
      lid.removeEventListener('pointercancel', onCancel);
      lid.removeEventListener('contextmenu', onContextMenu);
      link.removeEventListener('click', onClick);
    };
  }

  var api = { bind: bind, TAP_LIMIT: TAP_LIMIT, CLICK_WINDOW: CLICK_WINDOW };
  root.PokefutaLidSpin = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : this);
