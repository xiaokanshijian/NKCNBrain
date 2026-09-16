/**
 * NKCN 卡片 HTML 助记题遥测（由 card_html_view 注入，适配 W11 历史生成页）。
 * 覆盖：button.opt、div.opt、.opts/.options > li、多选「提交」判分。
 */
(function () {
  'use strict';
  var CFG = window.__NKCN_CARD_HTML__;
  if (!CFG) {
    try {
      var cfgEl = document.getElementById('nkcn-card-html-cfg');
      if (cfgEl && cfgEl.textContent) {
        CFG = JSON.parse(cfgEl.textContent);
        window.__NKCN_CARD_HTML__ = CFG;
      }
    } catch (e) {}
  }
  if (!CFG) {
    console.warn('[NKCN] 未找到 __NKCN_CARD_HTML__，请通过 /api/card_html_view 打开（非直接打开 .html 文件）');
    return;
  }

  function apiUrl(path) {
    var p = path || '/api/card_html_feedback_submit';
    if (/^https?:\/\//i.test(p)) return p;
    try {
      return new URL(p, window.location.href).href;
    } catch (e) {
      return window.location.origin + (p.charAt(0) === '/' ? p : '/' + p);
    }
  }

  var submitUrl = apiUrl(CFG.submitUrl);
  var storageKey = CFG.storageKey || ('nkcn_card_html_' + CFG.username + '_' + CFG.cid);
  var sessionId = 's_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10);
  var roster = CFG.roster || [];
  var memberReady = false;

  function postEvent(payload) {
    payload.username = CFG.username;
    payload.cid = CFG.cid;
    payload.session_id = sessionId;
    payload.client_ts = Date.now() / 1000;
    var body = JSON.stringify(payload);
    fetch(submitUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
      keepalive: true,
      credentials: 'same-origin',
    }).then(function (res) {
      if (!res.ok) {
        console.warn('[NKCN] 上报失败 HTTP', res.status, submitUrl);
      }
    }).catch(function (err) {
      console.warn('[NKCN] 上报网络错误', err, submitUrl);
    });
  }

  function getMember() {
    try {
      var raw = localStorage.getItem(storageKey);
      if (!raw) return null;
      var m = JSON.parse(raw);
      if (CFG.contentWeek != null && m && m.week != null && m.week !== CFG.contentWeek) {
        return null;
      }
      return m;
    } catch (e) {}
    return null;
  }

  function setMember(name, role) {
    var m = { name: name, role: role || '' };
    if (CFG.contentWeek != null) {
      m.week = CFG.contentWeek;
    }
    try {
      localStorage.setItem(storageKey, JSON.stringify(m));
    } catch (e) {}
    return m;
  }

  function memberPayload() {
    var m = getMember() || {};
    return { member_name: m.name || '', member_role: m.role || '' };
  }

  function clearStoredMember() {
    try {
      localStorage.removeItem(storageKey);
    } catch (e) {}
  }

  function ensureMemberPicker(done) {
    var qMember = null;
    var forcePick = !!CFG.forcePick;
    try {
      var sp = new URLSearchParams(window.location.search);
      qMember = sp.get('member');
      if (sp.get('pick') === '1' || sp.get('identity') === '1') {
        forcePick = true;
      }
    } catch (e) {}
    if (forcePick) {
      clearStoredMember();
    }
    if (qMember) {
      var hit = null;
      for (var i = 0; i < roster.length; i++) {
        if (roster[i].name === qMember) {
          hit = roster[i];
          break;
        }
      }
      setMember(qMember, hit ? hit.role : '');
      finishMemberPick();
      done();
      return;
    }
    var cur = getMember();
    if (!forcePick && cur && cur.name) {
      finishMemberPick();
      done();
      return;
    }

    if (!document.body) {
      document.addEventListener('DOMContentLoaded', function () {
        ensureMemberPicker(done);
      }, { once: true });
      return;
    }
    if (document.getElementById('nkcn-member-overlay')) {
      return;
    }

    var overlay = document.createElement('div');
    overlay.id = 'nkcn-member-overlay';
    overlay.setAttribute('style',
      'position:fixed;inset:0;z-index:2147483646;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;font-family:system-ui,-apple-system,\"Segoe UI\",sans-serif;');
    var box = document.createElement('div');
    box.setAttribute('style',
      'background:#fff;border-radius:12px;padding:20px 22px;max-width:420px;width:92%;box-shadow:0 12px 40px rgba(0,0,0,.2);');
    var title = document.createElement('div');
    title.textContent = '请选择你的身份（本组助记报告）';
    title.setAttribute('style', 'font-weight:600;font-size:16px;margin-bottom:12px;color:#222;');
    box.appendChild(title);
    if (CFG.cardTitle) {
      var sub = document.createElement('div');
      sub.textContent = CFG.cardTitle;
      sub.setAttribute('style', 'font-size:12px;color:#666;margin-bottom:12px;line-height:1.4;');
      box.appendChild(sub);
    }
    var list = document.createElement('div');
    list.setAttribute('style', 'display:flex;flex-direction:column;gap:8px;max-height:50vh;overflow:auto;');
    function pick(name, role) {
      setMember(name, role);
      if (overlay.parentNode) {
        document.body.removeChild(overlay);
      }
      finishMemberPick();
      done();
    }
    if (roster.length) {
      roster.forEach(function (r) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = (r.role ? r.role + ' · ' : '') + r.name;
        btn.setAttribute('style',
          'text-align:left;padding:10px 12px;border:1px solid #d0d7de;border-radius:8px;background:#f6f8fa;cursor:pointer;font-size:14px;');
        btn.onclick = function () { pick(r.name, r.role); };
        list.appendChild(btn);
      });
    } else {
      var inp = document.createElement('input');
      inp.placeholder = '输入姓名';
      inp.setAttribute('style', 'width:100%;padding:10px;border:1px solid #ccc;border-radius:8px;box-sizing:border-box;');
      var ok = document.createElement('button');
      ok.type = 'button';
      ok.textContent = '确认';
      ok.setAttribute('style', 'margin-top:10px;padding:8px 14px;border:none;border-radius:8px;background:#2563eb;color:#fff;cursor:pointer;');
      ok.onclick = function () {
        var n = (inp.value || '').trim();
        if (!n) return;
        pick(n, '');
      };
      list.appendChild(inp);
      list.appendChild(ok);
    }
    var guest = document.createElement('button');
    guest.type = 'button';
    guest.textContent = '访客 / 暂不登记';
    guest.setAttribute('style', 'margin-top:10px;padding:8px 12px;border:none;background:transparent;color:#666;cursor:pointer;font-size:12px;');
    guest.onclick = function () { pick('访客', ''); };
    box.appendChild(list);
    box.appendChild(guest);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    document.documentElement.classList.add('nkcn-await-member');
  }

  function finishMemberPick() {
    memberReady = true;
    document.documentElement.classList.remove('nkcn-await-member');
  }

  function blockClicksUntilMember(e) {
    if (memberReady) return;
    if (e.target && e.target.closest && e.target.closest('#nkcn-member-overlay')) return;
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
  }

  function normText(el) {
    return (el && (el.innerText || el.textContent) || '').replace(/\s+/g, ' ').trim();
  }

  function letterFromOption(el) {
    var k = el.querySelector && el.querySelector('.k, .key, .letter, .lbl, .lt');
    if (k) {
      var t = normText(k).replace(/[\.、\):：\s]/g, '');
      if (/^[A-Da-d]$/.test(t)) return t.toUpperCase();
    }
    var t = normText(el);
    var m = t.match(/^([A-Da-d])[\.、\):：\s]/);
    return m ? m[1].toUpperCase() : t.slice(0, 40);
  }

  /** W11 批次常见：li.opts / li.options / div|button.opt */
  function isOptionElement(el) {
    if (!el || !(el instanceof HTMLElement)) return false;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
    var tag = el.tagName.toLowerCase();
    var cls = String(el.className || '');
    if (/\b(submit|reset|flip-back|flipbtn|back-btn|ghost|turn|again|judge)\b/i.test(cls)) return false;
    if (tag === 'button' || tag === 'a') {
      var t = normText(el);
      if (t.length < 1 || t.length > 200) return false;
      if (/^(提交|重选|重置|判|翻面|返回)/.test(t)) return false;
      if (/^[A-Da-d][\.、\):：\s]/.test(t)) return true;
      if (/\bopt\b/i.test(cls)) return true;
    }
    if (tag === 'li') {
      if (el.closest('.opts, .options, ul.opts, ul.options')) return true;
      if (/\bopt\b/i.test(cls)) return true;
    }
    if (tag === 'div' && /\bopt\b/i.test(cls)) return true;
    return false;
  }

  function collectOptions(root) {
    var found = [];
    var sel = '.opts > li, .options > li, li.opt, div.opt, button.opt, .opts li, .options li';
    root.querySelectorAll(sel).forEach(function (el) {
      if (isOptionElement(el)) found.push(el);
    });
    if (found.length < 3) {
      root.querySelectorAll('button, li, div').forEach(function (el) {
        if (isOptionElement(el)) found.push(el);
      });
    }
    var uniq = [];
    var seen = new Set();
    found.forEach(function (el) {
      if (seen.has(el)) return;
      seen.add(el);
      uniq.push(el);
    });
    return uniq.filter(function (el) {
      return !el.closest('.face.back, .back');
    });
  }

  /** 布局壳层（含 card 子串但不是题卡根节点） */
  var CARD_SHELL_RE = /\b(card-wrap|card-scene|cards-wrap|card-body|card-head|card-foot|card-grid|card-deck|ov-card|card-inner)\b/i;

  function isNestedQuestionCard(node) {
    var p = node.parentElement;
    while (p) {
      if (p.classList && p.classList.contains('card')) return true;
      p = p.parentElement;
    }
    return false;
  }

  function tryPushQuestionCard(cards, seen, node) {
    if (!(node instanceof HTMLElement) || seen.has(node)) return;
    if (isNestedQuestionCard(node)) return;
    var opts = collectOptions(node);
    if (opts.length >= 3 && opts.length <= 8) {
      seen.add(node);
      cards.push({ root: node, options: opts });
    }
  }

  function findQuestionCards() {
    var cards = [];
    var seen = new Set();
    document.querySelectorAll('.card').forEach(function (node) {
      tryPushQuestionCard(cards, seen, node);
    });
    if (cards.length) return cards;
    /* 旧版页无 .card 类时的兜底（排除 card-wrap 等壳层） */
    document.querySelectorAll('[class*="card"]').forEach(function (node) {
      if (!(node instanceof HTMLElement)) return;
      if (node.classList && node.classList.contains('card')) return;
      if (CARD_SHELL_RE.test(String(node.className || ''))) return;
      tryPushQuestionCard(cards, seen, node);
    });
    return cards;
  }

  function hasSubmitControl(root) {
    var btns = root.querySelectorAll(
      'button.submit, button.submit-btn, button.btn-submit, button.judge, .submit, .judge'
    );
    for (var i = 0; i < btns.length; i++) {
      var btn = btns[i];
      if (!/\b(submit|judge|btn-submit)\b/i.test(String(btn.className)) &&
          !/提交|判定|判分/.test(normText(btn))) continue;
      return true;
    }
    return false;
  }

  /** 多选：看 DOM 标记/文案，不用「有无提交钮」（G8 单选也有 submit-btn） */
  function isMultiQuestion(root) {
    if (!root) return false;
    var explicit = root.querySelector(
      '.tag-multi, .multi-tag, .multi-badge, .qtype-multi, .type-badge.multi, .q-type.multi, .qtype-badge.multi'
    );
    if (explicit) return true;
    var marked = root.querySelectorAll('[class*="multi"]');
    for (var i = 0; i < marked.length; i++) {
      var cls = String(marked[i].className || '');
      if (CARD_SHELL_RE.test(cls)) continue;
      if (/\b(role|tag-multi|multi-tag|multi-badge|qtype-multi|type-badge|q-type|qtype-badge|card-type)\b/i.test(cls)) {
        return true;
      }
    }
    var textEls = root.querySelectorAll(
      '.type-badge, .qtype-tag, .qtype-badge, .card-type, .q-type, .qtitle, .q, .qtitle span'
    );
    for (var j = 0; j < textEls.length; j++) {
      var t = normText(textEls[j]);
      if (/多选/.test(t) && !/^单选/.test(t)) return true;
    }
    return false;
  }

  function questionLabel(root) {
    var role = root.querySelector('.role, .who, .tag + .role');
    var q = root.querySelector('.q, .stem, .question, .qtitle');
    var parts = [];
    if (role) parts.push(normText(role).slice(0, 60));
    if (q) parts.push(normText(q).slice(0, 140));
    if (!parts.length) {
      var h = root.querySelector('h2,h3,h4');
      if (h) parts.push(normText(h).slice(0, 160));
    }
    return parts.join(' | ') || normText(root).slice(0, 180);
  }

  function feedbackElVisible(el) {
    if (!el) return false;
    if (el.classList && (el.classList.contains('show') || el.classList.contains('ok'))) return true;
    return el.style.display !== 'none' && el.style.display !== '';
  }

  var WRONG_TIP_RE = /^✗|^×|再试|不对|错误|差一点|未完全|漏选|方向接近|还差|未勾|误选|组合不对|不完全|请先选择/;
  var OK_TIP_RE = /^✓|答对|恭喜|正确|命中|完全命中|全部命中/;

  /** 页面已进入「判对完成」态（翻面/解禁翻面钮/✓提示等），用于 submit 路径 */
  function hasSuccessCompletion(root) {
    if (!root) return false;
    if (root.dataset && root.dataset.answered === '1') return true;
    if (root.classList && (root.classList.contains('flipped') || root.classList.contains('flip'))) {
      return true;
    }
    var innerFlip = root.querySelector('.card-inner.flipped, [id^="inner-"].flipped');
    if (innerFlip) return true;
    var flipBtn = root.querySelector(
      '.flip-btn, button.flip-btn, button.flipbtn, [class*="flip-btn"]'
    );
    if (flipBtn && !flipBtn.disabled) return true;
    if (root.classList && root.classList.contains('locked')) return true;
    var tip = root.querySelector('.tip, .feedback, .hint, [class*="tip"], [class*="hint"]');
    if (feedbackElVisible(tip)) {
      if (tip.classList && tip.classList.contains('ok')) return true;
      if (OK_TIP_RE.test(normText(tip))) return true;
    }
    return false;
  }

  /** W11 九组：点选路径看本次 opt；提交路径须 hasSuccessCompletion，避免多选半对误判 */
  function detectOutcome(root, clickedOpt) {
    if (!root) return 'pending';

    if (clickedOpt && clickedOpt.classList) {
      if (clickedOpt.classList.contains('wrong')) return 'wrong_hint';
      if (clickedOpt.classList.contains('right') || clickedOpt.classList.contains('correct')) {
        return 'correct_flip';
      }
    }

    var tip = root.querySelector('.tip, .feedback, .hint, [class*="tip"], [class*="hint"]');
    if (feedbackElVisible(tip)) {
      if (tip.classList && tip.classList.contains('err')) return 'wrong_hint';
      var tt = normText(tip);
      if (WRONG_TIP_RE.test(tt)) return 'wrong_hint';
      if (OK_TIP_RE.test(tt)) return 'correct_flip';
    }

    if (hasSuccessCompletion(root)) return 'correct_flip';

    if (root.querySelector('button.opt.wrong, .opt.wrong, li.wrong')) return 'wrong_hint';

    return 'pending';
  }

  function postSelectOutcome(mem, qid, root, opt, attempt) {
    var outcome = detectOutcome(root, opt);
    if (outcome === 'pending') return;
    postEvent(Object.assign({}, mem, {
      event: 'select',
      qid: qid,
      question_label: questionLabel(root),
      attempt: attempt,
      selected: [letterFromOption(opt)],
      selected_text: [normText(opt)],
      outcome: outcome,
    }));
  }

  function gatherSelected(root) {
    var labels = [];
    var texts = [];
    root.querySelectorAll(
      '.opts li.sel, .opts li.chosen, .options li.sel, li.opt.sel, li.opt.chosen, li.opt.picked, ' +
      'div.opt.chosen, div.opt.picked, div.opt.sel, button.opt.picked'
    ).forEach(function (el) {
      labels.push(letterFromOption(el));
      texts.push(normText(el).slice(0, 120));
    });
    if (!labels.length) {
      root.querySelectorAll('.opts li, .options li, div.opt, button.opt, li.opt').forEach(function (el) {
        if (el.classList.contains('chosen') || el.classList.contains('sel') ||
            el.classList.contains('picked') || el.classList.contains('right') ||
            el.classList.contains('correct')) {
          labels.push(letterFromOption(el));
          texts.push(normText(el).slice(0, 120));
        }
      });
    }
    return { selected: labels, selected_text: texts };
  }

  function wireQuestions() {
    var cards = findQuestionCards();
    var attemptMap = {};

    cards.forEach(function (item, idx) {
      var qid = 'q' + idx;
      var root = item.root;
      var isMulti = isMultiQuestion(root);
      var submitGated = !isMulti && hasSubmitControl(root);
      var deferOutcome = isMulti || submitGated;
      attemptMap[qid] = 0;

      item.options.forEach(function (opt) {
        if (opt.__nkcnWired) return;
        opt.__nkcnWired = true;
        opt.addEventListener('click', function (e) {
          if (!memberReady) {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            ensureMemberPicker(function () {});
            return;
          }
          var mem = memberPayload();
          var sel = gatherSelected(root);
          if (!sel.selected.length) {
            sel = { selected: [letterFromOption(opt)], selected_text: [normText(opt)] };
          }
          var payload = Object.assign({}, mem, {
            event: deferOutcome ? 'select_partial' : 'select',
            qid: qid,
            question_label: questionLabel(root),
            attempt: deferOutcome ? attemptMap[qid] : (attemptMap[qid] = (attemptMap[qid] || 0) + 1),
            selected: sel.selected,
            selected_text: sel.selected_text,
            outcome: 'pending',
          });
          postEvent(payload);
          if (!deferOutcome) {
            var attemptNo = attemptMap[qid];
            setTimeout(function () {
              postSelectOutcome(mem, qid, root, opt, attemptNo);
            }, 520);
          }
        }, true);
      });

      root.querySelectorAll(
        'button.submit, button.submit-btn, button.btn-submit, button.judge, .submit, .judge'
      ).forEach(function (btn) {
        if (btn.__nkcnSubmitWired) return;
        if (!/\b(submit|judge|btn-submit)\b/i.test(String(btn.className)) &&
            !/提交|判定|判分/.test(normText(btn))) return;
        btn.__nkcnSubmitWired = true;
        btn.addEventListener('click', function () {
          var mem = memberPayload();
          attemptMap[qid] = (attemptMap[qid] || 0) + 1;
          var sel = gatherSelected(root);
          postEvent(Object.assign({}, mem, {
            event: 'submit',
            qid: qid,
            question_label: questionLabel(root),
            attempt: attemptMap[qid],
            selected: sel.selected,
            selected_text: sel.selected_text,
            outcome: 'pending',
          }));
          setTimeout(function () {
            var outcome = detectOutcome(root, null);
            if (outcome === 'pending') outcome = 'wrong_hint';
            postEvent(Object.assign({}, mem, {
              event: 'submit',
              qid: qid,
              question_label: questionLabel(root),
              attempt: attemptMap[qid],
              selected: sel.selected,
              selected_text: sel.selected_text,
              outcome: outcome,
            }));
          }, 720);
        }, true);
      });
    });

    if (cards.length && !document.body.dataset.nkcnTelemetryMounted) {
      document.body.dataset.nkcnTelemetryMounted = '1';
      var gidPrefix = CFG.groupId ? (CFG.groupId + '组') : '';
      console.info(gidPrefix + '[NKCN] 助记题遥测已挂载，题卡数=', cards.length);
    } else if (!cards.length && !document.body.dataset.nkcnTelemetryMounted) {
      console.warn('[NKCN] 未识别到助记题卡，请检查 HTML 结构');
    }
  }

  function onReady() {
    document.addEventListener('click', blockClicksUntilMember, true);
    document.addEventListener('mousedown', blockClicksUntilMember, true);
    ensureMemberPicker(function () {
      finishMemberPick();
      postEvent(Object.assign({ event: 'visit' }, memberPayload()));
      wireQuestions();
      setTimeout(wireQuestions, 800);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
})();
