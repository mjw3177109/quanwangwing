const DEFAULT_MOVE = Object.freeze({
  startup: 4,
  active: 2,
  recovery: 10,
  damage: 60,
  range: 90,
  hitstun: 12,
  pushback: 18
});

export class CombatRuntime {
  constructor() {
    this.frame = 0;
    this.fighters = new Map();
  }

  addFighter(id, options = {}) {
    if (this.fighters.has(id)) throw new Error("Fighter already exists: " + id);
    const maxHealth = Number(options.maxHealth || 1000);
    const fighter = {
      id,
      x: Number(options.x || 0),
      y: Number(options.y || 0),
      facing: options.facing === -1 ? -1 : 1,
      maxHealth,
      health: maxHealth,
      state: "idle",
      stateFrames: 0,
      move: null,
      moveFrame: 0,
      hitTargets: new Set(),
      hitstop: 0
    };
    this.fighters.set(id, fighter);
    return this.snapshotFighter(fighter);
  }

  getFighter(id) {
    const fighter = this.fighters.get(id);
    return fighter ? this.snapshotFighter(fighter) : null;
  }

  startAttack(id, definition = {}) {
    const fighter = this.fighters.get(id);
    if (!fighter || !["idle", "recovery"].includes(fighter.state)) return false;
    fighter.move = { ...DEFAULT_MOVE, ...definition };
    fighter.moveFrame = 0;
    fighter.hitTargets.clear();
    fighter.state = "attack";
    fighter.stateFrames = 0;
    return true;
  }

  tick() {
    this.frame += 1;
    for (const fighter of this.fighters.values()) {
      if (fighter.hitstop > 0) {
        fighter.hitstop -= 1;
        continue;
      }
      if (fighter.state === "hitstun") {
        fighter.stateFrames -= 1;
        if (fighter.stateFrames <= 0) {
          fighter.state = "idle";
          fighter.stateFrames = 0;
        }
      } else if (fighter.state === "attack" && fighter.move) {
        fighter.moveFrame += 1;
        fighter.stateFrames = fighter.moveFrame;
      }
    }

    for (const attacker of this.fighters.values()) {
      if (attacker.state !== "attack" || !attacker.move) continue;
      const firstActive = attacker.move.startup + 1;
      const lastActive = attacker.move.startup + attacker.move.active;
      if (attacker.moveFrame < firstActive || attacker.moveFrame > lastActive) continue;

      for (const target of this.fighters.values()) {
        if (target.id === attacker.id || attacker.hitTargets.has(target.id)) continue;
        if (target.state === "ko") continue;
        const distance = Math.abs(target.x - attacker.x);
        if (distance > attacker.move.range) continue;
        attacker.hitTargets.add(target.id);
        target.health = Math.max(0, target.health - attacker.move.damage);
        target.state = target.health === 0 ? "ko" : "hitstun";
        target.stateFrames = target.health === 0 ? 0 : attacker.move.hitstun;
        target.x += attacker.facing * attacker.move.pushback;
      }
    }

    for (const fighter of this.fighters.values()) {
      if (fighter.state === "attack" && fighter.move) {
        const endFrame = fighter.move.startup + fighter.move.active + fighter.move.recovery;
        if (fighter.moveFrame > endFrame) {
          fighter.state = "idle";
          fighter.stateFrames = 0;
          fighter.move = null;
          fighter.moveFrame = 0;
          fighter.hitTargets.clear();
        }
      }
    }
  }

  snapshotFighter(fighter) {
    return {
      id: fighter.id,
      x: fighter.x,
      y: fighter.y,
      facing: fighter.facing,
      maxHealth: fighter.maxHealth,
      health: fighter.health,
      state: fighter.state,
      stateFrames: fighter.stateFrames,
      moveFrame: fighter.moveFrame
    };
  }

  snapshot() {
    return {
      frame: this.frame,
      fighters: Array.from(this.fighters.values(), (fighter) => this.snapshotFighter(fighter))
    };
  }
}
