/*
 * ویرایش و حذف برای همه‌ی جدول‌ها (فقط نسخه اندروید). با لمس هر ردیف یک منو باز می‌شود:
 *   ✏️ ویرایش   🗑 حذف   📋 پرداخت‌ها/اقساط (برای بدهی، وام و فروش قسطی)
 * رکورد هر ردیف از «key» ردیف در React خوانده می‌شود (کلید همه‌ی ردیف‌ها شناسه‌ی رکورد است)،
 * پس به کد minify‌شده‌ی اپ دست نمی‌زنیم. بعد از هر تغییر، صفحه‌ی فعلی دوباره بارگذاری می‌شود.
 */
(function () {
  'use strict';

  // ------------------------------------------------------------------ ابزارها
  function h(tag, attrs, kids) {
    var el = document.createElement(tag);
    for (var k in (attrs || {})) {
      if (k === 'class') el.className = attrs[k];
      else if (k === 'text') el.textContent = attrs[k];
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), attrs[k]);
      else el.setAttribute(k, attrs[k]);
    }
    [].concat(kids || []).forEach(function (c) {
      if (c == null) return;
      el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return el;
  }

  function errText(body, status) {
    var e = body && body.error;
    if (typeof e === 'string') return e;
    if (Array.isArray(e)) return e.map(function (x) { return (x.loc ? x.loc.slice(1).join('.') + ': ' : '') + x.msg; }).join('، ');
    return 'خطای ' + status;
  }

  function api(method, path, body) {
    var opts = { method: method };
    if (body !== undefined) { opts.headers = { 'Content-Type': 'application/json' }; opts.body = JSON.stringify(body); }
    return fetch('/api' + path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(errText(j, r.status));
        return j;
      });
    });
  }

  function fmt(n) { return (n == null || n === '') ? '-' : Number(n).toLocaleString('en-US'); }

  // تاریخ میلادی (ISO) → شمسی، فقط برای نمایش
  function toJalali(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
    if (!m) return iso || '-';
    var gy = +m[1], gm = +m[2], gd = +m[3];
    var gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    var gy2 = gm > 2 ? gy + 1 : gy;
    var days = 355666 + 365 * gy + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400) + gd + gdm[gm - 1];
    var jy = -1595 + 33 * Math.floor(days / 12053); days %= 12053;
    jy += 4 * Math.floor(days / 1461); days %= 1461;
    if (days > 365) { jy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
    var jm = days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
    var jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
    return jy + '/' + (jm < 10 ? '0' : '') + jm + '/' + (jd < 10 ? '0' : '') + jd;
  }

  var toastTimer;
  function toast(msg, bad) {
    var t = document.getElementById('fa-toast');
    if (!t) { t = h('div', { id: 'fa-toast' }); document.body.appendChild(t); }
    t.textContent = msg;
    t.className = 'show' + (bad ? ' bad' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.className = ''; }, bad ? 4500 : 2200);
  }

  // ---------------------------------------------------------------- پنجره‌ها
  var sheets = [];
  function openSheet(opts) {
    var errBox = h('div', { class: 'fa-err' });
    var body = h('div', { class: 'fa-sheet-b' }, [opts.body, errBox]);
    var foot = h('div', { class: 'fa-sheet-f' });
    var back = h('div', { class: 'fa-sheet-back' });
    var box = h('div', { class: 'fa-sheet', dir: 'rtl' }, [
      h('div', { class: 'fa-sheet-h' }, [
        h('div', { class: 'fa-sheet-t', text: opts.title || '' }),
        h('button', { type: 'button', class: 'fa-x', 'aria-label': 'بستن', text: '✕', onclick: function () { api_.close(); } })
      ]),
      body, foot
    ]);
    back.appendChild(box);
    back.addEventListener('click', function (e) { if (e.target === back) api_.close(); });
    var api_ = {
      el: box,
      error: function (msg) { errBox.textContent = msg || ''; },
      close: function () {
        var i = sheets.indexOf(api_); if (i >= 0) sheets.splice(i, 1);
        back.remove();
        if (opts.onClose) opts.onClose();
      },
      closeAll: function () { while (sheets.length) sheets[sheets.length - 1].close(); }
    };
    (opts.actions || []).forEach(function (a) {
      var b = h('button', { type: 'button', class: 'fa-btn ' + (a.kind || 'ghost'), text: a.label });
      b.addEventListener('click', function () { a.onClick(api_, b); });
      foot.appendChild(b);
    });
    document.body.appendChild(back);
    sheets.push(api_);
    return api_;
  }
  window.faCloseSheet = function () {
    if (!sheets.length) return false;
    sheets[sheets.length - 1].close();
    return true;
  };

  function confirmBox(message, okLabel) {
    return new Promise(function (resolve) {
      var done = false;
      function finish(v, s) { if (!done) { done = true; s.close(); resolve(v); } }
      openSheet({
        title: 'تأیید', body: h('div', { class: 'fa-msg', text: message }),
        onClose: function () { if (!done) { done = true; resolve(false); } },
        actions: [
          { label: okLabel || 'حذف', kind: 'danger', onClick: function (s) { finish(true, s); } },
          { label: 'انصراف', kind: 'ghost', onClick: function (s) { finish(false, s); } }
        ]
      });
    });
  }

  // -------------------------------------------------------------------- فرم
  function buildForm(fields, values) {
    var root = h('div', { class: 'fa-form' });
    var inputs = {};
    fields.forEach(function (f) {
      var el;
      if (f.type === 'select') {
        el = h('select');
        (f.opts || []).forEach(function (o) { el.appendChild(h('option', { value: String(o[0]), text: o[1] })); });
      } else if (f.type === 'textarea') {
        el = h('textarea', { rows: '2' });
      } else if (f.type === 'checkbox') {
        el = h('input', { type: 'checkbox' });
      } else {
        el = h('input', { type: f.type || 'text' });
        if (f.type === 'number') el.setAttribute('inputmode', 'numeric');
      }
      var v = values[f.k];
      if (f.type === 'checkbox') el.checked = !!v;
      else el.value = v == null ? '' : String(v);
      inputs[f.k] = el;
      var wrap = h('label', { class: 'fa-field' + (f.type === 'checkbox' ? ' chk' : '') },
        f.type === 'checkbox' ? [el, h('span', { text: f.label })]
                              : [h('span', { class: 'fa-lbl', text: f.label + (f.req ? ' *' : '') }), el]);
      root.appendChild(wrap);
      if (f.hint) root.appendChild(h('div', { class: 'fa-hint', text: f.hint }));
    });
    return {
      el: root,
      read: function () {
        var out = {};
        fields.forEach(function (f) {
          var el = inputs[f.k];
          if (f.type === 'checkbox') out[f.k] = el.checked;
          else if (f.type === 'number') out[f.k] = el.value === '' ? null : Number(el.value);
          else out[f.k] = el.value.trim();
        });
        return out;
      },
      missing: function () {
        var vals = this.read();
        for (var i = 0; i < fields.length; i++) {
          var f = fields[i];
          if (f.req && (vals[f.k] === '' || vals[f.k] == null || (f.type === 'number' && isNaN(vals[f.k])))) return f.label;
        }
        return null;
      }
    };
  }

  function nn(s) { return s === '' ? null : s; }   // رشته خالی → NULL
  function opts(list, valKey, labelFn) { return list.map(function (x) { return [x[valKey], labelFn(x)]; }); }

  // ------------------------------------------------------- تعریف هر نوع رکورد
  function pay(paths) { return paths; }

  var ENT = {
    accounts: {
      noun: 'حساب',
      load: function (id) { return api('GET', '/accounts/' + id); },
      fields: function (e) {
        return [
          { k: 'name', label: 'نام حساب', req: true },
          { k: 'type', label: 'نوع', type: 'select', opts: [['bank', 'بانکی'], ['cash', 'نقدی'], ['wallet', 'کیف پول'], ['other', 'سایر']] },
          { k: 'bankName', label: 'بانک' }, { k: 'accountNumber', label: 'شماره حساب' },
          { k: 'cardNumber', label: 'شماره کارت' }, { k: 'iban', label: 'شبا' },
          { k: 'initialBalance', label: 'موجودی اولیه', type: 'number' },
          { k: 'currency', label: 'واحد پول', type: 'select', opts: [['IRR', 'ریال'], ['IRT', 'تومان']] },
          { k: 'notes', label: 'یادداشت' }, { k: 'active', label: 'فعال', type: 'checkbox' }
        ];
      },
      values: function (e) {
        return { name: e.name, type: e.type, bankName: e.bank_name, accountNumber: e.account_number, cardNumber: e.card_number,
                 iban: e.iban, initialBalance: e.initial_balance, currency: e.currency, notes: e.notes, active: !!e.active };
      },
      body: function (v) {
        return { name: v.name, type: v.type, bankName: nn(v.bankName), accountNumber: nn(v.accountNumber), cardNumber: nn(v.cardNumber),
                 iban: nn(v.iban), initialBalance: v.initialBalance || 0, currency: v.currency, notes: nn(v.notes), active: v.active };
      },
      save: function (id, b) { return api('PUT', '/accounts/' + id, b); },
      remove: function (id) { return api('DELETE', '/accounts/' + id); },
      removeMsg: 'این حساب حذف شود؟ (حسابی که تراکنش دارد قابل حذف نیست؛ به‌جایش «فعال» را بردارید.)'
    },

    transfers: {
      noun: 'انتقال',
      load: function (id) {
        return Promise.all([api('GET', '/transfers/' + id), api('GET', '/accounts')]).then(function (r) { r[0]._accounts = r[1]; return r[0]; });
      },
      fields: function (e) {
        var accs = opts(e._accounts, 'id', function (a) { return a.name; });
        return [
          { k: 'fromAccountId', label: 'از حساب', type: 'select', opts: accs, req: true },
          { k: 'toAccountId', label: 'به حساب', type: 'select', opts: accs, req: true },
          { k: 'amount', label: 'مبلغ', type: 'number', req: true },
          { k: 'date', label: 'تاریخ', type: 'date', req: true },
          { k: 'description', label: 'شرح' }
        ];
      },
      values: function (e) { return { fromAccountId: e.fromAccountId, toAccountId: e.toAccountId, amount: Math.abs(e.amount), date: (e.date || '').slice(0, 10), description: e.description }; },
      body: function (v) { return { fromAccountId: Number(v.fromAccountId), toAccountId: Number(v.toAccountId), amount: v.amount, date: v.date, description: v.description || undefined }; },
      save: function (id, b) { return api('PUT', '/transfers/' + encodeURIComponent(id), b); },
      remove: function (id) { return api('DELETE', '/transfers/' + encodeURIComponent(id)); },
      removeMsg: 'این انتقال (هر دو طرفش) حذف شود؟'
    },

    people: {
      noun: 'شخص',
      load: function (id) { return api('GET', '/people/' + id); },
      fields: function () {
        return [{ k: 'name', label: 'نام', req: true }, { k: 'phone', label: 'تلفن' }, { k: 'description', label: 'توضیح' },
                { k: 'accountNumber', label: 'شماره حساب' }, { k: 'notes', label: 'یادداشت', type: 'textarea' }];
      },
      values: function (e) { return { name: e.name, phone: e.phone, description: e.description, accountNumber: e.account_number, notes: e.notes }; },
      body: function (v) { return { name: v.name, phone: nn(v.phone), description: nn(v.description), accountNumber: nn(v.accountNumber), notes: nn(v.notes) }; },
      save: function (id, b) { return api('PUT', '/people/' + id, b); },
      remove: function (id) { return api('DELETE', '/people/' + id); },
      removeMsg: 'این شخص حذف شود؟ (شخصی که بدهی/طلب ثبت‌شده دارد قابل حذف نیست.)'
    },

    debts: {
      noun: 'بدهی/طلب',
      load: function (id) { return Promise.all([api('GET', '/debts/' + id), api('GET', '/people')]).then(function (r) { r[0]._people = r[1]; return r[0]; }); },
      fields: function (e) {
        return [
          { k: 'kind', label: 'نوع', type: 'select', opts: [['receivable', 'طلب (از دیگران)'], ['payable', 'بدهی (به دیگران)']] },
          { k: 'personId', label: 'شخص', type: 'select', opts: opts(e._people, 'id', function (p) { return p.name; }), req: true },
          { k: 'originalAmount', label: 'مبلغ اصلی (ریال)', type: 'number', req: true },
          { k: 'createdDate', label: 'تاریخ ثبت', type: 'date', req: true },
          { k: 'dueDate', label: 'سررسید (اختیاری)', type: 'date' },
          { k: 'description', label: 'توضیحات' }
        ];
      },
      values: function (e) { return { kind: e.kind, personId: e.person_id, originalAmount: e.original_amount, createdDate: e.created_date, dueDate: e.due_date, description: e.description }; },
      body: function (v) { return { kind: v.kind, personId: Number(v.personId), originalAmount: v.originalAmount, createdDate: v.createdDate, dueDate: v.dueDate || '', description: v.description }; },
      save: function (id, b) { return api('PUT', '/debts/' + id, b); },
      remove: function (id) { return api('DELETE', '/debts/' + id); },
      removeMsg: 'این مورد همراه با همه‌ی پرداخت‌هایش حذف شود؟',
      details: { label: '📋 پرداخت‌ها', open: function (id, done) { openPayments('/debts/' + id, '/debts/' + id + '/payments/', done); } }
    },

    loans: {
      noun: 'وام',
      load: function (id) { return api('GET', '/loans/' + id); },
      fields: function () {
        return [
          { k: 'name', label: 'نام وام', req: true }, { k: 'lender', label: 'طلبکار / بانک', req: true },
          { k: 'principal', label: 'اصل مبلغ (ریال)', type: 'number', req: true },
          { k: 'termMonths', label: 'تعداد اقساط', type: 'number', req: true },
          { k: 'installmentAmount', label: 'مبلغ هر قسط (ریال)', type: 'number', req: true },
          { k: 'startDate', label: 'تاریخ شروع', type: 'date', req: true,
            hint: 'تغییر تعداد، مبلغ قسط یا تاریخ شروع، جدول اقساط را از نو می‌سازد؛ این کار فقط وقتی ممکن است که هیچ قسطی پرداخت‌شده ثبت نشده باشد (از «اقساط» پرداخت‌ها را صفر کنید).' },
          { k: 'notes', label: 'یادداشت' }
        ];
      },
      values: function (e) { return { name: e.name, lender: e.lender, principal: e.principal, termMonths: e.term_months, installmentAmount: e.installment_amount, startDate: e.start_date, notes: e.notes }; },
      body: function (v) { return { name: v.name, lender: v.lender, principal: v.principal, termMonths: v.termMonths, installmentAmount: v.installmentAmount, startDate: v.startDate, notes: v.notes }; },
      save: function (id, b) { return api('PUT', '/loans/' + id, b); },
      remove: function (id) { return api('DELETE', '/loans/' + id); },
      removeMsg: 'این وام همراه با همه‌ی اقساطش حذف شود؟',
      details: { label: '📋 اقساط', open: function (id, done) { openInstallments(id, done); } }
    },

    sales: {
      noun: 'فروش قسطی',
      load: function (id) { return Promise.all([api('GET', '/installment-sales/' + id), api('GET', '/customers')]).then(function (r) { r[0]._customers = r[1]; return r[0]; }); },
      fields: function (e) {
        return [
          { k: 'customerId', label: 'مشتری', type: 'select', opts: opts(e._customers, 'id', function (c) { return c.name; }), req: true },
          { k: 'date', label: 'تاریخ', type: 'date', req: true },
          { k: 'itemAmount', label: 'مبلغ کالا', type: 'number', req: true },
          { k: 'discount', label: 'تخفیف', type: 'number' },
          { k: 'downPayment', label: 'پیش‌پرداخت', type: 'number' },
          { k: 'installmentCount', label: 'تعداد اقساط', type: 'number', req: true },
          { k: 'paymentTerms', label: 'شرایط پرداخت' }
        ];
      },
      values: function (e) { return { customerId: e.customer_id, date: e.date, itemAmount: e.item_amount, discount: e.discount, downPayment: e.down_payment, installmentCount: e.installment_count, paymentTerms: e.payment_terms }; },
      body: function (v) { return { customerId: Number(v.customerId), date: v.date, itemAmount: v.itemAmount, discount: v.discount || 0, downPayment: v.downPayment || 0, installmentCount: v.installmentCount, paymentTerms: v.paymentTerms }; },
      save: function (id, b) { return api('PUT', '/installment-sales/' + id, b); },
      remove: function (id) { return api('DELETE', '/installment-sales/' + id); },
      removeMsg: 'این فروش قسطی همراه با همه‌ی پرداخت‌هایش حذف شود؟',
      details: { label: '📋 پرداخت‌ها', open: function (id, done) { openPayments('/installment-sales/' + id, '/installment-sales/' + id + '/payments/', done); } }
    },

    categories: {
      noun: 'دسته‌بندی',
      load: function (id) { return api('GET', '/categories').then(function (l) { return l.filter(function (c) { return String(c.id) === String(id); })[0]; }); },
      fields: function () { return [{ k: 'name', label: 'نام دسته‌بندی', req: true }]; },
      values: function (e) { return { name: e.name }; },
      body: function (v, e) { return { name: v.name, parentId: e.parent_id, icon: e.icon, color: e.color }; },
      save: function (id, b) { return api('PUT', '/categories/' + id, b); },
      remove: function (id) { return api('DELETE', '/categories/' + id); },
      removeMsg: 'این دسته‌بندی حذف شود؟ (اگر در تراکنش‌ها استفاده شده باشد حذف نمی‌شود.)'
    },

    tags: {
      noun: 'برچسب',
      load: function (id) { return api('GET', '/tags').then(function (l) { return l.filter(function (t) { return String(t.id) === String(id); })[0]; }); },
      fields: function () { return [{ k: 'name', label: 'نام برچسب', req: true }]; },
      values: function (e) { return { name: e.name }; },
      body: function (v, e) { return { name: v.name, color: e.color }; },
      save: function (id, b) { return api('PUT', '/tags/' + id, b); },
      remove: function (id) { return api('DELETE', '/tags/' + id); },
      removeMsg: 'این برچسب حذف و از همه‌ی تراکنش‌ها برداشته شود؟'
    },

    budgets: {
      noun: 'بودجه',
      load: function (id) { return api('GET', '/budgets/item/' + id); },
      fields: function (e) { return [{ k: 'amount', label: 'بودجه‌ی «' + e.category_name + '» در ' + e.month + ' (ریال)', type: 'number', req: true }]; },
      values: function (e) { return { amount: e.amount }; },
      body: function (v) { return { amount: v.amount }; },
      save: function (id, b) { return api('PUT', '/budgets/' + id, b); },
      remove: function (id) { return api('DELETE', '/budgets/' + id); },
      removeMsg: 'این بودجه حذف شود؟'
    },

    rules: {
      noun: 'قانون',
      load: function (id) { return api('GET', '/rules').then(function (l) { return l.filter(function (r) { return String(r.id) === String(id); })[0]; }); },
      fields: function () {
        return [{ k: 'name', label: 'نام قانون', req: true }, { k: 'active', label: 'فعال', type: 'checkbox' },
                { k: 'autoApply', label: 'اعمال خودکار روی تراکنش‌های جدید', type: 'checkbox',
                  hint: 'شرط و عمل قانون از این‌جا قابل ویرایش نیست؛ برای تغییر آن‌ها قانون را حذف و دوباره بسازید.' }];
      },
      values: function (e) { return { name: e.name, active: !!e.active, autoApply: !!e.auto_apply }; },
      body: function (v) { return { name: v.name, active: v.active, autoApply: v.autoApply }; },
      save: function (id, b) { return api('PUT', '/rules/' + id, b); },
      remove: function (id) { return api('DELETE', '/rules/' + id); },
      removeMsg: 'این قانون حذف شود؟'
    }
  };

  // جدول‌ها با «امضای سربرگ» شناخته می‌شوند
  var SIG = {
    'نام|نوع|بانک|موجودی': 'accounts',
    'تاریخ|از حساب|مبلغ|شرح': 'transfers',
    'نام|تلفن|طلب از او|بدهی به او|خالص': 'people',
    'نوع|شخص|مبلغ اصلی|پرداخت‌شده|مانده|سررسید': 'debts',
    'نام|طلبکار|اصل مبلغ|پیشرفت اقساط|مبلغ قسط': 'loans',
    'مشتری|مبلغ نهایی|تعداد اقساط|مانده': 'sales',
    'نام': 'categories',
    'دسته‌بندی|بودجه|خرج‌شده|پیشرفت': 'budgets',
    'نام|شرط|دسته‌بندی|برچسب‌ها|اعمال خودکار': 'rules'
  };

  // -------------------------------------------------------------- ویرایش/حذف
  var onDone = function () { refreshPage(); };

  function editRecord(kind, id, done) {
    var cfg = ENT[kind];
    cfg.load(id).then(function (entity) {
      if (!entity) throw new Error('رکورد پیدا نشد');
      var form = buildForm(cfg.fields(entity), cfg.values(entity));
      openSheet({
        title: 'ویرایش ' + cfg.noun, body: form.el,
        actions: [
          { label: 'ذخیره', kind: 'primary', onClick: function (s, btn) {
              var miss = form.missing();
              if (miss) return s.error('«' + miss + '» را وارد کنید');
              btn.disabled = true; s.error('');
              cfg.save(id, cfg.body(form.read(), entity)).then(function () {
                sheets.slice().forEach(function (x) { x.close(); });
                toast('ذخیره شد'); done();
              }).catch(function (e) { btn.disabled = false; s.error(e.message); });
            } },
          { label: 'انصراف', kind: 'ghost', onClick: function (s) { s.close(); } }
        ]
      });
    }).catch(function (e) { toast(e.message, true); });
  }

  function deleteRecord(kind, id, done) {
    var cfg = ENT[kind];
    confirmBox(cfg.removeMsg).then(function (ok) {
      if (!ok) return;
      cfg.remove(id).then(function () {
        sheets.slice().forEach(function (x) { x.close(); });
        toast('حذف شد'); done();
      }).catch(function (e) { toast(e.message, true); });
    });
  }

  function rowMenu(kind, id, title) {
    var cfg = ENT[kind];
    var actions = [
      { label: '✏️ ویرایش', kind: 'primary', onClick: function () { editRecord(kind, id, onDone); } },
      { label: '🗑 حذف', kind: 'danger', onClick: function () { deleteRecord(kind, id, onDone); } }
    ];
    if (cfg.details) actions.unshift({ label: cfg.details.label, kind: 'ghost', onClick: function () { cfg.details.open(id, onDone); } });
    openSheet({ title: cfg.noun, body: h('div', { class: 'fa-msg', text: title }), actions: actions });
  }

  // ------------------------------------------------- پرداخت‌های بدهی/فروش قسطی
  function openPayments(itemPath, payBase, done) {
    api('GET', itemPath).then(function (item) {
      var list = h('div', { class: 'fa-list' });
      var pays = item.payments || [];
      if (!pays.length) list.appendChild(h('div', { class: 'fa-empty', text: 'پرداختی ثبت نشده' }));
      pays.forEach(function (p) {
        list.appendChild(h('div', { class: 'fa-li' }, [
          h('div', { class: 'fa-li-main' }, [h('b', { text: fmt(p.amount) }), h('span', { text: ' — ' + toJalali(p.date) + (p.notes ? ' — ' + p.notes : '') })]),
          h('button', { type: 'button', class: 'fa-icon', text: '✏️', onclick: function () { editPayment(payBase, p, done); } }),
          h('button', { type: 'button', class: 'fa-icon', text: '🗑', onclick: function () {
            confirmBox('این پرداخت حذف شود؟').then(function (ok) {
              if (!ok) return;
              api('DELETE', payBase + p.id).then(function () { sheets.slice().forEach(function (x) { x.close(); }); toast('حذف شد'); done(); })
                .catch(function (e) { toast(e.message, true); });
            });
          } })
        ]));
      });
      openSheet({ title: 'پرداخت‌های ثبت‌شده', body: list, actions: [{ label: 'بستن', kind: 'ghost', onClick: function (s) { s.close(); } }] });
    }).catch(function (e) { toast(e.message, true); });
  }

  function editPayment(payBase, p, done) {
    var form = buildForm([{ k: 'amount', label: 'مبلغ (ریال)', type: 'number', req: true }, { k: 'date', label: 'تاریخ', type: 'date', req: true }],
                         { amount: p.amount, date: p.date });
    openSheet({
      title: 'ویرایش پرداخت', body: form.el,
      actions: [
        { label: 'ذخیره', kind: 'primary', onClick: function (s, btn) {
            var miss = form.missing(); if (miss) return s.error('«' + miss + '» را وارد کنید');
            var v = form.read(); btn.disabled = true;
            api('PUT', payBase + p.id, { amount: v.amount, date: v.date }).then(function () {
              sheets.slice().forEach(function (x) { x.close(); }); toast('ذخیره شد'); done();
            }).catch(function (e) { btn.disabled = false; s.error(e.message); });
          } },
        { label: 'انصراف', kind: 'ghost', onClick: function (s) { s.close(); } }
      ]
    });
  }

  // --------------------------------------------------------------- اقساط وام
  var INST_STATUS = { paid: 'پرداخت‌شده', partially_paid: 'بخشی پرداخت‌شده', overdue: 'معوق', due: 'سررسید امروز', upcoming: 'آینده' };

  function openInstallments(loanId, done) {
    api('GET', '/loans/' + loanId).then(function (loan) {
      var list = h('div', { class: 'fa-list' });
      (loan.installments || []).forEach(function (i) {
        list.appendChild(h('div', { class: 'fa-li' }, [
          h('div', { class: 'fa-li-main' }, [
            h('b', { text: '#' + i.installment_number + ' — ' + toJalali(i.due_date) }),
            h('div', { class: 'fa-sub', text: 'مبلغ ' + fmt(i.amount) + ' · پرداخت‌شده ' + fmt(i.paid_amount) + ' · ' + (INST_STATUS[i.status] || i.status) })
          ]),
          h('button', { type: 'button', class: 'fa-icon', text: '✏️', onclick: function () { editInstallment(i, done); } })
        ]));
      });
      openSheet({ title: 'اقساط «' + loan.name + '»', body: list, actions: [{ label: 'بستن', kind: 'ghost', onClick: function (s) { s.close(); } }] });
    }).catch(function (e) { toast(e.message, true); });
  }

  function editInstallment(i, done) {
    var form = buildForm([
      { k: 'paidAmount', label: 'مبلغ پرداخت‌شده (برای پاک کردن پرداخت، ۰)', type: 'number', req: true },
      { k: 'amount', label: 'مبلغ قسط', type: 'number', req: true },
      { k: 'dueDate', label: 'سررسید', type: 'date', req: true }
    ], { paidAmount: i.paid_amount, amount: i.amount, dueDate: i.due_date });
    openSheet({
      title: 'ویرایش قسط ' + i.installment_number, body: form.el,
      actions: [
        { label: 'ذخیره', kind: 'primary', onClick: function (s, btn) {
            var miss = form.missing(); if (miss) return s.error('«' + miss + '» را وارد کنید');
            btn.disabled = true;
            api('PUT', '/loans/installments/' + i.id, form.read()).then(function () {
              sheets.slice().forEach(function (x) { x.close(); }); toast('ذخیره شد'); done();
            }).catch(function (e) { btn.disabled = false; s.error(e.message); });
          } },
        { label: 'انصراف', kind: 'ghost', onClick: function (s) { s.close(); } }
      ]
    });
  }

  // ------------------------------------------------------------- مدیریت مشتری‌ها
  function openCustomers() {
    api('GET', '/customers').then(function (customers) {
      var list = h('div', { class: 'fa-list' });
      if (!customers.length) list.appendChild(h('div', { class: 'fa-empty', text: 'مشتری‌ای ثبت نشده' }));
      customers.forEach(function (c) {
        list.appendChild(h('div', { class: 'fa-li' }, [
          h('div', { class: 'fa-li-main' }, [h('b', { text: c.name }), h('span', { text: c.phone ? ' — ' + c.phone : '' })]),
          h('button', { type: 'button', class: 'fa-icon', text: '✏️', onclick: function () { editCustomer(c); } }),
          h('button', { type: 'button', class: 'fa-icon', text: '🗑', onclick: function () {
            confirmBox('مشتری «' + c.name + '» حذف شود؟ (مشتری دارای فروش قسطی قابل حذف نیست.)').then(function (ok) {
              if (!ok) return;
              api('DELETE', '/customers/' + c.id).then(function () { sheets.slice().forEach(function (x) { x.close(); }); toast('حذف شد'); refreshPage(); })
                .catch(function (e) { toast(e.message, true); });
            });
          } })
        ]));
      });
      openSheet({ title: 'مشتریان', body: list, actions: [{ label: 'بستن', kind: 'ghost', onClick: function (s) { s.close(); } }] });
    }).catch(function (e) { toast(e.message, true); });
  }

  function editCustomer(c) {
    var form = buildForm([{ k: 'name', label: 'نام', req: true }, { k: 'phone', label: 'تلفن' }, { k: 'description', label: 'توضیح' }],
                         { name: c.name, phone: c.phone, description: c.description });
    openSheet({
      title: 'ویرایش مشتری', body: form.el,
      actions: [
        { label: 'ذخیره', kind: 'primary', onClick: function (s, btn) {
            var miss = form.missing(); if (miss) return s.error('«' + miss + '» را وارد کنید');
            var v = form.read(); btn.disabled = true;
            api('PUT', '/customers/' + c.id, { name: v.name, phone: nn(v.phone), description: nn(v.description) }).then(function () {
              sheets.slice().forEach(function (x) { x.close(); }); toast('ذخیره شد'); refreshPage();
            }).catch(function (e) { btn.disabled = false; s.error(e.message); });
          } },
        { label: 'انصراف', kind: 'ghost', onClick: function (s) { s.close(); } }
      ]
    });
  }

  // ------------------------------------------------- بارگذاری دوباره‌ی صفحه‌ی فعلی
  function navButtons() { return [].slice.call(document.querySelectorAll('aside nav button')); }
  function activeIndex(btns) {
    for (var i = 0; i < btns.length; i++) if (String(btns[i].className).indexOf('bg-indigo-50') !== -1) return i;
    return -1;
  }
  function refreshPage() {
    var btns = navButtons(), cur = activeIndex(btns);
    if (cur < 0) return location.reload();
    var main = document.querySelector('main'), top = main ? main.scrollTop : 0;
    var other = -1;
    btns.forEach(function (b, i) { if (other < 0 && i !== cur && /ایمپورت/.test(b.textContent)) other = i; });
    if (other < 0) other = cur === 0 ? 1 : 0;
    btns[other].click();                                // یک لحظه صفحه‌ی بدون درخواست → دوباره همین صفحه (mount تازه)
    setTimeout(function () {
      btns[cur].click();
      setTimeout(function () { var m = document.querySelector('main'); if (m) m.scrollTop = top; }, 150);
    }, 30);
  }

  // ----------------------------------------------------- علامت‌گذاری ردیف‌ها
  function fiberKey(el) {
    for (var k in el) {
      if (k.indexOf('__reactFiber$') === 0) { var f = el[k]; return f && f.key != null ? String(f.key) : null; }
    }
    return null;
  }

  function headerSig(table) {
    return [].slice.call(table.querySelectorAll('thead th')).map(function (th) {
      return th.textContent.replace(/[▲▼↑↓]/g, '').trim();
    }).filter(Boolean).join('|');
  }

  var scanQueued = false, hinted = {};
  function scan() {
    scanQueued = false;
    try {
      var main = document.querySelector('main');
      if (!main) return;
      [].forEach.call(main.querySelectorAll('table'), function (t) {
        // جدول تراکنش‌ها خودش ویرایش دارد؛ فقط جدول‌هایی که امضایشان شناخته‌شده است
        var kind = SIG[headerSig(t)];
        if (!kind) return;
        // «نام» تنها = دسته‌بندی؛ در سایر صفحه‌ها جدول تک‌ستونی وجود ندارد
        [].forEach.call(t.querySelectorAll('tbody tr'), function (tr) {
          if (tr.getAttribute('data-fa-kind')) return;
          var key = fiberKey(tr);
          if (key == null) return;
          tr.setAttribute('data-fa-kind', kind);
          tr.setAttribute('data-fa-id', key);
        });
        if (!hinted[kind] && t.querySelector('tbody tr[data-fa-kind]')) {
          hinted[kind] = true;
          toast('برای ویرایش یا حذف، روی هر ردیف بزنید');
        }
      });
      // برچسب‌ها به شکل chip هستند
      [].forEach.call(main.querySelectorAll('h2'), function (h2) {
        if (h2.textContent.trim() !== 'برچسب‌ها') return;
        var card = h2.parentElement && h2.parentElement.parentElement;
        if (!card) return;
        [].forEach.call(card.querySelectorAll('span.rounded-full'), function (chip) {
          if (chip.getAttribute('data-fa-kind')) return;
          var key = fiberKey(chip);
          if (key == null) return;
          chip.setAttribute('data-fa-kind', 'tags');
          chip.setAttribute('data-fa-id', key);
        });
      });
      syncFab();
    } catch (e) { /* علامت‌گذاری هرگز نباید صفحه را خراب کند */ }
  }

  function currentTitle() {
    var b = navButtons()[activeIndex(navButtons())];
    var span = b && b.querySelector('span:last-child');
    return span ? span.textContent.trim() : '';
  }

  // دکمه‌ی شناور «مشتریان» فقط در صفحه‌ی فروش قسطی
  function syncFab() {
    var want = currentTitle().indexOf('مشتریان') === 0;
    var fab = document.getElementById('fa-fab');
    if (want && !fab) {
      document.body.appendChild(h('button', { id: 'fa-fab', type: 'button', text: '👥 مشتریان', onclick: openCustomers }));
    } else if (!want && fab) {
      fab.remove();
    }
  }

  function queueScan() { if (!scanQueued) { scanQueued = true; requestAnimationFrame(scan); } }

  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!t.closest) return;
    if (t.closest('button, a, input, select, textarea, label, .fa-sheet-back')) return;
    var row = t.closest('[data-fa-kind]');
    if (!row) return;
    var kind = row.getAttribute('data-fa-kind');
    var title = (row.cells && row.cells[0] ? row.cells[0].textContent : row.textContent).trim().slice(0, 80);
    if (kind === 'debts' && row.cells && row.cells[1]) title = row.cells[0].textContent.trim() + ' — ' + row.cells[1].textContent.trim();
    rowMenu(kind, row.getAttribute('data-fa-id'), title);
  });

  function start() {
    var root = document.getElementById('root');
    if (!root) return;
    new MutationObserver(queueScan).observe(root, { subtree: true, childList: true });
    queueScan();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
