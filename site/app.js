const tableBody = document.getElementById('model-rows');
const filterButtons = document.querySelectorAll('.filter');
const landscapeChart = document.getElementById('landscape-chart');
const landscapeTooltip = document.getElementById('landscape-tooltip');
const landscapeMetricButtons = document.querySelectorAll('.landscape-metric');
const languageCharts = [
  { element: document.getElementById('language-chart-sg'), key: 'state_given_by_language', label: 'State-Given' },
  { element: document.getElementById('language-chart-ss'), key: 'state_seeking_by_language', label: 'State-Seeking' }
];
const gapChart = document.getElementById('gap-chart');
const gapTooltip = document.getElementById('gap-tooltip');
const gapFilterButtons = document.querySelectorAll('.gap-filter');
let loadedModels = [];
let loadedBandSummary = [];
let landscapeMetric = 'sg';
let gapFilter = 'all';

function percent(value) {
  return `${Number(value).toFixed(1)}%`;
}

function modelBrand(model) {
  const name = String(model.model || '').toLowerCase();
  if (name.startsWith('qwen')) return { key: 'qwen', label: 'Qwen', src: 'assets/model-logos/qwen-icon.png' };
  if (name.startsWith('minicpm')) return { key: 'minicpm', label: 'MiniCPM', src: 'assets/model-logos/minicpm-icon.png' };
  if (name.startsWith('deepseek')) return { key: 'deepseek', label: 'DeepSeek', src: 'assets/model-logos/deepseek-icon.png' };
  if (name.startsWith('lfm')) return { key: 'lfm', label: 'Liquid AI', src: 'assets/model-logos/lfm.png' };
  if (name.startsWith('glm')) return { key: 'glm', label: 'GLM / Z.ai', src: 'assets/model-logos/glm.png' };
  if (name.startsWith('mimo')) return { key: 'mimo', label: 'MiMo', src: 'assets/model-logos/mimo-wordmark.svg' };
  if (name.startsWith('minimax')) return { key: 'minimax', label: 'MiniMax', src: 'assets/model-logos/minimax-icon.png' };
  return { key: 'generic', mark: '·', label: 'Model' };
}

function modelLogo(model) {
  const brand = modelBrand(model);
  const logo = document.createElement('span');
  logo.className = `model-logo ${brand.key}`;
  logo.setAttribute('aria-hidden', 'true');
  logo.title = brand.label;
  if (brand.src) {
    const image = document.createElement('img');
    image.src = brand.src;
    image.alt = '';
    image.loading = 'lazy';
    image.decoding = 'async';
    logo.appendChild(image);
  } else {
    logo.textContent = brand.mark;
  }
  return logo;
}

function modelRow(model, rank) {
  const row = document.createElement('tr');
  if (model.class === 'baseline') row.className = 'reference';

  const name = document.createElement('td');
  const modelCell = document.createElement('div');
  modelCell.className = 'model-cell';
  const rankLabel = document.createElement('span');
  rankLabel.className = 'rank';
  rankLabel.textContent = String(rank).padStart(2, '0');
  const modelName = document.createElement('strong');
  modelName.textContent = model.model;
  modelCell.append(rankLabel, modelLogo(model), modelName);
  if (model.class === 'baseline') {
    const baselineLabel = document.createElement('span');
    baselineLabel.className = 'baseline-tag';
    baselineLabel.textContent = 'Baseline';
    modelCell.appendChild(baselineLabel);
  }
  name.appendChild(modelCell);

  const cells = [
    model.size || '—',
    model.platform || '—',
    percent(model.sg),
    percent(model.ss),
  ];

  row.appendChild(name);
  cells.forEach((value) => {
    const cell = document.createElement('td');
    cell.textContent = value;
    row.appendChild(cell);
  });

  const mean = document.createElement('td');
  const meanValue = document.createElement('b');
  meanValue.textContent = percent(model.overall);
  mean.appendChild(meanValue);
  row.appendChild(mean);
  return row;
}

function sortModels(models) {
  return [...models].sort((a, b) => {
    const classOrder = { local: 0, baseline: 1 };
    return (classOrder[a.class] - classOrder[b.class]) || (Number(b.overall) - Number(a.overall));
  });
}

function render(models, filter = 'all') {
  const filtered = sortModels(models).filter((model) => {
    if (filter === 'all') return true;
    if (filter === 'Server') return model.class === 'baseline';
    return model.band === filter;
  });

  tableBody.replaceChildren();
  filtered.forEach((model, index) => {
    tableBody.appendChild(modelRow(model, index + 1));
  });
}

const svgNamespace = 'http://www.w3.org/2000/svg';

function svgElement(name, attributes = {}, text = '') {
  const element = document.createElementNS(svgNamespace, name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  if (text) element.textContent = text;
  return element;
}

function numericSize(model) {
  const value = Number.parseFloat(String(model.size || '').replace(/[^0-9.]/g, ''));
  return Number.isFinite(value) ? value : null;
}

function hideLandscapeTooltip() {
  if (landscapeTooltip) landscapeTooltip.hidden = true;
}

function showLandscapeTooltip(model, point) {
  if (!landscapeTooltip || !landscapeChart) return;
  landscapeTooltip.textContent = `${model.model} · ${model.size} · ${model.platform || '—'} · SG ${percent(model.sg)} · SS ${percent(model.ss)}`;
  const wrap = landscapeChart.parentElement.getBoundingClientRect();
  const target = point.getBoundingClientRect();
  const left = Math.min(target.right - wrap.left + 8, wrap.width - 228);
  const top = Math.max(target.top - wrap.top - 10, 8);
  landscapeTooltip.style.left = `${Math.max(left, 8)}px`;
  landscapeTooltip.style.top = `${top}px`;
  landscapeTooltip.hidden = false;
}

function renderLandscape(models, metric = landscapeMetric) {
  if (!landscapeChart) return;
  const localModels = models.filter((model) => model.class === 'local' && numericSize(model) !== null);
  const width = 760;
  const height = 276;
  const plot = { left: 48, right: 18, top: 18, bottom: 42 };
  const plotWidth = width - plot.left - plot.right;
  const plotHeight = height - plot.top - plot.bottom;
  const xMin = 0.35;
  const xMax = 7.15;
  const yMax = 30;
  const x = (value) => plot.left + ((value - xMin) / (xMax - xMin)) * plotWidth;
  const y = (value) => plot.top + (1 - Math.min(Number(value) || 0, yMax) / yMax) * plotHeight;

  landscapeChart.replaceChildren();
  landscapeChart.appendChild(svgElement('title', { id: 'landscape-title' }, 'Local model success by parameter count'));
  landscapeChart.appendChild(svgElement('desc', { id: 'landscape-desc' }, 'Each point represents one evaluated local model. Horizontal position shows parameter count and vertical position shows strict micro-success.'));

  const grid = svgElement('g');
  [0, 10, 20, 30].forEach((tick) => {
    const tickY = y(tick);
    grid.appendChild(svgElement('line', { class: 'landscape-gridline', x1: plot.left, x2: width - plot.right, y1: tickY, y2: tickY }));
    grid.appendChild(svgElement('text', { class: 'landscape-axis', x: plot.left - 9, y: tickY + 3, 'text-anchor': 'end' }, `${tick}%`));
  });
  [1, 3].forEach((boundary) => {
    grid.appendChild(svgElement('line', { class: 'landscape-band-line', x1: x(boundary), x2: x(boundary), y1: plot.top, y2: height - plot.bottom }));
  });
  landscapeChart.appendChild(grid);

  const xTicks = [0.5, 1, 2, 3, 4, 7];
  const axis = svgElement('g');
  xTicks.forEach((tick) => {
    axis.appendChild(svgElement('text', { class: 'landscape-axis', x: x(tick), y: height - 21, 'text-anchor': 'middle' }, `${tick}B`));
  });
  axis.appendChild(svgElement('text', { class: 'landscape-axis-label', x: plot.left, y: height - 5 }, 'model size (parameters)'));
  axis.appendChild(svgElement('text', { class: 'landscape-axis-label', x: plot.left, y: 10 }, `${metric === 'sg' ? 'State-Given' : 'State-Seeking'} strict success`));
  landscapeChart.appendChild(axis);

  const points = svgElement('g');
  const topModel = [...localModels].sort((a, b) => Number(b[metric]) - Number(a[metric]))[0];
  localModels.forEach((model) => {
    const point = svgElement('circle', {
      class: `landscape-point${model === topModel ? ' is-top' : ''}`,
      cx: x(numericSize(model)),
      cy: y(model[metric]),
      r: model === topModel ? 5 : 4,
      'data-brand': modelBrand(model).key,
      tabindex: '0',
      role: 'button',
      'aria-label': `${model.model}, ${model.size}, ${metric === 'sg' ? 'State-Given' : 'State-Seeking'} ${percent(model[metric])}`
    });
    point.addEventListener('mouseenter', () => showLandscapeTooltip(model, point));
    point.addEventListener('focus', () => showLandscapeTooltip(model, point));
    point.addEventListener('mouseleave', hideLandscapeTooltip);
    point.addEventListener('blur', hideLandscapeTooltip);
    points.appendChild(point);
  });
  landscapeChart.appendChild(points);

  const referenceBars = document.getElementById('reference-bars');
  if (referenceBars) {
    referenceBars.replaceChildren();
    models.filter((model) => model.class === 'baseline').sort((a, b) => Number(b[metric]) - Number(a[metric])).forEach((model) => {
      const row = document.createElement('div');
      row.className = 'reference-row';
      row.appendChild(modelLogo(model));
      const label = document.createElement('label');
      label.textContent = model.model;
      label.title = model.model;
      const value = document.createElement('b');
      value.textContent = percent(model[metric]);
      row.append(label, value);
      referenceBars.appendChild(row);
    });
  }

  const head = document.getElementById('landscape-head');
  if (head && topModel) {
    const metricName = metric === 'sg' ? 'State-Given' : 'State-Seeking';
    head.textContent = `${topModel.model} · ${metricName} ${percent(topModel[metric])}`;
  }
}

function renderLanguageChart(summary) {
  const width = 520;
  const height = 258;
  const plot = { left: 46, right: 18, top: 18, bottom: 38 };
  const plotHeight = height - plot.top - plot.bottom;
  const yMax = 25;
  const y = (value) => plot.top + (1 - Math.min(Number(value) || 0, yMax) / yMax) * plotHeight;
  const groupX = [125, 260, 395];
  languageCharts.forEach(({ element, key, label }) => {
    if (!element) return;
    element.replaceChildren();
    element.appendChild(svgElement('title', { id: `${element.id}-title` }, `${label} success by local model size and language`));
    element.appendChild(svgElement('desc', { id: `${element.id}-desc` }, `Grouped bars compare Chinese and English strict micro-success across local model size bands for ${label}.`));
    const grid = svgElement('g');
    [0, 5, 10, 15, 20, 25].forEach((tick) => {
      const tickY = y(tick);
      grid.appendChild(svgElement('line', { class: 'analysis-gridline', x1: plot.left, x2: width - plot.right, y1: tickY, y2: tickY }));
      grid.appendChild(svgElement('text', { class: 'analysis-axis', x: plot.left - 8, y: tickY + 3, 'text-anchor': 'end' }, `${tick}%`));
    });
    element.appendChild(grid);
    const bars = svgElement('g');
    summary.forEach((band, index) => {
      const values = band[key] || {};
      const chinese = Number(values.Chinese) || 0;
      const english = Number(values.English) || 0;
      const baseY = y(0);
      const chineseX = groupX[index] - 20;
      const englishX = groupX[index] + 4;
      const chineseBar = svgElement('rect', { class: 'language-bar chinese', x: chineseX, y: y(chinese), width: 18, height: Math.max(baseY - y(chinese), 1), rx: 2, tabindex: '0', role: 'img', 'aria-label': `${label}, ${band.label}, Chinese ${percent(chinese)}` });
      const englishBar = svgElement('rect', { class: 'language-bar english', x: englishX, y: y(english), width: 18, height: Math.max(baseY - y(english), 1), rx: 2, tabindex: '0', role: 'img', 'aria-label': `${label}, ${band.label}, English ${percent(english)}` });
      bars.append(chineseBar, englishBar);
      if (chinese > 0) bars.appendChild(svgElement('text', { class: 'analysis-value', x: chineseX + 9, y: y(chinese) - 6, 'text-anchor': 'middle' }, chinese.toFixed(1)));
      if (english > 0) bars.appendChild(svgElement('text', { class: 'analysis-value', x: englishX + 9, y: y(english) - 6, 'text-anchor': 'middle' }, english.toFixed(1)));
      bars.appendChild(svgElement('text', { class: 'analysis-axis-label', x: groupX[index], y: height - 16, 'text-anchor': 'middle' }, band.label));
    });
    element.appendChild(bars);
  });
}

function shortModelName(name) {
  return name.replace(/-Instruct|-SFT|-DPO/g, '').replace('DeepSeek-R1-Distill-', 'DS-R1-').slice(0, 24);
}

function showGapTooltip(model, point) {
  if (!gapTooltip || !gapChart) return;
  const gap = Math.abs(Number(model.sg) - Number(model.ss));
  gapTooltip.textContent = `${model.model} · ${model.size} · SG ${percent(model.sg)} · SS ${percent(model.ss)} · gap ${gap.toFixed(1)} pp`;
  const wrap = gapChart.parentElement.getBoundingClientRect();
  const target = point.getBoundingClientRect();
  gapTooltip.style.left = `${Math.min(Math.max(target.right - wrap.left + 8, 8), wrap.width - 228)}px`;
  gapTooltip.style.top = `${Math.max(target.top - wrap.top - 10, 8)}px`;
  gapTooltip.hidden = false;
}

function hideGapTooltip() {
  if (gapTooltip) gapTooltip.hidden = true;
}

function renderGapChart(models, filter = gapFilter) {
  if (!gapChart) return;
  const localModels = models.filter((model) => model.class === 'local' && (filter === 'all' || model.band === filter)).sort((a, b) => Number(b.overall) - Number(a.overall));
  const width = 720;
  const rowHeight = 22;
  const height = Math.max(250, 42 + localModels.length * rowHeight);
  const plot = { left: 184, right: 35, top: 28, bottom: 20 };
  const plotWidth = width - plot.left - plot.right;
  const xMax = 32;
  const x = (value) => plot.left + (Math.min(Number(value) || 0, xMax) / xMax) * plotWidth;
  gapChart.setAttribute('viewBox', `0 0 ${width} ${height}`);
  gapChart.replaceChildren();
  gapChart.appendChild(svgElement('title', { id: 'gap-title' }, 'State-Given and State-Seeking results by local model'));
  gapChart.appendChild(svgElement('desc', { id: 'gap-desc' }, 'Each row connects a model\'s State-Seeking and State-Given scores, showing the interface gap.'));
  const grid = svgElement('g');
  [0, 5, 10, 15, 20, 25, 30].forEach((tick) => {
    const tickX = x(tick);
    grid.appendChild(svgElement('line', { class: 'analysis-gridline vertical', x1: tickX, x2: tickX, y1: plot.top - 14, y2: height - plot.bottom }));
    grid.appendChild(svgElement('text', { class: 'analysis-axis', x: tickX, y: 15, 'text-anchor': 'middle' }, `${tick}%`));
  });
  gapChart.appendChild(grid);
  const rows = svgElement('g');
  localModels.forEach((model, index) => {
    const rowY = plot.top + index * rowHeight;
    const sgX = x(model.sg);
    const ssX = x(model.ss);
    rows.appendChild(svgElement('line', { class: 'gap-row-line', x1: plot.left, x2: width - plot.right, y1: rowY + 5, y2: rowY + 5 }));
    rows.appendChild(svgElement('text', { class: 'gap-model-label', x: 6, y: rowY + 8 }, shortModelName(model.model)));
    const span = svgElement('line', { class: 'gap-span', x1: Math.min(ssX, sgX), x2: Math.max(ssX, sgX), y1: rowY + 4, y2: rowY + 4 });
    rows.appendChild(span);
    const ssPoint = svgElement('circle', { class: 'gap-point ss', cx: ssX, cy: rowY + 4, r: 4, tabindex: '0', role: 'img', 'aria-label': `${model.model} State-Seeking ${percent(model.ss)}` });
    const sgPoint = svgElement('circle', { class: 'gap-point sg', cx: sgX, cy: rowY + 4, r: 4, tabindex: '0', role: 'img', 'aria-label': `${model.model} State-Given ${percent(model.sg)}` });
    [ssPoint, sgPoint].forEach((point) => {
      point.addEventListener('mouseenter', () => showGapTooltip(model, point));
      point.addEventListener('focus', () => showGapTooltip(model, point));
      point.addEventListener('mouseleave', hideGapTooltip);
      point.addEventListener('blur', hideGapTooltip);
    });
    rows.append(ssPoint, sgPoint);
    rows.appendChild(svgElement('text', { class: 'gap-value', x: width - 6, y: rowY + 8, 'text-anchor': 'end' }, `${Math.abs(Number(model.sg) - Number(model.ss)).toFixed(1)} pp`));
  });
  gapChart.appendChild(rows);
}

fetch('../data/results.json')
  .then((response) => {
    if (!response.ok) throw new Error(`Could not load results: ${response.status}`);
    return response.json();
  })
  .then((data) => {
    const models = data.models || [];
    loadedModels = models;
    loadedBandSummary = data.size_band_summary || [];
    render(models);
    renderLandscape(models);
    renderLanguageChart(loadedBandSummary);
    renderGapChart(models);
    filterButtons.forEach((button) => {
      button.addEventListener('click', () => {
        filterButtons.forEach((item) => item.classList.remove('active'));
        button.classList.add('active');
        render(models, button.dataset.filter);
      });
    });
  })
  .catch((error) => {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 6;
    cell.textContent = 'Results could not be loaded. Open ../data/results.json to inspect the release.';
    row.appendChild(cell);
    tableBody.replaceChildren(row);
    console.error(error);
  });

const taskData = {
  DGC: {
    title: 'Device grounding',
    prompt: 'Turn on the desk lamp beside the monitor.',
    steps: [
      ['01', 'Use supplied context', 'Find the desk lamp beside the monitor in the provided home state.'],
      ['02', 'Control the target', 'Turn on the grounded desk lamp.'],
      ['03', 'Check side effects', 'The ceiling lamp and fan stay unchanged.']
    ],
    seekSteps: [
      ['01', 'Start partially observed', 'The target is not grounded until device state is queried.'],
      ['02', 'Query and resolve', 'Inspect available devices and locate the desk lamp.'],
      ['03', 'Control and verify', 'Turn it on; leave other devices unchanged.']
    ]
  },
  MSC: {
    title: 'Multi-device control',
    prompt: 'Turn on the lights in occupied rooms, but leave the fans alone.',
    steps: [
      ['01', 'Apply the room rule', 'Select lights in occupied rooms from the supplied state.'],
      ['02', 'Control selected lights', 'Turn on both matching lights.'],
      ['03', 'Exclude non-targets', 'Fans and empty-room lights stay unchanged.']
    ],
    seekSteps: [
      ['01', 'Query room state', 'Check room occupancy and device status.'],
      ['02', 'Select and control', 'Turn on lights only in occupied rooms.'],
      ['03', 'Verify exclusions', 'Fans and empty-room lights stay unchanged.']
    ]
  },
  AIR: {
    title: 'Ambiguity resolution',
    prompt: 'Make it comfortable in here.',
    steps: [
      ['01', 'Check the request', 'The room and the desired adjustment are missing.'],
      ['02', 'Ask before acting', 'Ask which room and what should change.'],
      ['03', 'Hold device state', 'No device changes while the request is unclear.']
    ],
    seekSteps: [
      ['01', 'Inspect available state', 'A device query cannot supply the missing intent.'],
      ['02', 'Ask a focused question', 'Clarify the room and desired adjustment.'],
      ['03', 'Wait for the reply', 'Leave all devices unchanged.']
    ]
  },
  FAR: {
    title: 'Future automation',
    prompt: 'Every weekday at 7:00, turn on the kitchen light.',
    steps: [
      ['01', 'Parse the schedule', 'Weekdays at 7:00; turn on the kitchen light.'],
      ['02', 'Save the future rule', 'Register the trigger and its action.'],
      ['03', 'Keep now unchanged', 'The kitchen light stays off until the trigger.']
    ],
    seekSteps: [
      ['01', 'Query current state', 'Inspect the kitchen light before scheduling.'],
      ['02', 'Register the rule', 'Save weekdays at 7:00 → kitchen light on.'],
      ['03', 'Wait for the trigger', 'Current device state remains unchanged.']
    ]
  },
  DCR: {
    title: 'Dialogue context',
    prompt: 'Turn on the lamp. Actually, the bedroom one.',
    steps: [
      ['01', 'Use the full dialogue', 'The supplied context includes the latest correction.'],
      ['02', 'Update the target', '“The bedroom one” replaces the earlier reference.'],
      ['03', 'Act on this turn', 'Turn on the bedroom lamp once.']
    ],
    seekSteps: [
      ['01', 'Retrieve prior context', 'Query the earlier turn needed to resolve “one”.'],
      ['02', 'Apply the correction', 'Resolve the current target to the bedroom lamp.'],
      ['03', 'Act on this turn', 'Turn it on once; do not replay history.']
    ]
  },
  PMU: {
    title: 'Personalized memory',
    prompt: 'Set the living-room lights the way I prefer in the evening.',
    steps: [
      ['01', 'Use supplied memory', 'Retrieve the user’s evening-light preference.'],
      ['02', 'Validate the memory', 'Check that it is current and relevant.'],
      ['03', 'Apply the preference', 'Set the living-room light to warm, 40%.']
    ],
    seekSteps: [
      ['01', 'Query relevant memory', 'Search for this user’s evening preference.'],
      ['02', 'Validate the result', 'Ignore stale or unrelated memories.'],
      ['03', 'Apply the preference', 'Set the living-room light to warm, 40%.']
    ]
  },
  REQ: {
    title: 'Read-only queries',
    prompt: 'How many lights are on right now?',
    steps: [
      ['01', 'Read supplied state', 'Count lights currently marked on.'],
      ['02', 'Return the result', 'Two lights are on.'],
      ['03', 'Make no changes', 'Every device remains in its current state.']
    ],
    seekSteps: [
      ['01', 'Query device state', 'Read each light before counting.'],
      ['02', 'Aggregate the result', 'Two lights are on.'],
      ['03', 'Answer read-only', 'Return the count without issuing control.']
    ]
  }
};

function sceneAppend(parent, name, attributes = {}, text = '') {
  const element = svgElement(name, attributes, text);
  parent.appendChild(element);
  return element;
}

function addRoomFrame(svg, room) {
  const scale = room.scale || 1;
  const group = sceneAppend(svg, 'g', {
    class: `scene-room room-${room.id}`,
    transform: `translate(${room.x} ${room.y}) scale(${scale})`
  });
  sceneAppend(group, 'ellipse', { class: 'room-shadow', cx: 250, cy: 202, rx: 232, ry: 25 });
  sceneAppend(group, 'path', { class: 'room-shell', d: 'M25 110 L250 194 L475 110 L475 126 L250 210 L25 126 Z' });
  sceneAppend(group, 'polygon', { class: 'room-wall room-wall-left', points: '25,110 25,32 250,-48 250,30' });
  sceneAppend(group, 'polygon', { class: 'room-wall room-wall-right', points: '250,30 250,-48 475,32 475,110' });
  sceneAppend(group, 'polygon', { class: 'room-floor', points: '25,110 250,30 475,110 250,194' });
  sceneAppend(group, 'path', { class: 'room-baseboard', d: 'M25 101 L250 21 M250 21 L475 101' });
  sceneAppend(group, 'polygon', { class: 'room-window', points: '55,82 55,49 112,29 112,62' });
  sceneAppend(group, 'polygon', { class: 'window-view', points: '60,76 60,53 107,36 107,59' });
  sceneAppend(group, 'path', { class: 'window-landscape', d: 'M60 66 Q72 58 82 63 T107 55 V59 L60 76 Z' });
  sceneAppend(group, 'path', { class: 'window-frame', d: 'M83 72 L83 39 M55 65 L112 45' });
  sceneAppend(group, 'path', { class: 'window-curtains', d: 'M49 47 Q53 45 57 47 L57 79 L52 82 Z M111 25 Q116 24 119 27 L116 59 L110 62 Z' });
  sceneAppend(group, 'path', { class: 'door-trim', d: 'M384 1 L450 25 V81 L384 57 Z' });
  sceneAppend(group, 'polygon', { class: 'room-door', points: '390,4 444,24 444,74 390,55' });
  sceneAppend(group, 'path', { class: 'door-panel', d: 'M396 12 L438 28 V65 L396 50 Z M402 19 L432 30 V46 L402 35 Z' });
  sceneAppend(group, 'circle', { class: 'door-handle', cx: 433, cy: 51, r: 1.8 });
  sceneAppend(group, 'polygon', { class: 'wall-art-frame', points: '150,8 190,-6 190,13 150,28' });
  sceneAppend(group, 'polygon', { class: 'wall-art-print', points: '154,9 186,-2 186,10 154,22' });
  sceneAppend(group, 'path', { class: 'wall-art-detail', d: 'M156 17 Q166 4 174 13 T184 5' });
  sceneAppend(group, 'path', { class: 'room-wall-seam', d: 'M250 30 V-48' });
  sceneAppend(group, 'text', { class: 'room-label', x: 302, y: 56 }, room.label);
  sceneAppend(group, 'text', { class: 'room-code', x: 457, y: 95, 'text-anchor': 'end' }, room.code);
  [
    'M72 127 L250 64', 'M119 145 L250 99', 'M181 168 L250 143',
    'M326 57 L428 94', 'M292 82 L394 120', 'M256 108 L357 146'
  ].forEach((path) => sceneAppend(group, 'path', { class: 'floor-seam', d: path }));
  return group;
}

function addLamp(group, id, x, y, state) {
  const classes = ['scene-light'];
  if (state.targets.has(id)) classes.push('is-target');
  if (state.inspected.has(id)) classes.push('is-inspected');
  const light = sceneAppend(group, 'g', {
    class: classes.join(' '),
    transform: `translate(${x} ${y})`,
    'data-on': String(state.on.has(id)),
    'aria-hidden': 'true'
  });
  sceneAppend(light, 'ellipse', { class: 'light-halo', cx: 1, cy: -14, rx: 39, ry: 27 });
  sceneAppend(light, 'ellipse', { class: 'selection-halo', cx: 0, cy: -14, rx: 22, ry: 25 });
  sceneAppend(light, 'ellipse', { class: 'lamp-base', cx: 0, cy: 0, rx: 12, ry: 3.5 });
  sceneAppend(light, 'path', { class: 'lamp-arm', d: 'M0 -2 L2 -16 Q3 -22 2 -25' });
  sceneAppend(light, 'circle', { class: 'lamp-joint', cx: 2, cy: -15, r: 2.5 });
  sceneAppend(light, 'path', { class: 'lamp-shade', d: 'M-10 -25 L-14 -35 Q-14 -38 2 -38 Q18 -38 18 -35 L12 -25 Z' });
  sceneAppend(light, 'circle', { class: 'lamp-bulb', cx: 2, cy: -25, r: 3 });
  if (state.targets.has(id) || state.inspected.has(id)) {
    sceneAppend(light, 'text', { class: 'device-state', x: 0, y: 14, 'text-anchor': 'middle' }, state.on.has(id) ? 'ON' : state.inspected.has(id) ? 'READ' : 'TARGET');
  }
  return light;
}

function addCeilingLight(group, id, x, y, state) {
  const classes = ['scene-ceiling-light'];
  if (state.targets.has(id)) classes.push('is-target');
  if (state.inspected.has(id)) classes.push('is-inspected');
  const light = sceneAppend(group, 'g', {
    class: classes.join(' '),
    transform: `translate(${x} ${y})`,
    'data-on': String(state.on.has(id)),
    'aria-hidden': 'true'
  });
  sceneAppend(light, 'ellipse', { class: 'light-halo', cx: 0, cy: 16, rx: 38, ry: 24 });
  sceneAppend(light, 'ellipse', { class: 'selection-halo', cx: 0, cy: 14, rx: 22, ry: 17 });
  sceneAppend(light, 'path', { class: 'pendant-cord', d: 'M0 -32 V-8' });
  sceneAppend(light, 'path', { class: 'pendant-shade', d: 'M-18 -8 Q0 -17 18 -8 L12 2 H-12 Z' });
  sceneAppend(light, 'circle', { class: 'pendant-bulb', cx: 0, cy: 0, r: 3.5 });
  if (state.targets.has(id) || state.inspected.has(id)) {
    sceneAppend(light, 'text', { class: 'device-state', x: 0, y: 30, 'text-anchor': 'middle' }, state.on.has(id) ? 'ON' : state.inspected.has(id) ? 'READ' : 'TARGET');
  }
  return light;
}

function addFan(group, x, y, occupied = false) {
  const fan = sceneAppend(group, 'g', { class: 'scene-fan', transform: `translate(${x} ${y})`, 'aria-hidden': 'true' });
  sceneAppend(fan, 'ellipse', { class: 'fan-outline', cx: 0, cy: 0, rx: 26, ry: 14 });
  sceneAppend(fan, 'path', { class: 'fan-blades', d: 'M0 -2 C-8 -8 -29 -11 -31 -5 C-33 1 -11 3 0 1 C5 9 20 20 25 15 C30 10 12 -1 2 -3 C6 -12 7 -28 0 -29 C-7 -29 -6 -8 -1 0 C-12 3 -27 14 -23 20 C-19 26 -3 11 1 3 Z' });
  sceneAppend(fan, 'circle', { class: 'fan-hub', cx: 0, cy: 0, r: 4 });
  if (occupied) sceneAppend(fan, 'text', { class: 'fan-label', x: 0, y: 39, 'text-anchor': 'middle' }, 'UNCHANGED');
  return fan;
}

function addOccupant(group, x, y) {
  const person = sceneAppend(group, 'g', { class: 'scene-occupant', transform: `translate(${x} ${y})`, 'aria-hidden': 'true' });
  sceneAppend(person, 'ellipse', { class: 'person-shadow', cx: 0, cy: 18, rx: 10, ry: 4 });
  sceneAppend(person, 'circle', { class: 'person-head', cx: 0, cy: -1, r: 4.5 });
  sceneAppend(person, 'path', { class: 'person-body', d: 'M-6 15 Q-5 4 0 4 Q5 4 6 15 L4 17 H-4 Z' });
  sceneAppend(person, 'path', { class: 'person-legs', d: 'M-3 16 L-6 22 M3 16 L7 21' });
  sceneAppend(person, 'text', { class: 'occupant-label', x: 10, y: 9 }, 'OCCUPIED');
}

function addSceneBadge(svg, x, y, eyebrow, label, kind = '') {
  const badge = sceneAppend(svg, 'g', { class: `scene-badge ${kind}`.trim(), transform: `translate(${x} ${y})` });
  const width = Math.max(174, Math.min(258, label.length * 6.4 + 24));
  sceneAppend(badge, 'rect', { width, height: 42, rx: 10 });
  sceneAppend(badge, 'text', { class: 'badge-eyebrow', x: 12, y: 15 }, eyebrow);
  sceneAppend(badge, 'text', { class: 'badge-label', x: 12, y: 31 }, label);
}

function sceneState(family, step, mode) {
  const state = { on: new Set(), targets: new Set(), inspected: new Set() };
  const resolved = mode === 'SG' || step > 0;
  const actionStep = mode === 'SG' ? 1 : 2;
  if (family === 'DGC') {
    if (resolved) state.targets.add('desk');
    if (step >= actionStep) state.on.add('desk');
  } else if (family === 'MSC') {
    if (resolved) {
      state.targets.add('living');
      state.targets.add('bedside');
    }
    if (step >= actionStep) {
      state.on.add('living');
      state.on.add('bedside');
    }
  } else if (family === 'FAR') {
    if (resolved) state.targets.add('kitchen');
  } else if (family === 'DCR') {
    if (resolved) state.targets.add('bedside');
    if (step > 1) state.on.add('bedside');
  } else if (family === 'PMU') {
    if (resolved) state.targets.add('living');
    if (step > 1) state.on.add('living');
  } else if (family === 'REQ') {
    if (mode === 'SG' || step > 0) {
      state.on.add('living');
      state.on.add('kitchen');
    }
    if (resolved) {
      state.inspected.add('living');
      state.inspected.add('kitchen');
    }
  }
  return state;
}

function addWorkspaceFurniture(room, state) {
  sceneAppend(room, 'ellipse', { class: 'furniture-shadow', cx: 164, cy: 143, rx: 112, ry: 21 });
  sceneAppend(room, 'path', { class: 'desk-legs', d: 'M83 102 L83 145 M151 127 L151 160 M244 96 L244 135 M176 122 L176 156' });
  sceneAppend(room, 'path', { class: 'desk-front', d: 'M78 86 L164 118 L164 131 L78 99 Z' });
  sceneAppend(room, 'path', { class: 'desk-side', d: 'M164 118 L253 86 L253 99 L164 131 Z' });
  sceneAppend(room, 'path', { class: 'desk-top', d: 'M78 86 L166 55 L253 86 L164 118 Z' });
  sceneAppend(room, 'path', { class: 'monitor-shell', d: 'M127 50 L194 26 L194 72 L127 96 Z' });
  sceneAppend(room, 'path', { class: 'monitor-screen', d: 'M133 53 L188 33 L188 68 L133 88 Z' });
  sceneAppend(room, 'path', { class: 'monitor-content', d: 'M139 58 L160 50 M139 65 L178 51 M139 72 L168 62' });
  sceneAppend(room, 'path', { class: 'monitor-glint', d: 'M138 55 L169 44' });
  sceneAppend(room, 'path', { class: 'monitor-stand', d: 'M160 85 L160 99 M150 102 L171 94' });
  sceneAppend(room, 'path', { class: 'keyboard-top', d: 'M174 96 L211 83 L230 90 L193 104 Z' });
  sceneAppend(room, 'path', { class: 'keyboard-front', d: 'M193 104 L230 90 L230 94 L193 108 Z' });
  sceneAppend(room, 'path', { class: 'keyboard-keys', d: 'M181 95 L207 86 M186 98 L212 89 M191 101 L217 92' });
  sceneAppend(room, 'ellipse', { class: 'desk-mouse', cx: 238, cy: 91, rx: 4, ry: 2.5 });
  sceneAppend(room, 'path', { class: 'desk-plant-leaves', d: 'M101 80 Q94 70 98 66 Q105 69 104 79 Q104 66 111 64 Q114 69 106 81 Q115 72 120 76 Q118 82 106 85' });
  sceneAppend(room, 'path', { class: 'desk-plant-pot', d: 'M99 83 L112 79 L113 89 L101 93 Z' });
  addLamp(room, 'desk', 227, 83, state);
  addCeilingLight(room, 'ceiling-work', 286, 11, state);
}

function addLivingFurniture(room, state, occupied = false) {
  sceneAppend(room, 'path', { class: 'rug', d: 'M73 119 L244 58 L411 120 L242 183 Z' });
  sceneAppend(room, 'ellipse', { class: 'furniture-shadow', cx: 174, cy: 157, rx: 119, ry: 23 });
  sceneAppend(room, 'path', { class: 'sofa-side', d: 'M67 103 L153 70 L153 116 L67 148 Z' });
  sceneAppend(room, 'path', { class: 'sofa-back', d: 'M67 103 L67 78 L153 46 L153 70 Z M153 70 L153 46 L261 84 L261 109 Z' });
  sceneAppend(room, 'path', { class: 'sofa-seat', d: 'M67 103 L153 70 L261 109 L174 143 Z' });
  sceneAppend(room, 'path', { class: 'sofa-front', d: 'M67 103 L174 143 L174 164 L67 124 Z M174 143 L261 109 L261 130 L174 164 Z' });
  sceneAppend(room, 'path', { class: 'sofa-cushion', d: 'M84 101 L145 78 L169 87 L108 111 Z' });
  sceneAppend(room, 'path', { class: 'sofa-cushion', d: 'M158 77 L239 106 L217 116 L137 86 Z' });
  sceneAppend(room, 'path', { class: 'sofa-stitching', d: 'M72 109 L174 148 L254 118 M154 75 L154 105' });
  sceneAppend(room, 'path', { class: 'coffee-table-side', d: 'M267 122 L322 102 L322 111 L267 132 Z' });
  sceneAppend(room, 'path', { class: 'coffee-table-front', d: 'M220 105 L267 122 L267 132 L220 115 Z' });
  sceneAppend(room, 'path', { class: 'coffee-table-top', d: 'M220 105 L274 85 L322 102 L267 122 Z' });
  sceneAppend(room, 'path', { class: 'table-book', d: 'M237 101 L256 94 L269 99 L250 107 Z M250 107 L269 99 L269 102 L250 110 Z' });
  sceneAppend(room, 'ellipse', { class: 'table-cup', cx: 294, cy: 101, rx: 5, ry: 2.4 });
  sceneAppend(room, 'path', { class: 'table-cup-side', d: 'M289 101 L290 107 Q294 110 298 105 L299 101 M298 102 Q304 101 301 106' });
  sceneAppend(room, 'path', { class: 'table-leg', d: 'M230 117 L230 139 M309 108 L309 128 M276 133 L276 150' });
  sceneAppend(room, 'path', { class: 'side-table-top', d: 'M351 116 L393 101 L420 111 L378 127 Z' });
  sceneAppend(room, 'path', { class: 'side-table-front', d: 'M351 116 L378 127 L378 138 L351 127 Z M378 127 L420 111 L420 122 L378 138 Z' });
  addLamp(room, 'living', 389, 100, state);
  addFan(room, 325, 32, occupied);
  if (occupied) addOccupant(room, 291, 142);
}

function addBedroomFurniture(room, state, occupied = false) {
  sceneAppend(room, 'path', { class: 'rug bedroom-rug', d: 'M56 121 L225 61 L397 123 L228 185 Z' });
  sceneAppend(room, 'ellipse', { class: 'furniture-shadow', cx: 187, cy: 159, rx: 128, ry: 22 });
  sceneAppend(room, 'path', { class: 'bed-side', d: 'M76 93 L177 56 L177 150 L76 112 Z' });
  sceneAppend(room, 'path', { class: 'bed-front', d: 'M177 150 L292 108 L292 133 L177 176 Z' });
  sceneAppend(room, 'path', { class: 'bed-frame', d: 'M76 93 L177 56 L292 98 L177 139 Z' });
  sceneAppend(room, 'path', { class: 'bed-cover', d: 'M82 94 L177 60 L282 99 L186 134 Z' });
  sceneAppend(room, 'path', { class: 'bed-throw', d: 'M186 101 L282 99 L282 113 L186 148 Z' });
  sceneAppend(room, 'path', { class: 'bed-folds', d: 'M178 64 L176 124 M192 69 L190 119 M204 74 L202 115' });
  sceneAppend(room, 'path', { class: 'bed-pillow', d: 'M91 88 L133 73 L161 83 L119 99 Z' });
  sceneAppend(room, 'path', { class: 'bed-pillow', d: 'M137 72 L169 61 L198 72 L166 84 Z' });
  sceneAppend(room, 'path', { class: 'bed-stitching', d: 'M199 136 L278 108 M196 141 L273 114' });
  sceneAppend(room, 'path', { class: 'nightstand-front', d: 'M335 112 L369 124 L369 148 L335 136 Z' });
  sceneAppend(room, 'path', { class: 'nightstand-side', d: 'M369 124 L411 109 L411 134 L369 148 Z' });
  sceneAppend(room, 'path', { class: 'nightstand-top', d: 'M335 112 L377 97 L411 109 L369 124 Z' });
  sceneAppend(room, 'path', { class: 'nightstand-drawer', d: 'M343 119 L361 126 L361 132 L343 126 Z' });
  sceneAppend(room, 'circle', { class: 'nightstand-knob', cx: 354, cy: 127, r: 1.5 });
  addLamp(room, 'bedside', 378, 95, state);
  addCeilingLight(room, 'ceiling-bedroom', 275, 11, state);
  if (occupied) addOccupant(room, 318, 151);
}

function addKitchenFurniture(room, state) {
  sceneAppend(room, 'ellipse', { class: 'furniture-shadow', cx: 192, cy: 157, rx: 140, ry: 21 });
  sceneAppend(room, 'path', { class: 'backsplash', d: 'M57 53 L143 22 L228 53 L228 69 L143 38 L57 69 Z' });
  sceneAppend(room, 'path', { class: 'backsplash-grout', d: 'M86 59 L86 41 M114 48 L114 31 M143 54 V36 M172 47 V29 M200 58 V42 M67 58 L152 28 M96 68 L181 38 M126 78 L211 48' });
  sceneAppend(room, 'path', { class: 'counter-front', d: 'M48 91 L141 125 L141 155 L48 120 Z' });
  sceneAppend(room, 'path', { class: 'counter-side', d: 'M141 125 L237 90 L237 120 L141 155 Z' });
  sceneAppend(room, 'path', { class: 'counter-top', d: 'M48 91 L144 56 L237 90 L141 125 Z' });
  sceneAppend(room, 'path', { class: 'cabinet-door', d: 'M57 111 L92 124 L92 145 L57 132 Z M101 127 L133 139 L133 151 L101 139 Z' });
  sceneAppend(room, 'path', { class: 'cabinet-side', d: 'M149 122 L226 94 L226 119 L149 148 Z' });
  sceneAppend(room, 'path', { class: 'sink-rim', d: 'M73 85 L111 71 L133 79 L95 93 Z' });
  sceneAppend(room, 'path', { class: 'sink-basin', d: 'M80 85 L111 74 L126 80 L96 91 Z' });
  sceneAppend(room, 'path', { class: 'sink-faucet', d: 'M105 74 V65 Q105 60 111 60 H115 V69' });
  sceneAppend(room, 'circle', { class: 'sink-handle', cx: 118, cy: 69, r: 1.4 });
  sceneAppend(room, 'path', { class: 'stove-top', d: 'M161 77 L204 61 L225 69 L182 85 Z' });
  sceneAppend(room, 'circle', { class: 'stove-burner', cx: 183, cy: 72, r: 4 });
  sceneAppend(room, 'circle', { class: 'stove-burner', cx: 204, cy: 68, r: 4 });
  sceneAppend(room, 'path', { class: 'island-front', d: 'M259 117 L330 143 L330 164 L259 138 Z' });
  sceneAppend(room, 'path', { class: 'island-side', d: 'M330 143 L420 110 L420 132 L330 164 Z' });
  sceneAppend(room, 'path', { class: 'island-top', d: 'M259 117 L348 84 L420 110 L330 143 Z' });
  sceneAppend(room, 'path', { class: 'island-detail', d: 'M276 122 L315 137 M367 110 L402 118' });
  addCeilingLight(room, 'kitchen', 272, 11, state);
}

function renderHomeScene(family, step, mode) {
  const task = taskData[family];
  const steps = mode === 'SS' ? task.seekSteps : task.steps;
  const currentStep = steps[step];
  const state = sceneState(family, step, mode);
  const focusRoom = { DGC: 'workspace', AIR: 'living', FAR: 'kitchen', DCR: 'bedroom', PMU: 'living' }[family];
  const pairedRooms = { MSC: ['living', 'bedroom'], REQ: ['living', 'kitchen'] }[family];
  const compactViewport = window.matchMedia('(max-width: 600px)').matches;
  const compactPair = Boolean(pairedRooms && compactViewport);
  const viewBox = focusRoom
    ? '170 30 950 580'
    : compactPair ? '0 0 1000 900' : '0 0 1200 370';
  const viewHeight = compactPair ? 900 : focusRoom ? 620 : 370;
  const svg = svgElement('svg', {
    class: `home-scene family-${family.toLowerCase()}${focusRoom ? ' is-focused' : ''}${pairedRooms ? ' is-paired' : ''}${compactViewport ? ' is-mobile-layout' : ''}${mode === 'SS' ? ` is-seeking${step === 0 ? ' pre-query' : ''}` : ''}`,
    viewBox,
    role: 'img',
    'aria-label': `${task.title}, ${mode === 'SG' ? 'state supplied' : step === 0 ? 'state not queried' : 'tool state returned'}: ${currentStep[1].toLowerCase()}`
  });
  sceneAppend(svg, 'title', {}, `${task.title} walkthrough`);
  sceneAppend(svg, 'desc', {}, 'A perspective cutaway home scene shows room occupancy, lights, furniture, and the device changes relevant to this task.');
  const backdrop = sceneAppend(svg, 'defs');
  const backgroundGlow = sceneAppend(backdrop, 'radialGradient', { id: 'home-glow', cx: '80%', cy: '18%', r: '80%' });
  sceneAppend(backgroundGlow, 'stop', { offset: '0%', 'stop-color': '#403343', 'stop-opacity': '.38' });
  sceneAppend(backgroundGlow, 'stop', { offset: '100%', 'stop-color': '#111014', 'stop-opacity': '0' });
  const wallGradient = sceneAppend(backdrop, 'linearGradient', { id: 'wall-soft', x1: '0', x2: '1', y1: '0', y2: '1' });
  sceneAppend(wallGradient, 'stop', { offset: '0%', 'stop-color': '#302b2d' });
  sceneAppend(wallGradient, 'stop', { offset: '100%', 'stop-color': '#1b191b' });
  const sideWallGradient = sceneAppend(backdrop, 'linearGradient', { id: 'wall-deep', x1: '0', x2: '1', y1: '0', y2: '1' });
  sceneAppend(sideWallGradient, 'stop', { offset: '0%', 'stop-color': '#211f22' });
  sceneAppend(sideWallGradient, 'stop', { offset: '100%', 'stop-color': '#151416' });
  const floorGradient = sceneAppend(backdrop, 'linearGradient', { id: 'floor-wood', x1: '0', x2: '0', y1: '0', y2: '1' });
  sceneAppend(floorGradient, 'stop', { offset: '0%', 'stop-color': '#4a4140' });
  sceneAppend(floorGradient, 'stop', { offset: '100%', 'stop-color': '#282426' });
  const windowGradient = sceneAppend(backdrop, 'linearGradient', { id: 'window-glass', x1: '0', x2: '0', y1: '0', y2: '1' });
  sceneAppend(windowGradient, 'stop', { offset: '0%', 'stop-color': '#766f79' });
  sceneAppend(windowGradient, 'stop', { offset: '58%', 'stop-color': '#a58c7d' });
  sceneAppend(windowGradient, 'stop', { offset: '100%', 'stop-color': '#665b5d' });
  const doorGradient = sceneAppend(backdrop, 'linearGradient', { id: 'door-wood', x1: '0', x2: '1', y1: '0', y2: '1' });
  sceneAppend(doorGradient, 'stop', { offset: '0%', 'stop-color': '#725a4b' });
  sceneAppend(doorGradient, 'stop', { offset: '100%', 'stop-color': '#3a302e' });
  const artGradient = sceneAppend(backdrop, 'linearGradient', { id: 'art-print', x1: '0', x2: '1', y1: '0', y2: '1' });
  sceneAppend(artGradient, 'stop', { offset: '0%', 'stop-color': '#927b70' });
  sceneAppend(artGradient, 'stop', { offset: '100%', 'stop-color': '#554b57' });
  const fabricGradient = sceneAppend(backdrop, 'linearGradient', { id: 'sofa-fabric', x1: '0', x2: '0', y1: '0', y2: '1' });
  sceneAppend(fabricGradient, 'stop', { offset: '0%', 'stop-color': '#77717a' });
  sceneAppend(fabricGradient, 'stop', { offset: '100%', 'stop-color': '#39363d' });
  const bedGradient = sceneAppend(backdrop, 'linearGradient', { id: 'bed-cover', x1: '0', x2: '1', y1: '0', y2: '1' });
  sceneAppend(bedGradient, 'stop', { offset: '0%', 'stop-color': '#8b8190' });
  sceneAppend(bedGradient, 'stop', { offset: '100%', 'stop-color': '#514c5a' });
  const tileGradient = sceneAppend(backdrop, 'linearGradient', { id: 'tile-surface', x1: '0', x2: '0', y1: '0', y2: '1' });
  sceneAppend(tileGradient, 'stop', { offset: '0%', 'stop-color': '#716861' });
  sceneAppend(tileGradient, 'stop', { offset: '100%', 'stop-color': '#514b49' });
  const woodGradient = sceneAppend(backdrop, 'linearGradient', { id: 'wood-surface', x1: '0', x2: '1', y1: '0', y2: '1' });
  sceneAppend(woodGradient, 'stop', { offset: '0%', 'stop-color': '#876e5c' });
  sceneAppend(woodGradient, 'stop', { offset: '100%', 'stop-color': '#493a33' });
  const screenGradient = sceneAppend(backdrop, 'linearGradient', { id: 'screen-light', x1: '0', x2: '1', y1: '0', y2: '1' });
  sceneAppend(screenGradient, 'stop', { offset: '0%', 'stop-color': '#5d7887' });
  sceneAppend(screenGradient, 'stop', { offset: '100%', 'stop-color': '#1c2630' });
  const warmGradient = sceneAppend(backdrop, 'radialGradient', { id: 'lamp-warmth' });
  sceneAppend(warmGradient, 'stop', { offset: '0%', 'stop-color': '#ffd995', 'stop-opacity': '.78' });
  sceneAppend(warmGradient, 'stop', { offset: '100%', 'stop-color': '#ffb866', 'stop-opacity': '0' });
  const shadow = sceneAppend(backdrop, 'filter', { id: 'soft-shadow', x: '-40%', y: '-40%', width: '180%', height: '190%' });
  sceneAppend(shadow, 'feGaussianBlur', { in: 'SourceAlpha', stdDeviation: 3, result: 'blur' });
  sceneAppend(shadow, 'feOffset', { in: 'blur', dx: 1, dy: 4, result: 'offset' });
  const shadowMerge = sceneAppend(shadow, 'feMerge');
  sceneAppend(shadowMerge, 'feMergeNode', { in: 'offset' });
  sceneAppend(shadowMerge, 'feMergeNode', { in: 'SourceGraphic' });

  sceneAppend(svg, 'rect', { class: 'scene-backdrop', width: 1200, height: viewHeight, rx: 14 });
  sceneAppend(svg, 'rect', { class: 'scene-backdrop-glow', width: 1200, height: viewHeight, rx: 14 });

  const roomSpecs = {
    workspace: { label: 'WORKSPACE', code: '01', x: 42, y: 100 },
    living: { label: 'LIVING ROOM', code: '02', x: 654, y: 100 },
    bedroom: { label: 'BEDROOM', code: '03', x: 42, y: 330 },
    kitchen: { label: 'KITCHEN', code: '04', x: 654, y: 330 }
  };
  const roomIds = focusRoom ? [focusRoom] : pairedRooms || Object.keys(roomSpecs);
  const rooms = {};
  roomIds.forEach((id) => {
    let position = roomSpecs[id];
    if (focusRoom) position = { x: 155, y: 148, scale: 1.95 };
    else if (pairedRooms && compactPair) {
      position = { x: 100, y: id === pairedRooms[0] ? 80 : 520, scale: 1.6 };
    } else if (pairedRooms) {
      position = { x: id === pairedRooms[0] ? 5 : 605, y: 68, scale: 1.25 };
    }
    rooms[id] = addRoomFrame(svg, { id, ...roomSpecs[id], ...position });
  });

  if (rooms.workspace) addWorkspaceFurniture(rooms.workspace, state);
  if (rooms.living) addLivingFurniture(rooms.living, state, family === 'MSC' && (mode === 'SG' || step > 0));
  if (rooms.bedroom) addBedroomFurniture(rooms.bedroom, state, family === 'MSC' && (mode === 'SG' || step > 0));
  if (rooms.kitchen) addKitchenFurniture(rooms.kitchen, state);

  const badge = (eyebrow, label, kind = '') => addSceneBadge(svg, 870, 8, eyebrow, label, kind);
  if (family === 'AIR' && step === 1) badge('CLARIFICATION', 'Which room should I adjust?', 'question');
  if (family === 'AIR' && step === 2) badge('WAITING FOR DETAILS', 'No device changed', 'question');
  if (family === 'FAR' && step === 1) badge('RULE SAVED', 'Mon–Fri · 07:00', 'automation');
  if (family === 'FAR' && step === 2) badge('FUTURE ACTION', 'Kitchen light on', 'automation');
  if (family === 'DCR' && step === 1) badge('LATEST CORRECTION', 'Bedroom lamp', 'correction');
  if (family === 'DCR' && step === 2) badge('ACTION EXECUTED ONCE', 'Bedroom lamp on', 'correction');
  if (family === 'PMU' && (mode === 'SG' || step > 0) && step < 2) badge('EVENING PREFERENCE', 'Warm white · 40%', 'memory');
  if (family === 'PMU' && step === 2) badge('PREFERENCE APPLIED', 'Warm white · 40%', 'memory');
  if (family === 'REQ' && step > 0) badge('READ-ONLY RESULT', '2 lights are on', 'answer');

  sceneItems.replaceChildren(svg);
}

const taskRows = document.querySelectorAll('.task-row');
const taskDemo = document.querySelector('.task-demo');
const taskTitle = document.getElementById('task-demo-title');
const taskPrompt = document.getElementById('task-prompt');
const walkSteps = document.getElementById('walk-steps');
const sceneItems = document.getElementById('scene-items');
const sceneMode = document.getElementById('scene-mode');
const walkCounter = document.getElementById('walk-counter');
const walkCopy = document.getElementById('walk-step-copy');
const walkToggle = document.getElementById('walk-toggle');
const walkPrevious = document.getElementById('walk-prev');
const walkNext = document.getElementById('walk-next');
const interfaceButtons = document.querySelectorAll('.interface-button');
let activeFamily = 'DGC';
let activeStep = 0;
let activeInterface = 'SG';
let walkTimer;
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
const mobileScenePreference = window.matchMedia('(max-width: 600px)');
let walkPaused = motionPreference.matches;
const motionPreferenceListener = (event) => {
  walkPaused = event.matches;
  syncWalkToggle();
  updateTaskStep();
  restartWalk();
};

function currentTaskSteps() {
  const task = taskData[activeFamily];
  return activeInterface === 'SS' ? task.seekSteps : task.steps;
}

function syncWalkToggle() {
  walkToggle.textContent = walkPaused ? 'Play' : 'Pause';
  walkToggle.setAttribute('aria-label', `${walkPaused ? 'Play' : 'Pause'} walkthrough`);
  walkToggle.setAttribute('aria-pressed', String(!walkPaused));
}

function updatePlaybackControls() {
  walkPrevious.disabled = activeStep === 0;
  walkNext.disabled = activeStep === currentTaskSteps().length - 1;
}

function renderTask(family, resetStep = true) {
  const task = taskData[family];
  activeFamily = family;
  if (resetStep) activeStep = 0;
  taskRows.forEach((row) => {
    const selected = row.dataset.family === family;
    row.classList.toggle('selected', selected);
    row.setAttribute('aria-pressed', String(selected));
  });
  taskDemo.classList.remove('switching');
  void taskDemo.offsetWidth;
  taskDemo.classList.add('switching');
  taskTitle.textContent = task.title;
  taskPrompt.textContent = task.prompt;
  syncWalkToggle();
  walkSteps.replaceChildren();
  currentTaskSteps().forEach((step, index) => {
    const marker = document.createElement('button');
    marker.className = 'walk-step';
    marker.type = 'button';
    marker.dataset.step = index;
    const markerNumber = document.createElement('span');
    markerNumber.className = 'walk-step-number';
    markerNumber.textContent = String(index + 1).padStart(2, '0');
    const markerLabel = document.createElement('span');
    markerLabel.className = 'walk-step-label';
    markerLabel.textContent = step[1];
    marker.append(markerNumber, markerLabel);
    marker.title = step[1];
    marker.setAttribute('aria-label', `Go to step ${index + 1}: ${step[1]}`);
    marker.addEventListener('click', () => setTaskStep(index));
    walkSteps.appendChild(marker);
  });
  updateTaskStep();
  restartWalk();
}

function updateTaskStep() {
  const task = taskData[activeFamily];
  const steps = currentTaskSteps();
  const step = steps[activeStep];
  walkSteps.dataset.paused = String(walkPaused);
  walkSteps.querySelectorAll('.walk-step').forEach((marker, index) => {
    marker.classList.toggle('done', index < activeStep);
    marker.classList.toggle('current', index === activeStep);
    if (index === activeStep) marker.setAttribute('aria-current', 'step');
    else marker.removeAttribute('aria-current');
  });
  sceneMode.textContent = activeInterface === 'SG'
    ? 'Context supplied'
    : activeStep === 0 ? 'State not queried' : 'State queried';
  renderHomeScene(activeFamily, activeStep, activeInterface);
  walkCounter.textContent = `Step ${activeStep + 1} of ${steps.length}`;
  walkCopy.textContent = step[2];
  updatePlaybackControls();
}

function setTaskStep(step) {
  const lastStep = currentTaskSteps().length - 1;
  activeStep = Math.max(0, Math.min(lastStep, step));
  updateTaskStep();
  restartWalk();
}

function restartWalk() {
  window.clearInterval(walkTimer);
  if (walkPaused) return;
  walkTimer = window.setInterval(() => {
    activeStep = (activeStep + 1) % currentTaskSteps().length;
    updateTaskStep();
  }, 5200);
}

taskRows.forEach((row) => {
  row.addEventListener('click', () => renderTask(row.dataset.family));
});
walkPrevious.addEventListener('click', () => setTaskStep(activeStep - 1));
walkNext.addEventListener('click', () => setTaskStep(activeStep + 1));
walkToggle.addEventListener('click', () => {
  walkPaused = !walkPaused;
  syncWalkToggle();
  updateTaskStep();
  restartWalk();
});

if (motionPreference.addEventListener) motionPreference.addEventListener('change', motionPreferenceListener);
else motionPreference.addListener(motionPreferenceListener);
const mobileSceneListener = () => renderHomeScene(activeFamily, activeStep, activeInterface);
if (mobileScenePreference.addEventListener) mobileScenePreference.addEventListener('change', mobileSceneListener);
else mobileScenePreference.addListener(mobileSceneListener);

function setInterface(mode) {
  activeInterface = mode;
  activeStep = 0;
  interfaceButtons.forEach((button) => {
    const selected = button.dataset.interface === mode;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  renderTask(activeFamily, false);
}

interfaceButtons.forEach((button) => {
  button.addEventListener('click', () => setInterface(button.dataset.interface));
});

landscapeMetricButtons.forEach((button) => {
  button.addEventListener('click', () => {
    landscapeMetric = button.dataset.landscapeMetric;
    landscapeMetricButtons.forEach((item) => item.classList.toggle('active', item === button));
    renderLandscape(loadedModels, landscapeMetric);
  });
});

gapFilterButtons.forEach((button) => {
  button.addEventListener('click', () => {
    gapFilter = button.dataset.gapFilter;
    gapFilterButtons.forEach((item) => item.classList.toggle('active', item === button));
    renderGapChart(loadedModels, gapFilter);
  });
});

document.querySelectorAll('.band-card').forEach((card) => {
  card.addEventListener('click', () => {
    const filter = [...filterButtons].find((button) => button.dataset.filter === card.dataset.bandFilter);
    if (filter) filter.click();
  });
});

setInterface('SG');
renderTask('DGC');
