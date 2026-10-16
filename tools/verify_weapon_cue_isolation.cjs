const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const path = require('path');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'src/extension.js'), 'utf8');
const profiles = JSON.parse(fs.readFileSync(path.join(root, 'data/calibration/weapon-profiles.json'), 'utf8'));
const calibration = JSON.parse(fs.readFileSync(path.join(root, 'data/calibration/fixed-camera-display.json'), 'utf8'));
function body(name) {
  const start = source.indexOf(`function ${name}(`);
  assert(start >= 0, name);
  let end = source.indexOf('{', start), depth = 1;
  while (depth && ++end < source.length) {
    if (source[end] === '{') depth++;
    if (source[end] === '}') depth--;
  }
  return source.slice(start, end + 1);
}
const names = ['__5ehubRmWrap', '__5ehubRmAngles', '__5ehubDelta', '__5ehubIntegratePunch', '__5ehubLiveRecoil', '__5ehubAim', '__5ehubDisplayAim', '__5ehubCurrentDisplayAim'];
if (source.includes('function __5ehubUsesLiveRecoil(')) names.push('__5ehubUsesLiveRecoil');
const context = vm.createContext({ Math, Date, Instance: { GetGameTime: () => 5 }, __5ehubDisplayCalibration: calibration });
vm.runInContext(names.map(body).join('\n'), context);
context.__5ehubGuideStarted = true;
context.__5ehubNativePunch = {time: 4.99, angle: [-4, 2, 0], velocity: [-20, 12, 0]};
const eye = {x: 0, y: 0, z: 64}, target = {x: 500, y: 100, z: 64};
const plain = x => JSON.parse(JSON.stringify(x));
let cases = 0;
for (const [name, profile] of Object.entries(profiles)) {
  if (name === 'weapon_elite') continue;
  context.__5ehubProfileName = name; context.__5ehubProfile = profile;
  for (const index of [0, 1, Math.floor(profile.recoil.length / 2), profile.recoil.length - 1]) {
    const expected = plain(context.__5ehubDisplayAim(eye, target, index));
    for (const pitch of [0, 4, -7]) {
      context.__5ehubViewDelta = {pitch, yaw: pitch / 2, velocityPitch: 12, velocityYaw: -8, updated: Date.now()/1000};
      assert.deepEqual(plain(context.__5ehubCurrentDisplayAim(eye, target, index)), expected, `${name} cue must stay on its fixed calibrated trajectory`);
      assert.deepEqual(plain(context.__5ehubAim(eye, target, index, true)), plain(context.__5ehubAim(eye, target, index)), `${name} must ignore Dual recoil`);
      cases++;
    }
  }
}
context.__5ehubProfileName = 'weapon_elite'; context.__5ehubProfile = profiles.weapon_elite;
context.__5ehubViewDelta = {pitch: 0, yaw: 0, updated: Date.now()/1000};
const dualA = plain(context.__5ehubCurrentDisplayAim(eye, target, 1));
context.__5ehubNativePunch.angle = [-8, -2, 0];
assert.notDeepEqual(plain(context.__5ehubCurrentDisplayAim(eye, target, 1)), dualA, 'Dual must retain live compensation');
console.log(`PASS: ${cases} automatic-weapon cue cases stay fixed; Dual live recoil remains enabled.`);
