import test from "node:test";
import assert from "node:assert/strict";
import { CombatRuntime } from "../src/engine/CombatRuntime.js";

test("fighter starts at full health and idle", () => {
  const game = new CombatRuntime();
  game.addFighter("A", { x: 0 });
  assert.equal(game.getFighter("A").health, 1000);
  assert.equal(game.getFighter("A").state, "idle");
});

test("attack applies damage only during active frames", () => {
  const game = new CombatRuntime();
  game.addFighter("A", { x: 0, facing: 1 });
  game.addFighter("B", { x: 50, facing: -1 });
  game.startAttack("A", {
    startup: 2, active: 1, recovery: 3, damage: 100, range: 80, hitstun: 5, pushback: 10
  });

  game.tick();
  assert.equal(game.getFighter("B").health, 1000);
  game.tick();
  assert.equal(game.getFighter("B").health, 1000);
  game.tick();
  assert.equal(game.getFighter("B").health, 900);
  assert.equal(game.getFighter("B").state, "hitstun");
});

test("one move cannot hit the same target more than once", () => {
  const game = new CombatRuntime();
  game.addFighter("A", { x: 0 });
  game.addFighter("B", { x: 40 });
  game.startAttack("A", {
    startup: 0, active: 4, recovery: 2, damage: 75, range: 100, hitstun: 2, pushback: 0
  });
  for (let i = 0; i < 6; i += 1) game.tick();
  assert.equal(game.getFighter("B").health, 925);
});

test("out-of-range target is not hit", () => {
  const game = new CombatRuntime();
  game.addFighter("A", { x: 0 });
  game.addFighter("B", { x: 500 });
  game.startAttack("A", { startup: 0, active: 2, range: 40, damage: 200 });
  game.tick();
  game.tick();
  assert.equal(game.getFighter("B").health, 1000);
});
