'use strict';
// ページとアプリの窓のつなぎ。ページに口は出さない（ページの出来事を聞くだけ）。
// - gf-raise：開いている画面をもう一度開くよう頼まれた（GUIFrameWork）。窓を前に出し、最小化も戻す。
const {ipcRenderer} = require('electron');

window.addEventListener('gf-raise', () => ipcRenderer.send('raise'));
