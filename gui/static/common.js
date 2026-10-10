'use strict';
// Shared by every page: talking to the local server, running ecobuild commands, dialogs and notifications.
const ECO = (() => {
  const params = new URLSearchParams(location.search);
  // The server makes a new token every start. It arrives on the first URL and is kept for the other windows.
  if (params.get('t')) {
    try { localStorage.setItem('ecobuild-gui-token', params.get('t')); } catch (e) { /* storage blocked */ }
  }
  let token = params.get('t') || '';
  try { token = token || localStorage.getItem('ecobuild-gui-token') || ''; } catch (e) { /* storage blocked */ }

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

  async function call(api, body = {}) {
    let response;
    try {
      response = await fetch('/api/' + api, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-ECOBuild-Token': token}, body: JSON.stringify(body)});
    } catch (e) {
      throw new Error('GUIのサーバーにつながりません。ecobuild-gui を起動し直してください。');
    }
    const data = await response.json().catch(() => ({error: 'サーバーの応答を読めませんでした。'}));
    if (data.error) throw new Error(data.error);
    return data.value;
  }

  // Running commands, shown at the bottom left so long operations (build, clone) are visible.
  const running = document.createElement('div'); running.className = 'eco-running'; running.setAttribute('aria-live', 'polite');
  const toasts = document.createElement('div'); toasts.className = 'eco-toasts'; toasts.setAttribute('role', 'status');
  document.addEventListener('DOMContentLoaded', () => document.body.append(running, toasts));

  function toast(message, kind = 'ok', ms = 4500) {
    const item = document.createElement('div'); item.className = 'eco-toast ' + kind; item.textContent = message;
    toasts.append(item); setTimeout(() => item.remove(), ms);
  }

  const label = args => args.filter(a => a !== '--yes').slice(0, 4).join(' ');
  async function cli(dir, args, {stdin, quiet = false} = {}) {
    let row;
    if (!quiet) { row = document.createElement('div'); row.innerHTML = `<span class="eco-spinner"></span><span>実行中</span><code>ecobuild ${esc(label(args))}</code>`; running.append(row); }
    try {
      return await call('cli', {dir, args, stdin});
    } catch (e) {
      return {ok: false, result: null, notices: [], error: {code: 'gui', message: e.message}, argv: ['ecobuild', ...args]};
    } finally { row?.remove(); }
  }

  function detailText(details) {
    if (details == null || details === '') return '';
    if (typeof details === 'string') return details;
    if (Array.isArray(details)) return details.map(d => typeof d === 'string' ? d : JSON.stringify(d)).join('\n');
    if (details.output) return details.output;
    return JSON.stringify(details, null, 2);
  }

  function showError(doc, title = 'うまくいきませんでした') {
    const e = doc.error || {message: '不明なエラーです。'};
    const detail = detailText(e.details) || (doc.ok === false && !e.details && doc.stderr && e.code === 'gui_no_output' ? doc.stderr : '');
    return dialog({title, wide: !!detail, body: `<p>${esc(e.message)}</p>${e.hint ? `<p class="eco-hint">${esc(e.hint)}</p>` : ''}${detail ? `<pre>${esc(detail)}</pre>` : ''}${doc.argv ? `<p class="eco-cmd">${esc(doc.argv.join(' '))}</p>` : ''}`, buttons: [['閉じる', 'primary', true]]});
  }

  // Runs a command; on "confirmation_required" asks with the CLI's own message and runs again with --yes.
  // Shows errors in a dialog and notices as notifications. Returns the document when it succeeded, otherwise null.
  async function run(dir, args, {success, stdin, confirm: confirmText, title} = {}) {
    if (confirmText && !await confirm({title: title || '確認', message: confirmText, ok: '実行する'})) return null;
    let doc = await cli(dir, args, {stdin});
    if (!doc.ok && doc.error?.code === 'confirmation_required') {
      const ok = await confirm({title: title || '確認', message: doc.error.message.replace(/^確認が必要です：/, ''), detail: detailText(doc.error.details), ok: '実行する', danger: true});
      if (!ok) return null;
      doc = await cli(dir, [...args, '--yes'], {stdin});
    }
    if (!doc.ok) { await showError(doc); return null; }
    if (success) toast(typeof success === 'function' ? success(doc.result) : success);
    for (const notice of doc.notices || []) toast('お知らせ：' + notice, 'info', 9000);
    return doc;
  }

  // Generic modal. buttons: [label, class, value]. Resolves with the value of the pressed button (or null).
  function dialog({title, body = '', buttons = [['閉じる', 'primary', true]], wide = false, onOpen}) {
    return new Promise(resolve => {
      const d = document.createElement('dialog'); d.className = 'eco-dialog' + (wide ? ' wide' : '');
      d.innerHTML = `<h2>${esc(title)}</h2><div class="eco-body">${body}</div><div class="eco-actions"></div>`;
      const actions = d.querySelector('.eco-actions');
      let result = null;
      for (const [text, cls, value] of buttons) {
        const b = document.createElement('button'); b.type = 'button'; b.textContent = text; if (cls) b.className = cls;
        b.addEventListener('click', () => { result = value; d.close(); }); actions.append(b);
      }
      d.addEventListener('close', () => { d.remove(); resolve(result); });
      document.body.append(d); d.showModal(); onOpen?.(d);
      actions.querySelector('.primary, .danger')?.focus();
    });
  }

  const confirm = ({title, message, detail, ok = 'OK', danger = false}) => dialog({title, body: `<p>${esc(message)}</p>${detail ? `<pre>${esc(detail)}</pre>` : ''}`, wide: !!detail, buttons: [['キャンセル', '', false], [ok, danger ? 'danger' : 'primary', true]]}).then(Boolean);

  function colorDiff(text) {
    return String(text).split('\n').map(line => {
      const cls = /^(\+\+\+|---|diff |index |new file|deleted file|similarity|rename )/.test(line) ? 'meta' : line.startsWith('@@') ? 'hunk' : line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : '';
      return cls ? `<span class="${cls}">${esc(line)}</span>` : esc(line);
    }).join('\n');
  }
  const output = (title, text, {diff = false, sub = ''} = {}) => dialog({title, wide: true, body: `${sub ? `<p class="eco-intro">${esc(sub)}</p>` : ''}<pre class="${diff ? 'eco-diff' : ''}">${diff ? colorDiff(text || '') : esc(text || '')}</pre>`});

  // Form dialog. fields: {name, label, type, value, options: [[value, label, note]], placeholder, required, help, min}.
  // submit(values) may return an error string to keep the dialog open. Resolves with the values (or null when cancelled).
  function form({title, intro = '', fields = [], ok = 'OK', danger = false, wide = false, submit, extra = ''}) {
    return new Promise(resolve => {
      const d = document.createElement('dialog'); d.className = 'eco-dialog' + (wide ? ' wide' : '');
      const html = fields.map(f => {
        const id = 'f-' + f.name, attrs = `name="${esc(f.name)}" ${f.required ? 'required' : ''} ${f.placeholder ? `placeholder="${esc(f.placeholder)}"` : ''} ${f.min != null ? `min="${f.min}"` : ''}`;
        const help = f.help ? `<span class="eco-help">${esc(f.help)}</span>` : '';
        if (f.type === 'html') return f.html;
        if (f.type === 'checkbox') return `<label class="eco-check"><input type="checkbox" ${attrs} ${f.value ? 'checked' : ''}> ${esc(f.label)}</label>${help}`;
        if (f.type === 'radio') return `<fieldset><legend>${esc(f.label)}</legend>${f.options.map(([v, l, note]) => `<label><input type="radio" name="${esc(f.name)}" value="${esc(v)}" ${String(v) === String(f.value) ? 'checked' : ''}><span><strong>${esc(l)}</strong>${note ? `<small>${esc(note)}</small>` : ''}</span></label>`).join('')}</fieldset>${help}`;
        if (f.type === 'select') return `<label class="eco-field">${esc(f.label)}<select ${attrs}>${f.options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(f.value ?? '') ? 'selected' : ''}>${esc(l ?? v)}</option>`).join('')}</select>${help}</label>`;
        if (f.type === 'textarea') return `<label class="eco-field">${esc(f.label)}<textarea ${attrs} rows="${f.rows || 4}">${esc(f.value ?? '')}</textarea>${help}</label>`;
        return `<label class="eco-field">${esc(f.label)}<input id="${id}" type="${f.type || 'text'}" ${attrs} value="${esc(f.value ?? '')}" autocomplete="off">${help}</label>`;
      }).join('');
      d.innerHTML = `<form><h2>${esc(title)}</h2>${intro ? `<p class="eco-intro">${intro}</p>` : ''}${html}${extra}<p class="eco-error" role="alert"></p><div class="eco-actions"><button type="button" data-cancel>キャンセル</button><button type="submit" class="${danger ? 'danger' : 'primary'}">${esc(ok)}</button></div></form>`;
      const formEl = d.querySelector('form'), error = d.querySelector('.eco-error'), okButton = d.querySelector('[type=submit]');
      let result = null;
      d.querySelector('[data-cancel]').addEventListener('click', () => d.close());
      formEl.addEventListener('submit', async event => {
        event.preventDefault();
        const values = {};
        for (const f of fields) {
          if (f.type === 'html') continue;
          if (f.type === 'checkbox') values[f.name] = formEl.elements[f.name].checked;
          else if (f.type === 'radio') values[f.name] = formEl.querySelector(`[name="${f.name}"]:checked`)?.value ?? '';
          else values[f.name] = formEl.elements[f.name].value.trim();
        }
        error.textContent = '';
        if (submit) {
          okButton.disabled = true;
          try {
            const message = await submit(values, d);
            if (message) { error.textContent = message; return; }
          } finally { okButton.disabled = false; }
        }
        result = values; d.close();
      });
      d.addEventListener('close', () => { d.remove(); resolve(result); });
      document.body.append(d); d.showModal();
      formEl.querySelector('input:not([type=checkbox]):not([type=radio]), textarea, select')?.focus();
      d.formEl = formEl;
    });
  }

  // Splits text into command arguments for comma lists.
  const commaList = text => String(text || '').split(',').map(s => s.trim()).filter(Boolean);

  let infoPromise;
  const info = () => (infoPromise ||= call('info').catch(() => ({me: ''})));

  const loading = text => `<div class="eco-loading"><span class="eco-spinner"></span>${esc(text || '読み込んでいます…')}</div>`;

  return {call, cli, run, showError, dialog, confirm, form, output, toast, esc, commaList, info, loading, detailText, colorDiff, params};
})();
