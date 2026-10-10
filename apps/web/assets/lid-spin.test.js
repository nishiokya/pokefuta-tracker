// node apps/web/assets/lid-spin.test.js
// 写真館の tests/lid-spin.test.ts と同じ筋書き。片方を変えたら揃える
const assert = require('node:assert/strict');
const { bind, CLICK_WINDOW } = require('./lid-spin.js');

function setup({ coarse = true, reduce = false } = {}) {
  let clock = 0;
  const frames = new Map();
  let nextFrame = 1;
  const env = {
    matchMedia: (q) => ({ matches: q.includes('coarse') ? coarse : q.includes('reduced-motion') ? reduce : false }),
    performance: { now: () => clock },
    requestAnimationFrame: (cb) => { const id = nextFrame++; frames.set(id, cb); return id; },
    cancelAnimationFrame: (id) => frames.delete(id),
  };
  const element = () => {
    const handlers = {};
    return {
      handlers, style: {},
      addEventListener: (t, f) => { handlers[t] = f; },
      removeEventListener: (t) => { delete handlers[t]; },
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 200, height: 200 }),
      setPointerCapture() {},
    };
  };
  const lid = element();
  const link = element();
  let spins = 0;
  bind(lid, link, () => { spins += 1; }, env);

  // 中心 (100,100) から半径 radius・角度 deg の位置
  const at = (deg, radius = 80) => ({
    clientX: 100 + radius * Math.cos((deg * Math.PI) / 180),
    clientY: 100 + radius * Math.sin((deg * Math.PI) / 180),
  });
  const pointer = (type, deg, extra = {}) => {
    const f = lid.handlers[type];
    if (f) f({ pointerId: 1, pointerType: 'touch', isPrimary: true, timeStamp: clock, preventDefault() {}, ...at(deg, extra.radius), ...extra });
  };
  const advance = (ms) => { clock += ms; };
  // 慣性を最後まで回す（16ms ごと）
  const settle = () => {
    for (let i = 0; i < 2000 && frames.size; i++) {
      const [[id, cb]] = frames;
      frames.delete(id);
      clock += 16;
      cb(clock);
    }
  };
  const click = (detail = 1) => {
    const e = { detail, prevented: false, stopped: false, preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; } };
    if (link.handlers.click) link.handlers.click(e);
    return { opened: !e.prevented, counted: !e.stopped };
  };
  const angle = () => Number((lid.style.transform || 'rotate(0deg)').match(/-?[\d.]+/)[0]);
  // 0° から to° まで、16ms ごとに step° ずつ回して離す
  const drag = (to, step = 15, extra = {}) => {
    pointer('pointerdown', 0, extra);
    for (let d = step; Math.abs(d) <= Math.abs(to); d += step) { advance(16); pointer('pointermove', d, extra); }
    pointer('pointerup', to, extra);
  };
  return { lid, link, pointer, advance, settle, click, angle, drag, spins: () => spins, frames };
}

const tests = {
  'タップはリンクを開き、計測にも数える'() {
    const t = setup();
    t.pointer('pointerdown', 0);
    t.advance(60);
    t.pointer('pointerup', 3);
    assert.deepEqual(t.click(), { opened: true, counted: true });
    assert.equal(t.spins(), 0);
  },
  '回したら慣性で回って止まり、直後のクリックは開かない'() {
    const t = setup();
    t.drag(60);
    // ブラウザは指を離した直後にクリックを出す
    assert.deepEqual(t.click(), { opened: false, counted: false });
    assert.equal(t.spins(), 1);
    const released = t.angle();
    t.settle();
    assert.ok(t.angle() > released + 90, `慣性で回る: ${released} → ${t.angle()}`);
    assert.equal(t.frames.size, 0, '止まったらフレームを残さない');
  },
  'ブラウザがクリックを出さなかったとき、次の正当なクリックは止めない'() {
    const t = setup();
    t.drag(60);
    t.advance(CLICK_WINDOW + 1);
    assert.deepEqual(t.click(), { opened: true, counted: true });
  },
  'キーボード・読み上げのクリック（detail 0）は回した直後でも止めない'() {
    const t = setup();
    t.drag(60);
    assert.deepEqual(t.click(0), { opened: true, counted: true });
  },
  '止めるのは1回だけ'() {
    const t = setup();
    t.drag(60);
    t.click();
    assert.deepEqual(t.click(), { opened: true, counted: true });
  },
  '2本目の指は無視し、1本目の回転を上書きしない'() {
    const t = setup();
    t.pointer('pointerdown', 0);
    for (let d = 15; d <= 60; d += 15) { t.advance(16); t.pointer('pointermove', d); }
    t.pointer('pointerdown', 200, { pointerId: 2, isPrimary: false });
    t.pointer('pointermove', 210, { pointerId: 2, isPrimary: false });
    t.pointer('pointerup', 210, { pointerId: 2, isPrimary: false });
    t.pointer('pointerup', 60);
    assert.deepEqual(t.click(), { opened: false, counted: false });
    assert.equal(t.spins(), 1);
  },
  'pointercancel では回さず・数えず・クリックも止めない'() {
    const t = setup();
    t.pointer('pointerdown', 0);
    for (let d = 15; d <= 60; d += 15) { t.advance(16); t.pointer('pointermove', d); }
    t.pointer('pointercancel', 60);
    assert.equal(t.frames.size, 0);
    assert.equal(t.spins(), 0);
    assert.deepEqual(t.click(), { opened: true, counted: true });
  },
  '±180° をまたいでも短い向きに回る'() {
    const t = setup();
    t.pointer('pointerdown', 170);
    t.advance(16);
    t.pointer('pointermove', 190); // atan2 では -170°
    t.advance(200);
    t.pointer('pointerup', 190);
    assert.ok(Math.abs(t.angle() - 20) < 1e-6, `20° 回る: ${t.angle()}`);
  },
  '中心付近の指のぶれは回転に数えない'() {
    const t = setup();
    t.pointer('pointerdown', 0, { radius: 5 });
    t.advance(16);
    t.pointer('pointermove', 180, { radius: 5 }); // 中心をはさんで数 px 動いただけ
    t.advance(16);
    t.pointer('pointerup', 180, { radius: 5 });
    assert.equal(t.angle(), 0);
    assert.deepEqual(t.click(), { opened: true, counted: true });
  },
  'マウスでは何もしない'() {
    const t = setup();
    t.drag(90, 15, { pointerType: 'mouse' });
    assert.equal(t.angle(), 0);
    assert.deepEqual(t.click(), { opened: true, counted: true });
  },
  'PC（pointer: fine）では何も付けない'() {
    const t = setup({ coarse: false });
    assert.deepEqual(Object.keys(t.lid.handlers), []);
    assert.deepEqual(Object.keys(t.link.handlers), []);
  },
  'prefers-reduced-motion では慣性を付けない'() {
    const t = setup({ reduce: true });
    t.drag(60);
    assert.equal(t.frames.size, 0);
    assert.deepEqual(t.click(), { opened: false, counted: false });
  },
  '指を止めてから離したら慣性を付けない'() {
    const t = setup();
    t.pointer('pointerdown', 0);
    for (let d = 15; d <= 60; d += 15) { t.advance(16); t.pointer('pointermove', d); }
    t.advance(200);
    t.pointer('pointerup', 60);
    assert.equal(t.frames.size, 0);
  },
};

let failed = 0;
for (const [name, fn] of Object.entries(tests)) {
  try { fn(); console.log(`ok - ${name}`); } catch (e) { failed += 1; console.log(`not ok - ${name}\n  ${e.message}`); }
}
if (failed) { console.log(`${failed} failed`); process.exit(1); }
console.log(`${Object.keys(tests).length} passed`);
