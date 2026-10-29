/**
 * A short two-tone alarm made with the Web Audio API (no sound files).
 * Browsers only allow audio after the user has interacted with the page, so
 * playAlarm() resolves to false when sound is blocked or unavailable and the
 * caller shows a visual fallback instead.
 */
let ctx = null;

export async function unlockAudio() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return false;
    ctx = ctx || new Ctx();
    if (ctx.state === 'suspended') await ctx.resume();
    return ctx.state === 'running';
  } catch {
    return false;
  }
}

export async function playAlarm() {
  if (!(await unlockAudio())) return false;
  try {
    const start = ctx.currentTime;
    [880, 660, 880, 660].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'square';
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, start + i * 0.18);
      gain.gain.exponentialRampToValueAtTime(0.15, start + i * 0.18 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + i * 0.18 + 0.16);
      osc.connect(gain).connect(ctx.destination);
      osc.start(start + i * 0.18);
      osc.stop(start + i * 0.18 + 0.17);
    });
    return true;
  } catch {
    return false;
  }
}
