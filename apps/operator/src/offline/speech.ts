// Audio opcional (Web Speech API) para instrucciones críticas.
let enabled = false;

export function setSpeechEnabled(v: boolean) {
  enabled = v;
  if (!v && typeof speechSynthesis !== 'undefined') speechSynthesis.cancel();
}

export function speak(text: string, force = false) {
  if ((!enabled && !force) || typeof speechSynthesis === 'undefined') return;
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'es-MX';
    u.rate = 0.95;
    speechSynthesis.speak(u);
  } catch {
    /* sin soporte */
  }
}
