// Unit checks for the pure helpers in static/app.js (run: node tests/ui_logic.js)
const assert = require('assert');
const u = require('../static/app.js');

assert.strictEqual(u.stepTarget(70, 1, 50, 85), 71);
assert.strictEqual(u.stepTarget(85, 1, 50, 85), 85);
assert.strictEqual(u.stepTarget(50, -1, 50, 85), 50);
assert.strictEqual(u.stepTarget(70.4, 1, 50, 85), 71);
assert.strictEqual(u.fmtNum(70), '70');
assert.strictEqual(u.fmtNum(70.5), '70.5');
assert.strictEqual(u.ageText(2), 'just now');
assert.strictEqual(u.ageText(30), '30s ago');
assert.strictEqual(u.ageText(300), '5 min ago');
assert.strictEqual(u.ageText(7300), '2 h ago');
assert.strictEqual(u.retryText('30'), '30 seconds');
assert.strictEqual(u.retryText('600'), '10 minutes');
assert.strictEqual(u.retryText(null), 'a little while');

const st = { mode: 'HEAT', target: 70 };
assert.strictEqual(u.isDirty({ mode: 'HEAT', target: 70 }, st), false);
assert.strictEqual(u.isDirty({ mode: 'HEAT', target: 71 }, st), true);
assert.strictEqual(u.isDirty({ mode: 'COOL', target: 70 }, st), true);
assert.strictEqual(u.isDirty({ mode: 'FAN', target: 70 }, { mode: 'FAN', target: 55 }), false); // target ignored
assert.strictEqual(u.isDirty({ mode: 'HEAT', target: 70 }, null), false);

assert.deepStrictEqual(u.buildSetBody({ mode: 'HEAT', target: 70 }, null), { mode: 'HEAT', target: 70 });
assert.deepStrictEqual(u.buildSetBody({ mode: 'FAN', target: 70 }, null), { mode: 'FAN' });
assert.deepStrictEqual(u.buildSetBody({ mode: 'COOL', target: 74 }, 'X'), { mode: 'COOL', target: 74, start_at: 'X' });

assert.strictEqual(u.activityText({ activity: 'heating', relays: { heat2: true } }), 'Heating · stage 2');
assert.strictEqual(u.activityText({ activity: 'idle', relays: {} }), 'Idle');
assert.strictEqual(u.localInputValue(new Date(2030, 0, 5, 7, 8)), '2030-01-05T07:08');
console.log('ui logic OK');
