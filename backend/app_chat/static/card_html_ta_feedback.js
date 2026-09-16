/**
 * NKCN 小组作答可视化页底部 TA/教师批注（card_feedback_html_view 注入）。
 */
(function () {
  'use strict';
  var CFG = window.__NKCN_TA_FEEDBACK__;
  if (!CFG) {
    console.warn('[NKCN] 未找到 __NKCN_TA_FEEDBACK__');
    return;
  }

  function apiUrl(path) {
    var p = path || CFG.getUrl || '/api/card_ta_feedback';
    if (/^https?:\/\//i.test(p)) return p;
    try {
      return new URL(p, window.location.href).href;
    } catch (e) {
      return window.location.origin + (p.charAt(0) === '/' ? p : '/' + p);
    }
  }

  var getUrl = apiUrl(CFG.getUrl);
  var saveUrl = apiUrl(CFG.saveUrl);
  var identities = CFG.identities || [];
  var studentHint = CFG.studentHint || '学生只查看，不编辑';

  function fmtTime(ts) {
    if (!ts) return '—';
    try {
      var d = new Date(ts * 1000);
      return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-'
        + String(d.getDate()).padStart(2, '0') + ' '
        + String(d.getHours()).padStart(2, '0') + ':'
        + String(d.getMinutes()).padStart(2, '0');
    } catch (e) {
      return '—';
    }
  }

  function mount() {
    if (!document.body || document.getElementById('nkcn-ta-feedback-section')) {
      return;
    }

    var section = document.createElement('section');
    section.id = 'nkcn-ta-feedback-section';
    section.setAttribute('style',
      'max-width:1200px;margin:28px auto 32px;padding:20px 24px 24px;'
      + 'background:#fff;border:1px solid #d8e0dc;border-radius:12px;'
      + 'box-shadow:0 2px 12px rgba(0,0,0,.06);font-family:"PingFang SC","Microsoft YaHei",sans-serif;');

    var head = document.createElement('div');
    head.setAttribute('style', 'display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;');
    var title = document.createElement('h2');
    title.textContent = 'TA / 教师批注';
    title.setAttribute('style', 'margin:0;font-size:1.1rem;color:#2d6a4f;');
    var editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.textContent = '编辑';
    editBtn.id = 'nkcn-ta-feedback-edit';
    editBtn.setAttribute('style',
      'padding:8px 16px;border:none;border-radius:8px;background:#2d6a4f;color:#fff;'
      + 'cursor:pointer;font-size:14px;');
    head.appendChild(title);
    head.appendChild(editBtn);

    var hint = document.createElement('p');
    hint.textContent = studentHint;
    hint.setAttribute('style', 'margin:0 0 10px;font-size:13px;color:#8b2635;');

    var meta = document.createElement('div');
    meta.id = 'nkcn-ta-feedback-meta';
    meta.setAttribute('style', 'font-size:12px;color:#5a6b66;margin-bottom:8px;');
    meta.textContent = '加载中…';

    var ta = document.createElement('textarea');
    ta.id = 'nkcn-ta-feedback-body';
    ta.readOnly = true;
    ta.setAttribute('style',
      'width:100%;min-height:120px;padding:12px;border:1px solid #d8e0dc;border-radius:8px;'
      + 'font-size:14px;line-height:1.6;resize:vertical;box-sizing:border-box;background:#f8faf8;');
    ta.placeholder = '（暂无批注）';

    section.appendChild(head);
    section.appendChild(hint);
    section.appendChild(meta);
    section.appendChild(ta);
    document.body.appendChild(section);

    function setMeta(row) {
      if (!row || !row.author) {
        meta.textContent = '尚未填写批注';
        return;
      }
      meta.textContent = '最后更新：' + fmtTime(row.updated_at) + ' · 署名：' + row.author;
    }

    function setBody(text) {
      ta.value = text || '';
    }

    function load() {
      var url = getUrl + (getUrl.indexOf('?') >= 0 ? '&' : '?')
        + 'username=' + encodeURIComponent(CFG.username)
        + '&cid=' + encodeURIComponent(String(CFG.cid));
      fetch(url, { credentials: 'same-origin' })
        .then(function (res) { return res.json(); })
        .then(function (payload) {
          if (payload.error_num !== 0) {
            meta.textContent = '加载失败：' + (payload.msg || '');
            return;
          }
          var row = payload.data || {};
          setMeta(row);
          setBody(row.content || '');
        })
        .catch(function (err) {
          meta.textContent = '加载失败：' + err;
        });
    }

    function openEditor() {
      if (document.getElementById('nkcn-ta-feedback-overlay')) return;

      var overlay = document.createElement('div');
      overlay.id = 'nkcn-ta-feedback-overlay';
      overlay.setAttribute('style',
        'position:fixed;inset:0;z-index:2147483647;background:rgba(0,0,0,.45);'
        + 'display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;');

      var box = document.createElement('div');
      box.setAttribute('style',
        'background:#fff;border-radius:12px;padding:22px;max-width:560px;width:100%;'
        + 'max-height:90vh;overflow:auto;box-shadow:0 12px 40px rgba(0,0,0,.25);');

      var h = document.createElement('div');
      h.textContent = '编辑批注';
      h.setAttribute('style', 'font-weight:600;font-size:16px;margin-bottom:8px;color:#222;');

      var warn = document.createElement('p');
      warn.textContent = studentHint;
      warn.setAttribute('style', 'margin:0 0 14px;font-size:13px;color:#8b2635;line-height:1.5;');

      var lab = document.createElement('div');
      lab.textContent = '请选择您的身份';
      lab.setAttribute('style', 'font-size:13px;font-weight:600;margin-bottom:8px;color:#333;');

      var idList = document.createElement('div');
      idList.setAttribute('style', 'display:flex;flex-direction:column;gap:6px;margin-bottom:14px;');
      var selected = '';
      identities.forEach(function (id) {
        var lbl = document.createElement('label');
        lbl.setAttribute('style',
          'display:flex;align-items:center;gap:8px;padding:8px 10px;border:1px solid #d0d7de;'
          + 'border-radius:8px;cursor:pointer;font-size:14px;');
        var radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'nkcn-ta-identity';
        radio.value = id;
        radio.onchange = function () {
          selected = id;
          modalTa.readOnly = false;
          modalTa.setAttribute('style', modalTa.getAttribute('style').replace('background:#f1f3f5', 'background:#fff'));
        };
        lbl.appendChild(radio);
        lbl.appendChild(document.createTextNode(id));
        idList.appendChild(lbl);
      });

      var modalTa = document.createElement('textarea');
      modalTa.value = ta.value;
      modalTa.readOnly = true;
      modalTa.setAttribute('style',
        'width:100%;min-height:140px;padding:10px;border:1px solid #ccc;border-radius:8px;'
        + 'font-size:14px;line-height:1.6;resize:vertical;box-sizing:border-box;background:#f1f3f5;');
      modalTa.placeholder = '请先选择身份后再填写…';

      var actions = document.createElement('div');
      actions.setAttribute('style', 'display:flex;justify-content:flex-end;gap:10px;margin-top:14px;');
      var cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.textContent = '取消';
      cancel.setAttribute('style', 'padding:8px 14px;border:1px solid #ccc;border-radius:8px;background:#fff;cursor:pointer;');
      var ok = document.createElement('button');
      ok.type = 'button';
      ok.textContent = '确认保存';
      ok.setAttribute('style', 'padding:8px 14px;border:none;border-radius:8px;background:#2d6a4f;color:#fff;cursor:pointer;');

      function close() {
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      }

      cancel.onclick = close;
      overlay.onclick = function (e) {
        if (e.target === overlay) close();
      };

      ok.onclick = function () {
        if (!selected) {
          alert('请先选择身份（教师 / 课程TA / 各联TA）');
          return;
        }
        ok.disabled = true;
        ok.textContent = '保存中…';
        fetch(saveUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({
            username: CFG.username,
            cid: CFG.cid,
            author: selected,
            content: modalTa.value,
          }),
        })
          .then(function (res) { return res.json(); })
          .then(function (payload) {
            ok.disabled = false;
            ok.textContent = '确认保存';
            if (payload.error_num !== 0) {
              alert('保存失败：' + (payload.msg || ''));
              return;
            }
            var row = payload.data || {};
            setMeta(row);
            setBody(row.content || '');
            close();
          })
          .catch(function (err) {
            ok.disabled = false;
            ok.textContent = '确认保存';
            alert('保存失败：' + err);
          });
      };

      actions.appendChild(cancel);
      actions.appendChild(ok);
      box.appendChild(h);
      box.appendChild(warn);
      box.appendChild(lab);
      box.appendChild(idList);
      box.appendChild(modalTa);
      box.appendChild(actions);
      overlay.appendChild(box);
      document.body.appendChild(overlay);
    }

    editBtn.onclick = openEditor;
    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
