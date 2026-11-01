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

import { readFileSync } from "node:fs";

test("preview canvas uses verified SWF intrinsic dimensions without 16:9 distortion", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const css = readFileSync(new URL("../src/style.css", import.meta.url), "utf8");
  const match = html.match(/<canvas\s+id="game"\s+width="(\d+)"\s+height="(\d+)"/);
  assert.ok(match, "preview canvas must declare intrinsic dimensions");
  assert.equal(Number(match[1]), ORIGINAL_SWF_STAGE.width);
  assert.equal(Number(match[2]), ORIGINAL_SWF_STAGE.height);
  assert.match(css, /canvas\s*\{[^}]*height:\s*auto;/);
  assert.doesNotMatch(css, /canvas\s*\{[^}]*aspect-ratio:\s*16\s*\/\s*9/);
  assert.match(html, /调试占位画面/);
});
