'use strict';
// 返答の知らせの音（ファイルを使わず Web Audio で作る、短く柔らかい音）。window.html・dock.html から読む。
// ECOSounds.play(id, volume)：volume は 0〜1。ECOSounds.list：選べる音。
(() => {
  let context = null;
  const audio = () => {
    if (!context) context = new AudioContext();
    if (context.state === 'suspended') context.resume();
    return context;
  };
  // 1つの音。f：周波数、at：始まり（秒）、len：長さ、to：終わりの周波数（音程を滑らせる）
  function tone(out, {type = 'sine', f, at = 0, len = 0.6, gain = 1, to = null, attack = 0.012}) {
    const c = out.context, t = c.currentTime + at;
    const osc = c.createOscillator(), env = c.createGain();
    osc.type = type; osc.frequency.setValueAtTime(f, t);
    if (to) osc.frequency.exponentialRampToValueAtTime(to, t + len * 0.6);
    env.gain.setValueAtTime(0.0001, t);
    env.gain.exponentialRampToValueAtTime(gain, t + attack);
    env.gain.exponentialRampToValueAtTime(0.0001, t + len);
    osc.connect(env).connect(out); osc.start(t); osc.stop(t + len + 0.05);
  }
  // 少しこもらせて、耳に痛くないように
  function output(volume) {
    const c = audio(), master = c.createGain(), low = c.createBiquadFilter();
    master.gain.value = Math.max(0, Math.min(1, volume)) * 0.35;
    low.type = 'lowpass'; low.frequency.value = 4200;
    master.connect(low).connect(c.destination);
    return master;
  }
  const bell = (o, f, at, len, gain) => { tone(o, {f, at, len, gain}); tone(o, {f: f * 2.01, at, len: len * 0.5, gain: gain * 0.18}); };
  const SOUNDS = {
    chime: {label: 'チャイム', play: o => { bell(o, 659, 0, 0.9, 0.8); bell(o, 880, 0.14, 1.1, 0.7); }},
    pop: {label: 'ポン', play: o => tone(o, {f: 740, to: 520, len: 0.22, gain: 0.9, attack: 0.005})},
    drop: {label: 'しずく', play: o => { tone(o, {f: 520, to: 1250, len: 0.18, gain: 0.7, attack: 0.004}); tone(o, {f: 1250, at: 0.11, len: 0.35, gain: 0.25}); }},
    marimba: {label: 'マリンバ', play: o => [523, 659, 784].forEach((f, i) => tone(o, {type: 'triangle', f, at: i * 0.09, len: 0.35, gain: 0.7, attack: 0.004}))},
    koto: {label: '琴', play: o => [587, 880, 1175].forEach((f, i) => tone(o, {type: 'triangle', f, at: i * 0.06, len: 1.0, gain: 0.45, attack: 0.003}))},
    bell: {label: 'ベル', play: o => { bell(o, 1047, 0, 1.6, 0.6); bell(o, 1319, 0.02, 1.4, 0.25); }},
    soft: {label: 'そよかぜ', play: o => { tone(o, {f: 392, len: 0.7, gain: 0.5, attack: 0.08}); tone(o, {f: 587, at: 0.12, len: 0.8, gain: 0.35, attack: 0.08}); }},
  };
  window.ECOSounds = {
    list: Object.entries(SOUNDS).map(([id, s]) => ({id, label: s.label})),
    play(id, volume = 0.6) {
      const s = SOUNDS[id];
      if (!s || volume <= 0) return;
      try { s.play(output(volume)); } catch (e) { /* 音が出せなくても知らせは続ける */ }
    },
  };
})();
