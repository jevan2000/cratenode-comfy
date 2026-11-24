// CrateNode-Comfy: run "just before each run" hooks once per queued prompt.
//
// Palette Generator (new_each_run) and Fluid Gradient (randomize) write new values into
// their fields just before a run, so the queued prompt carries them. ComfyUI's
// app.queuePrompt(number, batchCount, options) builds all `batchCount` prompts inside one
// call, so a hook that runs once per call gave every prompt in a batch the same values,
// and ComfyUI then reused the first result for the rest ("queued 5, got 1").
//
// This wraps app.queuePrompt once: a batch of N becomes N calls of one prompt each, with
// every registered hook awaited before each. Seeds with "control after generate" still
// step once per prompt, as before.

const { app } = window.comfyAPI.app;

const hooks = (window.__cratenodeBeforeRun = window.__cratenodeBeforeRun || []);

export function onBeforeRun(fn) {
  if (!hooks.includes(fn)) hooks.push(fn);
  install();
}

async function runHooks() {
  for (const fn of hooks) {
    try { await fn(); } catch (e) { console.warn("CrateNode before run:", e); }
  }
}

function install() {
  const queue = app.queuePrompt;
  if (typeof queue !== "function" || queue.cnBeforeRun) return;
  const wrapped = async function (number, batchCount = 1, ...rest) {
    if (!hooks.length) return queue.call(this, number, batchCount, ...rest);
    const n = Math.max(1, Number(batchCount) || 1);
    let ok = false;
    for (let i = 0; i < n; i++) {
      await runHooks();
      ok = (await queue.call(this, number, 1, ...rest)) || ok;
    }
    return ok;
  };
  wrapped.cnBeforeRun = true;
  app.queuePrompt = wrapped;
}
