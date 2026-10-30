import test from "node:test";
import assert from "node:assert/strict";
import { ORIGINAL_SWF_STAGE } from "../src/engine/OriginalStage.js";

test("source SWF stage dimensions and tick rate are locked", () => {
  assert.equal(ORIGINAL_SWF_STAGE.width, 660);
  assert.equal(ORIGINAL_SWF_STAGE.height, 485);
  assert.equal(ORIGINAL_SWF_STAGE.frameRate, 32);
  assert.equal(ORIGINAL_SWF_STAGE.mainTimelineFrames, 39);
  assert.equal(ORIGINAL_SWF_STAGE.sourceSha256.length, 64);
});
