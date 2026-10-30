const DEFAULT_BINDINGS = {
  p1: {
    left: ["KeyA"], right: ["KeyD"], up: ["KeyW"], down: ["KeyS"],
    light: ["KeyJ"], heavy: ["KeyK"], special: ["KeyL"], start: ["Enter"]
  },
  p2: {
    left: ["ArrowLeft"], right: ["ArrowRight"], up: ["ArrowUp"], down: ["ArrowDown"],
    light: ["Numpad1"], heavy: ["Numpad2"], special: ["Numpad3"], start: ["NumpadEnter"]
  }
};

export class InputBuffer {
  constructor(target = window, bindings = DEFAULT_BINDINGS) {
    this.target = target;
    this.bindings = bindings;
    this.held = new Set();
    this.pressed = new Set();
    this.onKeyDown = this.onKeyDown.bind(this);
    this.onKeyUp = this.onKeyUp.bind(this);
    this.onBlur = this.onBlur.bind(this);
    target.addEventListener("keydown", this.onKeyDown);
    target.addEventListener("keyup", this.onKeyUp);
    target.addEventListener("blur", this.onBlur);
  }

  onKeyDown(event) {
    if (!this.held.has(event.code)) this.pressed.add(event.code);
    this.held.add(event.code);
    if (Object.values(this.bindings).some((map) =>
      Object.values(map).some((codes) => codes.includes(event.code)))) {
      event.preventDefault();
    }
  }

  onKeyUp(event) {
    this.held.delete(event.code);
  }

  onBlur() {
    this.held.clear();
    this.pressed.clear();
  }

  codes(player, action) {
    return (this.bindings[player] && this.bindings[player][action]) || [];
  }

  isDown(player, action) {
    return this.codes(player, action).some((code) => this.held.has(code));
  }

  consumePressed(player, action) {
    const match = this.codes(player, action).find((code) => this.pressed.has(code));
    if (!match) return false;
    this.pressed.delete(match);
    return true;
  }

  endFrame() {
    this.pressed.clear();
  }

  destroy() {
    this.target.removeEventListener("keydown", this.onKeyDown);
    this.target.removeEventListener("keyup", this.onKeyUp);
    this.target.removeEventListener("blur", this.onBlur);
    this.onBlur();
  }
}

export { DEFAULT_BINDINGS };
