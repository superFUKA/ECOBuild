'use strict';
// 同じ作業空間に生きたエージェントのタブがあるか（electron なしで試せるよう、index.js から切り出した判定）。
// チーム・受け箱・状態は作業空間ごとに1つなので、2つ目を開くと別の会話が同じものを共有してしまう
const path = require('path');

const sameDir = (a, b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();

// dir の作業空間で動いている（exited でない）作業空間のタブ。オペレーターは対象外。なければ undefined
function liveTabIn(sessions, dir) {
  return sessions.find(x => x.kind === 'workspace' && !x.exited && x.dir && sameDir(x.dir, dir));
}

const BUSY_MESSAGE = 'この作業空間ではもうエージェントが動いています。同じ作業空間に2つ目は開けません（チーム・受け箱を共有してしまいます）。'
  + '別の作業空間で開くか、このタブを使ってください。';

module.exports = {sameDir, liveTabIn, BUSY_MESSAGE};
