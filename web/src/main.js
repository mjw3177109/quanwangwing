import { FixedStepLoop } from "./engine/FixedStepLoop.js";
import { InputBuffer } from "./engine/InputBuffer.js";
import { CombatRuntime } from "./engine/CombatRuntime.js";
import { ORIGINAL_SWF_STAGE } from "./engine/OriginalStage.js";

const canvas = document.querySelector("#game");
const context = canvas.getContext("2d");
const frameCounter = document.querySelector("#frame-counter");
const input = new InputBuffer(window);
const combat = new CombatRuntime();

combat.addFighter("P1", { x: 345, facing: 1 });
combat.addFighter("P2", { x: 615, facing: -1 });

const moves = {
  light: { startup: 3, active: 2, recovery: 8, damage: 45, range: 112, hitstun: 12, pushback: 16 },
  heavy: { startup: 8, active: 3, recovery: 17, damage: 105, range: 135, hitstun: 22, pushback: 30 },
  special: { startup: 12, active: 5, recovery: 24, damage: 180, range: 210, hitstun: 32, pushback: 45 }
};

function update() {
  if (input.consumePressed("p1", "light")) combat.startAttack("P1", moves.light);
  if (input.consumePressed("p1", "heavy")) combat.startAttack("P1", moves.heavy);
  if (input.consumePressed("p1", "special")) combat.startAttack("P1", moves.special);

  if (input.consumePressed("p2", "light")) combat.startAttack("P2", moves.light);
  if (input.consumePressed("p2", "heavy")) combat.startAttack("P2", moves.heavy);
  if (input.consumePressed("p2", "special")) combat.startAttack("P2", moves.special);

  const p1 = combat.getFighter("P1");
  if (p1 && p1.state === "idle") {
    if (input.isDown("p1", "left")) combat.fighters.get("P1").x -= 3;
    if (input.isDown("p1", "right")) combat.fighters.get("P1").x += 3;
  }
  const p2 = combat.getFighter("P2");
  if (p2 && p2.state === "idle") {
    if (input.isDown("p2", "left")) combat.fighters.get("P2").x -= 3;
    if (input.isDown("p2", "right")) combat.fighters.get("P2").x += 3;
  }

  combat.tick();
  input.endFrame();
  frameCounter.textContent = "FRAME " + String(combat.frame).padStart(6, "0");
}

function drawHealth(x, y, width, fighter) {
  context.fillStyle = "#141927";
  context.fillRect(x, y, width, 13);
  context.fillStyle = fighter.health > 300 ? "#d9a94f" : "#d45d58";
  context.fillRect(x, y, width * (fighter.health / fighter.maxHealth), 13);
  context.strokeStyle = "#f3d49a";
  context.strokeRect(x, y, width, 13);
}

function drawFighter(fighter, color, label) {
  const x = fighter.x;
  const y = 395;
  context.save();
  context.translate(x, y);
  context.scale(fighter.facing, 1);
  context.fillStyle = color;
  context.fillRect(-25, -92, 50, 92);
  context.fillStyle = "#f2d6b1";
  context.beginPath();
  context.arc(0, -111, 19, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = "#111827";
  context.fillRect(5, -117, 5, 4);
  if (fighter.state === "attack") {
    context.fillStyle = "#f4c66e99";
    context.fillRect(20, -76, 100, 44);
  }
  context.restore();

  context.fillStyle = "#e9edf6";
  context.font = "bold 12px Segoe UI, sans-serif";
  context.textAlign = "center";
  context.fillText(label + " / " + fighter.state.toUpperCase(), x, 420);
}

function render() {
  const gradient = context.createLinearGradient(0, 0, 0, 540);
  gradient.addColorStop(0, "#171f36");
  gradient.addColorStop(0.58, "#29334a");
  gradient.addColorStop(1, "#0b101c");
  context.fillStyle = gradient;
  context.fillRect(0, 0, 960, 540);

  context.fillStyle = "#ffffff08";
  for (let x = 0; x < 960; x += 48) context.fillRect(x, 0, 1, 470);
  for (let y = 0; y < 470; y += 48) context.fillRect(0, y, 960, 1);

  context.fillStyle = "#d3a65b";
  context.font = "900 35px Segoe UI, sans-serif";
  context.textAlign = "center";
  context.fillText("KOF WING 1.4", 480, 88);
  context.fillStyle = "#d6deed";
  context.font = "12px Segoe UI, sans-serif";
  context.fillText("HTML5 COMBAT RUNTIME — FOUNDATION BUILD", 480, 113);

  const p1 = combat.getFighter("P1");
  const p2 = combat.getFighter("P2");
  drawHealth(80, 145, 340, p1);
  drawHealth(540, 145, 340, p2);
  drawFighter(p1, "#5c91c7", "PLAYER 1");
  drawFighter(p2, "#bd6d64", "PLAYER 2");

  context.fillStyle = "#080b12";
  context.fillRect(0, 465, 960, 75);
  context.fillStyle = "#e7bd72";
  context.font = "bold 12px Segoe UI, sans-serif";
  context.fillText("ORIGINAL SWF 660x485 @ 32FPS — ASSETS NOT IMPORTED", 480, 493);
  context.fillStyle = "#aeb9ce";
  context.font = "11px Segoe UI, sans-serif";
  context.fillText("P1: A / D 移动 · J 轻击 · K 重击 · L 特殊技     P2: 方向键移动 · Num1 / Num2 / Num3 攻击", 480, 517);
}

// Match the source SWF simulation tick; the 960x540 canvas remains a debug-only viewport.
const loop = new FixedStepLoop({ update, render, stepMs: 1000 / ORIGINAL_SWF_STAGE.frameRate });
loop.start();

window.addEventListener("beforeunload", () => {
  loop.stop();
  input.destroy();
});
