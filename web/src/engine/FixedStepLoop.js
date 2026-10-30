export class FixedStepLoop {
  constructor({ update, render, stepMs = 1000 / 60, maxFrameMs = 250 }) {
    if (typeof update !== "function" || typeof render !== "function") {
      throw new TypeError("FixedStepLoop requires update and render callbacks.");
    }
    this.update = update;
    this.render = render;
    this.stepMs = stepMs;
    this.maxFrameMs = maxFrameMs;
    this.accumulator = 0;
    this.lastTime = null;
    this.running = false;
    this.rafId = null;
    this.onFrame = this.onFrame.bind(this);
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.lastTime = null;
    this.accumulator = 0;
    this.rafId = requestAnimationFrame(this.onFrame);
  }

  stop() {
    this.running = false;
    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    this.rafId = null;
  }

  onFrame(now) {
    if (!this.running) return;
    if (this.lastTime === null) this.lastTime = now;
    const elapsed = Math.min(now - this.lastTime, this.maxFrameMs);
    this.lastTime = now;
    this.accumulator += elapsed;

    while (this.accumulator >= this.stepMs) {
      this.update(this.stepMs);
      this.accumulator -= this.stepMs;
    }

    this.render(this.accumulator / this.stepMs);
    this.rafId = requestAnimationFrame(this.onFrame);
  }
}
