import { FixedStepLoop } from "./engine/FixedStepLoop.js";
import { InputBuffer } from "./engine/InputBuffer.js";
import { CombatRuntime } from "./engine/CombatRuntime.js";
import { ORIGINAL_SWF_STAGE } from "./engine/OriginalStage.js";

const canvas = document.querySelector("#game");
// Keep the intrinsic bitmap at the byte-verified SWF RECT; CSS scales it responsively.
canvas.width = ORIGINAL_SWF_STAGE.width;
canvas.height = ORIGINAL_SWF_STAGE.height;
const STAGE_WIDTH = ORIGINAL_SWF_STAGE.width;
const STAGE_HEIGHT = ORIGINAL_SWF_STAGE.height;
const context = canvas.getContext("2d");
const frameCounter = document.querySelector("#frame-counter");
const input = new InputBuffer(window);
const combat = new CombatRuntime();

combat.addFighter("P1", { x: 220, facing: 1 });
combat.addFighter("P2", { x: 440, facing: -1 });

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
  const y = 370;
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
  context.fillText(label + " / " + fighter.state.toUpperCase(), x, 404);
}

function render() {
  const gradient = context.createLinearGradient(0, 0, 0, STAGE_HEIGHT);
  gradient.addColorStop(0, "#171f36");
  gradient.addColorStop(0.58, "#29334a");
  gradient.addColorStop(1, "#0b101c");
  context.fillStyle = gradient;
  context.fillRect(0, 0, STAGE_WIDTH, STAGE_HEIGHT);

  context.fillStyle = "#ffffff08";
  for (let x = 0; x < STAGE_WIDTH; x += 33) context.fillRect(x, 0, 1, 420);
  for (let y = 0; y < 420; y += 33) context.fillRect(0, y, STAGE_WIDTH, 1);

  context.fillStyle = "#d3a65b";
  context.font = "900 35px Segoe UI, sans-serif";
  context.textAlign = "center";
  context.fillText("KOF WING 1.4", STAGE_WIDTH / 2, 76);
  context.fillStyle = "#d6deed";
  context.font = "12px Segoe UI, sans-serif";
  context.fillText("HTML5 COMBAT RUNTIME — DEBUG ONLY", STAGE_WIDTH / 2, 102);

  const p1 = combat.getFighter("P1");
  const p2 = combat.getFighter("P2");
  drawHealth(25, 132, 245, p1);
  drawHealth(390, 132, 245, p2);
  drawFighter(p1, "#5c91c7", "PLAYER 1");
  drawFighter(p2, "#bd6d64", "PLAYER 2");

  context.fillStyle = "#080b12";
  context.fillRect(0, 420, STAGE_WIDTH, STAGE_HEIGHT - 420);
  context.fillStyle = "#e7bd72";
  context.font = "bold 12px Segoe UI, sans-serif";
  context.fillText("ORIGINAL SWF 660x485 @ 32FPS — ASSETS NOT IMPORTED", STAGE_WIDTH / 2, 448);
  context.fillStyle = "#aeb9ce";
  context.font = "11px Segoe UI, sans-serif";
  context.fillText("P1: A/D · J/K/L   |   P2: 方向键 · Num1/2/3   |   DEBUG VALUES ONLY", STAGE_WIDTH / 2, 472);
}

// Match the source SWF tick and intrinsic RECT; visuals and combat values remain debug-only.
const loop = new FixedStepLoop({ update, render, stepMs: 1000 / ORIGINAL_SWF_STAGE.frameRate });
loop.start();

window.addEventListener("beforeunload", () => {
  loop.stop();
  input.destroy();
});
