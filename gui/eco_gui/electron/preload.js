'use strict';
// ページとアプリの窓のつなぎ。ページに出すのは印（gfHost）だけで、操作の口は出さない（ページの出来事を聞くだけ）。
// - gf-raise：開いている画面をもう一度開くよう頼まれた（GUIFrameWork）。窓を前に出し、最小化も戻す。
// - gfHost.openWindows：この窓は人の操作の直後でなくても子の窓を開ける（ポップアップを止めない）と GUIFrameWork に伝える。
//   窓の中に重ねて開く画面を、CLI からの open・時間のかかる実行の後でも、本物の子の窓で開く（main.js の guard が許す）。
const {contextBridge, ipcRenderer} = require('electron');

contextBridge.exposeInMainWorld('gfHost', {openWindows: true});
window.addEventListener('gf-raise', () => ipcRenderer.send('raise'));
