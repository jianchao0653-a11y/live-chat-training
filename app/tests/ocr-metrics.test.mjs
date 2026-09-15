import test from 'node:test';
import assert from 'node:assert/strict';
import {ocrMetrics,editDistance} from '../evals/ocr-metrics.mjs';
test('OCR metrics count Unicode characters and catch wrong speaker attribution',()=>{
  assert.equal(editDistance('😀好','😀号'),1);
  assert.equal(ocrMetrics('对方：你好\n我：在的','对方：你好\n我：在的').characterErrorRate,0);
  assert.equal(ocrMetrics('对方：你好\n我：在的','我：你好\n对方：在的').orderedSpeakerLineAccuracy,0);
  assert.ok(ocrMetrics('我：好','我：好\n未知：多一行').characterErrorRate>0);
  assert.equal(ocrMetrics('未知：模糊','模糊').orderedSpeakerLineAccuracy,0);
});
