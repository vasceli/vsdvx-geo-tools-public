const $ = (id) => document.getElementById(id);

function setToday() {
  if (!$('contract_date').value) {
    const d = new Date();
    $('contract_date').value = d.toISOString().slice(0, 10);
  }
}

function value(id) { return $(id).value.trim(); }
function checked(id) { return Boolean($(id)?.checked); }

function safeFilePart(text, fallback = 'филиал') {
  const cleaned = String(text || fallback)
    .replace(/[<>:"/\\|?*]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return cleaned || fallback;
}

function outputFilename(ext) {
  const number = value('contract_number') || 'DEMO-001';
  const org = safeFilePart(value('org_name'));
  const months = value('months') || '6';
  return `Договор №${number} - ${org} ${months} мес.${ext}`;
}

function collectPayload() {
  const payment_schedule = [];
  if (value('pay1_date') && value('pay1_amount')) payment_schedule.push({ label: 'Оплата первой части', date: value('pay1_date'), amount: value('pay1_amount') });
  if (value('pay2_date') && value('pay2_amount')) payment_schedule.push({ label: 'Оплата второй части', date: value('pay2_date'), amount: value('pay2_amount') });
  const includeReputation = checked('include_reputation');
  return {
    contract_number: value('contract_number'),
    contract_date: value('contract_date'),
    months: Number(value('months')),
    total_price: Number(value('total_price')),
    include_reputation: includeReputation,
    reputation_total: includeReputation && value('reputation_total') ? Number(value('reputation_total')) : 0,
    vat_mode: value('vat_mode'),
    customer_legal_name: value('customer_legal_name'),
    customer_director_position: value('customer_director_position'),
    customer_long_name: value('customer_long_name'),
    customer_basis: value('customer_basis'),
    customer_inn: value('customer_inn'),
    customer_kpp: value('customer_kpp'),
    customer_ogrn: value('customer_ogrn'),
    customer_short_sign: value('customer_short_sign'),
    customer_legal_address: value('customer_legal_address'),
    customer_rs: value('customer_rs'),
    customer_bank: value('customer_bank'),
    customer_bank_address: value('customer_bank_address'),
    customer_bik: value('customer_bik'),
    customer_ks: value('customer_ks'),
    maps_link: value('maps_link'),
    org_name: value('org_name'),
    org_address: value('org_address'),
    payment_schedule,
  };
}

function applyParsed(parsed) {
  const customerFields = [
    'customer_legal_name', 'customer_director_position', 'customer_long_name', 'customer_basis',
    'customer_inn', 'customer_kpp', 'customer_ogrn', 'customer_short_sign', 'customer_legal_address',
    'customer_rs', 'customer_bank', 'customer_bank_address', 'customer_bik', 'customer_ks'
  ];
  for (const key of customerFields) {
    if ($(key)) $(key).value = parsed[key] || '';
  }
}

function formatMoney(n) {
  return Math.round(Number(n || 0)).toLocaleString('ru-RU') + ',00';
}

async function apiJson(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function renderTable(calc) {
  const tbody = $('services_table').querySelector('tbody');
  tbody.innerHTML = '';
  let sectionNo = 0;
  for (const row of calc.rows) {
    const tr = document.createElement('tr');
    tr.className = row.type;
    const tdNo = document.createElement('td');
    const tdName = document.createElement('td');
    const tdAmount = document.createElement('td');
    if (row.type === 'section') tdNo.textContent = String(++sectionNo);
    else if (row.type === 'total') tdNo.textContent = String(sectionNo + 1);
    tdName.textContent = row.name;
    tdAmount.textContent = formatMoney(row.amount);
    tr.append(tdNo, tdName, tdAmount);
    tbody.appendChild(tr);
  }
}

async function calculate() {
  const req = {
    months: Number(value('months')),
    total_price: Number(value('total_price')),
    include_reputation: checked('include_reputation'),
    reputation_total: checked('include_reputation') && value('reputation_total') ? Number(value('reputation_total')) : 0,
  };
  const calc = await apiJson('api/calculate', req);
  renderTable(calc);
  return calc;
}

async function validate() {
  const data = await apiJson('api/validate', collectPayload());
  const el = $('validation');
  if (!data.ok || data.warnings.length) {
    el.className = 'status error';
    el.textContent = data.warnings.join('\n');
  } else {
    el.className = 'status ok';
    el.textContent = 'Проверка прошла. Критичных незаполненных полей нет.';
  }
  return data;
}

function toggleReputation() {
  const enabled = checked('include_reputation');
  $('reputation_total').disabled = !enabled;
  if (!enabled) {
    $('reputation_total').value = '';
    $('reputation_total').placeholder = '0 — договор без репутации';
  }
}

async function downloadGenerated(endpoint, ext) {
  await calculate();
  await validate();
  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(collectPayload()),
  });
  if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = outputFilename(ext);
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

$('parse_requisites_btn').addEventListener('click', async () => {
  const file = $('requisites_file').files[0];
  const status = $('parse_status');
  if (!file) {
    status.className = 'status error';
    status.textContent = 'Сначала выбери файл с реквизитами.';
    return;
  }
  status.className = 'status';
  status.textContent = 'Парсю файл...';
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('api/parse-requisites', { method: 'POST', body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`);
    const parsed = await res.json();
    applyParsed(parsed);
    status.className = parsed.missing_fields?.length ? 'status error' : 'status ok';
    status.textContent = parsed.missing_fields?.length
      ? `Распарсил, но надо проверить/дозаполнить:\n${parsed.missing_fields.join('\n')}`
      : 'Реквизиты распарсились. Все равно проверь глазами.';
  } catch (e) {
    status.className = 'status error';
    status.textContent = e.message;
  }
});

$('parse_map_btn').addEventListener('click', async () => {
  const status = $('map_status');
  status.className = 'status';
  status.textContent = 'Пробую получить данные из Яндекс.Карт...';
  try {
    const parsed = await apiJson('api/parse-map', { url: value('maps_link') });
    if (parsed.org_name) $('org_name').value = parsed.org_name;
    if (parsed.org_address) $('org_address').value = parsed.org_address;
    status.className = parsed.warnings?.length ? 'status error' : 'status ok';
    status.textContent = [
      parsed.profile_id ? `ID профиля: ${parsed.profile_id}` : '',
      parsed.source ? `Источник: ${parsed.source}` : '',
      ...(parsed.warnings || []),
      'Поля филиала можно поправить вручную.'
    ].filter(Boolean).join('\n');
  } catch (e) {
    status.className = 'status error';
    status.textContent = e.message;
  }
});

$('calculate_btn').addEventListener('click', async () => {
  try { await calculate(); await validate(); }
  catch (e) { $('validation').className = 'status error'; $('validation').textContent = e.message; }
});

$('preview_btn').addEventListener('click', async () => {
  try {
    await calculate();
    const res = await fetch('api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collectPayload()),
    });
    if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`);
    const html = await res.text();
    const w = window.open('', '_blank');
    w.document.open();
    w.document.write(html);
    w.document.close();
  } catch (e) {
    $('validation').className = 'status error';
    $('validation').textContent = e.message;
  }
});

$('docx_btn').addEventListener('click', async () => {
  try { await downloadGenerated('api/generate-docx', 'docx'); }
  catch (e) { $('validation').className = 'status error'; $('validation').textContent = e.message; }
});

$('pdf_btn').addEventListener('click', async () => {
  try { await downloadGenerated('api/generate-pdf', 'pdf'); }
  catch (e) { $('validation').className = 'status error'; $('validation').textContent = e.message; }
});

$('months').addEventListener('change', async () => {
  const plans = await fetch('api/plans').then(r => r.json());
  const plan = plans[value('months')];
  if (plan) {
    $('total_price').value = plan.default_total;
    if (checked('include_reputation')) $('reputation_total').placeholder = plan.default_reputation_total;
  }
  await calculate().catch(() => {});
});

$('include_reputation').addEventListener('change', async () => {
  toggleReputation();
  await calculate().catch(() => {});
});

for (const id of ['total_price', 'reputation_total']) {
  $(id).addEventListener('input', () => calculate().catch(() => {}));
}

setToday();
toggleReputation();
calculate().catch(() => {});
