const tableBody = document.getElementById('model-rows');
const filterButtons = document.querySelectorAll('.filter');
const landscapeChart = document.getElementById('landscape-chart');
const landscapeTooltip = document.getElementById('landscape-tooltip');
const landscapeMetricButtons = document.querySelectorAll('.landscape-metric');
const languageChart = document.getElementById('language-chart');
const languageMetricButtons = document.querySelectorAll('.analysis-toggle');
const languageCaption = document.getElementById('language-caption');
const gapChart = document.getElementById('gap-chart');
const gapTooltip = document.getElementById('gap-tooltip');
const gapFilterButtons = document.querySelectorAll('.gap-filter');
let loadedModels = [];
let loadedBandSummary = [];
let landscapeMetric = 'sg';
let languageMetric = 'sg';
let gapFilter = 'all';

function percent(value) {
  return `${Number(value).toFixed(1)}%`;
}

function modelRow(model, rank) {
  const row = document.createElement('tr');
  if (model.class === 'baseline') row.className = 'reference';

  const name = document.createElement('td');
  const rankLabel = document.createElement('span');
  rankLabel.className = 'rank';
  rankLabel.textContent = String(rank).padStart(2, '0');
  const modelName = document.createElement('strong');
  modelName.textContent = model.model;
  name.append(rankLabel, modelName);

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
      'data-band': model.band,
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
      const label = document.createElement('label');
      label.textContent = model.model;
      label.title = model.model;
      const bar = document.createElement('i');
      bar.style.width = `${Math.min(Number(model[metric]) / 80 * 100, 100)}%`;
      const value = document.createElement('b');
      value.textContent = percent(model[metric]);
      row.append(label, bar, value);
      referenceBars.appendChild(row);
    });
  }

  const head = document.getElementById('landscape-head');
  const copy = document.getElementById('landscape-copy');
  if (head && copy && topModel) {
    const metricName = metric === 'sg' ? 'State-Given' : 'State-Seeking';
    head.textContent = `${topModel.model} leads local ${metricName} at ${percent(topModel[metric])}.`;
    copy.textContent = `${localModels.length} local models are plotted by parameter count. The size bands make the upward trend visible while preserving each model-level result.`;
  }
}

function renderLanguageChart(summary, metric = languageMetric) {
  if (!languageChart) return;
  const width = 520;
  const height = 258;
  const plot = { left: 46, right: 18, top: 18, bottom: 38 };
  const plotWidth = width - plot.left - plot.right;
  const plotHeight = height - plot.top - plot.bottom;
  const yMax = 25;
  const y = (value) => plot.top + (1 - Math.min(Number(value) || 0, yMax) / yMax) * plotHeight;
  const groupX = [125, 260, 395];
  const languageKey = metric === 'sg' ? 'state_given_by_language' : 'state_seeking_by_language';
  const metricName = metric === 'sg' ? 'State-Given' : 'State-Seeking';
  languageChart.replaceChildren();
  languageChart.appendChild(svgElement('title', { id: 'language-title' }, 'Chinese and English success by local model size'));
  languageChart.appendChild(svgElement('desc', { id: 'language-desc' }, 'Grouped bars compare the Chinese and English tracks for each local model size band.'));
  const grid = svgElement('g');
  [0, 5, 10, 15, 20, 25].forEach((tick) => {
    const tickY = y(tick);
    grid.appendChild(svgElement('line', { class: 'analysis-gridline', x1: plot.left, x2: width - plot.right, y1: tickY, y2: tickY }));
    grid.appendChild(svgElement('text', { class: 'analysis-axis', x: plot.left - 8, y: tickY + 3, 'text-anchor': 'end' }, `${tick}%`));
  });
  languageChart.appendChild(grid);
  const bars = svgElement('g');
  summary.forEach((band, index) => {
    const values = band[languageKey] || {};
    const chinese = Number(values.Chinese) || 0;
    const english = Number(values.English) || 0;
    const baseY = y(0);
    const chineseX = groupX[index] - 20;
    const englishX = groupX[index] + 4;
    const chineseBar = svgElement('rect', { class: 'language-bar chinese', x: chineseX, y: y(chinese), width: 18, height: Math.max(baseY - y(chinese), chinese ? 1 : 0), rx: 2, tabindex: '0', role: 'img', 'aria-label': `${band.label} Chinese ${percent(chinese)}` });
    const englishBar = svgElement('rect', { class: 'language-bar english', x: englishX, y: y(english), width: 18, height: Math.max(baseY - y(english), english ? 1 : 0), rx: 2, tabindex: '0', role: 'img', 'aria-label': `${band.label} English ${percent(english)}` });
    bars.append(chineseBar, englishBar);
    if (chinese > 0) bars.appendChild(svgElement('text', { class: 'analysis-value', x: chineseX + 9, y: y(chinese) - 6, 'text-anchor': 'middle' }, chinese.toFixed(1)));
    if (english > 0) bars.appendChild(svgElement('text', { class: 'analysis-value', x: englishX + 9, y: y(english) - 6, 'text-anchor': 'middle' }, english.toFixed(1)));
    bars.appendChild(svgElement('text', { class: 'analysis-axis-label', x: groupX[index], y: height - 16, 'text-anchor': 'middle' }, band.label));
  });
  languageChart.appendChild(bars);
  languageChart.appendChild(svgElement('text', { class: 'analysis-axis-label', x: plot.left, y: 10 }, `${metricName} strict success`));
  if (languageCaption) languageCaption.textContent = `Chinese and English means are shown separately for ${metricName}.`;
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

fetch('data/results.json')
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
    cell.textContent = 'Results could not be loaded. Open data/results.json to inspect the release.';
    row.appendChild(cell);
    tableBody.replaceChildren(row);
    console.error(error);
  });

const taskData = {
  DGC: {
    title: 'Device Grounding and Control',
    prompt: 'Turn on the desk lamp beside the monitor.',
    caption: 'ROOM / DEVICE STATE',
    success: 'Identify the intended device, apply one valid control, and leave unrelated devices unchanged.',
    steps: [
      ['01', 'Ground the reference', 'Resolve “desk lamp” to the correct device among similar candidates.'],
      ['02', 'Apply one control', 'Execute the requested service with valid parameters.'],
      ['03', 'Preserve other state', 'The target changes; the ceiling lamp and fan remain unchanged.']
    ],
    scenes: [
      '<div class="scene-device"><span>◌</span><small>DESK LAMP</small></div><div class="scene-device"><span>◉</span><small>CEILING LAMP</small></div><div class="scene-device"><span>⌁</span><small>FAN</small></div>',
      '<div class="scene-device target"><span class="pulse"></span><span>◌</span><small>DESK LAMP / ON</small></div><div class="scene-device"><span>◉</span><small>CEILING LAMP</small></div><div class="scene-device"><span>⌁</span><small>FAN</small></div>',
      '<div class="scene-device changed"><span>◌</span><small>DESK LAMP / ON</small></div><div class="scene-device muted"><span>◉</span><small>CEILING LAMP</small></div><div class="scene-device muted"><span>⌁</span><small>FAN</small></div>'
    ]
  },
  MSC: {
    title: 'Multi-device Selection and Control',
    prompt: 'Turn on the lights in occupied rooms, but leave the fans alone.',
    caption: 'MULTI-DEVICE STATE',
    success: 'Select the complete requested set, control every target, and avoid adding non-target devices.',
    steps: [
      ['01', 'Select the target set', 'Use the room and state rules to identify all occupied-room lights.'],
      ['02', 'Coordinate actions', 'Apply the same intent across the selected devices.'],
      ['03', 'Exclude non-targets', 'Fans and lights in empty rooms remain unchanged.']
    ],
    scenes: [
      '<div class="scene-device"><span>◉</span><small>LIVING / ON</small></div><div class="scene-device"><span>◌</span><small>BEDROOM / OFF</small></div><div class="scene-device muted"><span>⌁</span><small>FAN / OFF</small></div>',
      '<div class="scene-device target"><span class="pulse"></span><span>◉</span><small>LIVING / ON</small></div><div class="scene-device target"><span class="pulse"></span><span>◌</span><small>BEDROOM / ON</small></div><div class="scene-device muted"><span>⌁</span><small>FAN / OFF</small></div>',
      '<div class="scene-device changed"><span>◉</span><small>LIVING / ON</small></div><div class="scene-device changed"><span>◌</span><small>BEDROOM / ON</small></div><div class="scene-device muted"><span>⌁</span><small>FAN / OFF</small></div>'
    ]
  },
  AIR: {
    title: 'Ambiguity and Intent Resolution',
    prompt: 'Make it comfortable in here.',
    caption: 'REQUEST / EVIDENCE',
    success: 'Recognize when the available evidence is insufficient, ask for the missing slot, and do not act on a guess.',
    steps: [
      ['01', 'Check the evidence', 'The request does not identify a room or a specific comfort action.'],
      ['02', 'Ask one useful question', 'Request the missing information that makes the next action executable.'],
      ['03', 'Do not act yet', 'No device changes before the ambiguity is resolved.']
    ],
    scenes: [
      '<div class="scene-device dialogue"><span>“Make it comfortable in here.”</span><small>UNDER-SPECIFIED REQUEST</small></div>',
      '<div class="scene-device target"><span class="pulse"></span><span>Which room should I adjust?</span><small>CLARIFICATION</small></div>',
      '<div class="scene-device muted"><span>◌</span><small>NO ACTION</small></div><div class="scene-device muted"><span>◉</span><small>NO ACTION</small></div><div class="scene-device muted"><span>⌁</span><small>NO ACTION</small></div>'
    ]
  },
  FAR: {
    title: 'Future Automation Registration',
    prompt: 'Every weekday at 7:00, turn on the kitchen light.',
    caption: 'CURRENT STATE / FUTURE RULE',
    success: 'Register the requested time rule while leaving the current device state unchanged.',
    steps: [
      ['01', 'Parse the condition', 'Separate the future schedule from the action it will trigger.'],
      ['02', 'Register the rule', 'Store the weekday and time condition with the kitchen-light action.'],
      ['03', 'Leave now unchanged', 'The kitchen light does not turn on during registration.']
    ],
    scenes: [
      '<div class="scene-device"><span>◌</span><small>KITCHEN / OFF</small></div><div class="scene-device"><span>◷</span><small>NOW</small></div>',
      '<div class="scene-device rule"><span>MON–FRI · 07:00 → LIGHT ON</span><small>REGISTERED RULE</small></div>',
      '<div class="scene-device muted"><span>◌</span><small>KITCHEN / STILL OFF</small></div><div class="scene-device changed"><span>✓</span><small>RULE SAVED</small></div>'
    ]
  },
  DCR: {
    title: 'Dialogue-context Resolution',
    prompt: 'User: Turn on the lamp.  User: Actually, the bedroom one.',
    caption: 'DIALOGUE / CURRENT TURN',
    success: 'Use prior dialogue to resolve the correction, execute only the current request, and avoid replaying history.',
    steps: [
      ['01', 'Read the dialogue', 'The first turn names a lamp; the second turn corrects its location.'],
      ['02', 'Resolve the correction', 'Use “actually” and “bedroom” to update the current target.'],
      ['03', 'Execute once', 'Control the bedroom lamp without repeating an earlier action.']
    ],
    scenes: [
      '<div class="scene-device dialogue"><span>“Actually, the bedroom one.”</span><small>CURRENT TURN</small></div>',
      '<div class="scene-device"><span>◌</span><small>DESK / IGNORED</small></div><div class="scene-device target"><span class="pulse"></span><span>◌</span><small>BEDROOM / TARGET</small></div>',
      '<div class="scene-device muted"><span>◌</span><small>DESK / UNCHANGED</small></div><div class="scene-device changed"><span>◌</span><small>BEDROOM / ON</small></div>'
    ]
  },
  PMU: {
    title: 'Personalized Memory Use',
    prompt: 'Set the living-room lights the way I prefer in the evening.',
    caption: 'USER / VALID PREFERENCE',
    success: 'Select the current user’s valid preference and apply it to the requested target without changing unrelated state.',
    steps: [
      ['01', 'Retrieve relevant memory', 'Find a preference that belongs to this user and context.'],
      ['02', 'Check validity', 'Ignore superseded or unrelated preferences before acting.'],
      ['03', 'Apply the preference', 'Set the living-room lights to the remembered evening level.']
    ],
    scenes: [
      '<div class="scene-device memory"><span>Evening: warm, 40%</span><small>VALID MEMORY</small></div>',
      '<div class="scene-device target"><span class="pulse"></span><span>40%</span><small>LIVING LIGHTS</small></div><div class="scene-device muted"><span>◉</span><small>OTHER ROOM</small></div>',
      '<div class="scene-device changed"><span>40%</span><small>LIVING / WARM</small></div><div class="scene-device muted"><span>◉</span><small>OTHER / SAME</small></div>'
    ]
  },
  REQ: {
    title: 'Read-only Environment Queries',
    prompt: 'How many lights are on right now?',
    caption: 'OBSERVATION / NO MUTATION',
    success: 'Inspect permitted state, return the correct structured answer, and make no device-control attempt.',
    steps: [
      ['01', 'Inspect allowed state', 'Read the current device statuses and identify lights.'],
      ['02', 'Count the matches', 'Aggregate only the devices satisfying the query.'],
      ['03', 'Return the answer', 'Report the count while preserving the environment exactly.']
    ],
    scenes: [
      '<div class="scene-device query-target"><span>◉</span><small>ON</small></div><div class="scene-device muted"><span>◌</span><small>OFF</small></div><div class="scene-device query-target"><span>◉</span><small>ON</small></div>',
      '<div class="scene-device target"><span class="pulse"></span><span>2</span><small>LIGHTS ON</small></div>',
      '<div class="scene-device answer"><span><b>2</b> lights are on.</span><small>READ-ONLY ANSWER</small></div>'
    ]
  }
};

const taskRows = document.querySelectorAll('.task-row');
const taskDemo = document.querySelector('.task-demo');
const taskTitle = document.getElementById('task-demo-title');
const taskPrompt = document.getElementById('task-prompt');
const taskSuccess = document.getElementById('task-success-copy');
const walkSteps = document.getElementById('walk-steps');
const sceneItems = document.getElementById('scene-items');
const sceneCaption = document.getElementById('scene-caption');
const walkCounter = document.getElementById('walk-counter');
const walkTitle = document.getElementById('walk-step-title');
const walkCopy = document.getElementById('walk-step-copy');
const walkToggle = document.getElementById('walk-toggle');
const processTrack = document.querySelector('.process-track');
const processNodes = document.querySelectorAll('.process-node');
const interfaceButtons = document.querySelectorAll('.interface-button');
const interfaceNote = document.getElementById('interface-note');
const taskMapNodes = document.querySelectorAll('.task-map-node');
const taskMapReadoutTitle = document.getElementById('task-map-readout-title');
const taskMapReadoutCopy = document.getElementById('task-map-readout-copy');
const taskStageMap = {
  DGC: ['resolve', 'act', 'score'],
  MSC: ['resolve', 'act', 'score'],
  AIR: ['observe', 'act', 'score'],
  FAR: ['resolve', 'act', 'score'],
  DCR: ['observe', 'resolve', 'act'],
  PMU: ['observe', 'resolve', 'act'],
  REQ: ['observe', 'resolve', 'score']
};
const interfaceCopy = {
  SG: 'State-Given supplies the relevant context before the model responds.',
  SS: 'State-Seeking begins with partial observation and adds a query-and-act loop.'
};
let activeFamily = 'DGC';
let activeStep = 0;
let walkTimer;
let walkPaused = false;

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
  taskSuccess.textContent = task.success;
  sceneCaption.textContent = task.caption;
  updateTaskMap();
  walkSteps.replaceChildren();
  task.steps.forEach((step, index) => {
    const marker = document.createElement('span');
    marker.className = 'walk-step';
    marker.dataset.step = index;
    marker.setAttribute('aria-label', `Step ${index + 1}: ${step[1]}`);
    walkSteps.appendChild(marker);
  });
  updateTaskStep();
  restartWalk();
}

function updateTaskStep() {
  const task = taskData[activeFamily];
  const step = task.steps[activeStep];
  walkSteps.querySelectorAll('.walk-step').forEach((marker, index) => {
    marker.classList.toggle('done', index < activeStep);
    marker.classList.toggle('current', index === activeStep && !walkPaused);
  });
  sceneItems.innerHTML = task.scenes[activeStep];
  walkCounter.textContent = `STEP ${step[0]} / ${task.steps.length}`;
  walkTitle.textContent = step[1];
  walkCopy.textContent = step[2];
  const rawStage = taskStageMap[activeFamily][activeStep];
  const activeStage = processTrack.dataset.interface === 'SG' && rawStage === 'observe' ? 'resolve' : rawStage;
  processNodes.forEach((node) => {
    const stage = node.dataset.stage;
    const stageIndex = ['request', 'observe', 'resolve', 'act', 'score'].indexOf(stage);
    const activeIndex = ['request', 'observe', 'resolve', 'act', 'score'].indexOf(activeStage);
    node.classList.toggle('current', stage === activeStage);
    node.classList.toggle('complete', stageIndex >= 0 && stageIndex < activeIndex);
  });
}

function restartWalk() {
  window.clearInterval(walkTimer);
  if (walkPaused) return;
  walkTimer = window.setInterval(() => {
    activeStep = (activeStep + 1) % taskData[activeFamily].steps.length;
    updateTaskStep();
  }, 3600);
}

taskRows.forEach((row) => {
  row.addEventListener('click', () => renderTask(row.dataset.family));
});
walkToggle.addEventListener('click', () => {
  walkPaused = !walkPaused;
  walkToggle.setAttribute('aria-pressed', String(!walkPaused));
  walkToggle.textContent = walkPaused ? 'Play animation' : 'Pause animation';
  updateTaskStep();
  restartWalk();
});

function setInterface(mode) {
  processTrack.dataset.interface = mode;
  interfaceButtons.forEach((button) => {
    button.classList.toggle('active', button.dataset.interface === mode);
  });
  interfaceNote.textContent = interfaceCopy[mode];
  updateTaskStep();
}

function updateTaskMap() {
  const task = taskData[activeFamily];
  taskMapNodes.forEach((node) => {
    node.classList.toggle('selected', node.dataset.family === activeFamily);
  });
  if (taskMapReadoutTitle) taskMapReadoutTitle.textContent = `${activeFamily} · ${task.title}`;
  if (taskMapReadoutCopy) taskMapReadoutCopy.textContent = task.steps[0][2];
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

languageMetricButtons.forEach((button) => {
  button.addEventListener('click', () => {
    languageMetric = button.dataset.languageMetric;
    languageMetricButtons.forEach((item) => item.classList.toggle('active', item === button));
    renderLanguageChart(loadedBandSummary, languageMetric);
  });
});

gapFilterButtons.forEach((button) => {
  button.addEventListener('click', () => {
    gapFilter = button.dataset.gapFilter;
    gapFilterButtons.forEach((item) => item.classList.toggle('active', item === button));
    renderGapChart(loadedModels, gapFilter);
  });
});

taskMapNodes.forEach((node) => {
  node.addEventListener('click', () => renderTask(node.dataset.family));
  node.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      renderTask(node.dataset.family);
    }
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
