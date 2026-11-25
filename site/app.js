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
let loadedResults = null;
let landscapeMetric = 'sg';
let gapFilter = 'all';
let locale = localStorage.getItem('edgebench-locale') === 'zh' ? 'zh' : 'en';

const copy = {
  en: {
    nav: ['Suite', 'Tasks', 'Interfaces', 'Results', 'Submit results', 'Reproduce'],
    kicker: 'BENCHMARK SUITE — MODULE 01', lead: 'The first module in an extensible benchmark suite for small local models in a simulated home.',
    viewResults: 'View results ↓', dataset: 'Explore the dataset ↗', moduleLine: 'Local models, in a living environment.',
    languages: 'LANGUAGES', setting: 'SETTING', focus: 'FOCUS', languagePair: 'English · Chinese', simulatedHome: 'Simulated home', everydayTasks: 'Everyday agent tasks',
    facts: ['bilingual cases', 'task families', 'interaction interfaces', 'local models evaluated'],
    taskLabel: '01 / Task families', taskHeading: 'Tasks for home-agent evaluation.', taskSummary: 'Explore how an agent understands a request, gathers context, and acts on a home.',
    tasks: ['Device grounding', 'Multi-device control', 'Ambiguity resolution', 'Future automation', 'Dialogue context', 'Personalized memory', 'Read-only queries'],
    capabilities: 'capabilities', casesPerFamily: 'cases per family', interfaces: 'Evaluation interfaces', interfaceHeading: 'Two ways to work with home state.',
    interfaceDesc: ['The request includes the relevant home state.', 'The model queries home state before deciding.'],
    results: 'Results', resultsHeading: 'Results by local model size.', resultsDesc: 'Strict micro-success across both language tracks; 4 server-hosted models serve as reference baselines.',
    bandMeans: 'LOCAL SIZE-BAND MEANS', landscape: 'LOCAL MODEL LANDSCAPE', languageTracks: 'Language tracks by size', gapByModel: 'Interface gap by model',
    topLocal: 'TOP LOCAL', reference: 'REFERENCE BASELINES', leaderboard: 'Local model leaderboard', all: 'All', ref: 'Reference',
    tableHeaders: ['Model', 'Size', 'Platform', 'SG', 'SS', 'Mean'], tableNote: 'Local first; server models are reference baselines.',
    submit: 'Submit results', submitHeading: 'Share a benchmark run.', submitDesc: 'Send the scorer report and summary directly to the EdgeBench review inbox.', inbox: 'RESULTS INBOX',
    emailHelp: 'Attach the scorer’s report.md and summary.json. Include the model revision, interface, language, coverage, score, dataset revision, EdgeBench commit, and AIR review status.', emailResults: 'Email results ↗', emailSubject: 'EdgeBench-Home evaluation results', emailBody: 'Hello EdgeBench team,\n\nModel and revision: \nInterface: \nLanguage: \nStrict micro-success: \nCoverage: \nDataset revision: \nEdgeBench commit: \nTask-family scores: \nAIR review status: \n\nI have attached the scorer report and summary.',
    reproduce: 'Reproduce', reproduceHeading: 'Run the benchmark.', reproduceDesc: 'Use the public runners and scorer with the EdgeBench-Home dataset.', quickStart: 'Quick start ↗',
    footerDataset: 'Dataset', license: 'Apache-2.0', you: 'You', assistant: 'Assistant',
    taskTitles: ['Device Grounding and Control', 'Multi-device Selection and Control', 'Ambiguity and Intent Resolution', 'Future Automation Registration', 'Dialogue-context Resolution', 'Personalized Memory Use', 'Read-only Environment Queries'],
    baseline: 'Baseline', sourceData: 'Source data ↗', interfaceFlow: ['Request + state', 'Model', 'Request', 'Query + state'],
    bandConfigs: ['7 configurations', '9 configurations', '2 configurations'], bandGap: 'interface gap',
    highlights: {
      label: 'EVALUATION HIGHLIGHTS', source: 'EdgeBench-Home · State-Seeking',
      heading: 'How local models perform when they gather information.',
      copy: 'Qwen3-1.7B-16K on RK3588 records 23/420 Chinese (5.5%) and 4/420 English (1.0%) under State-Seeking, totaling 27/840 (3.2%).',
      qwenLabel: 'Qwen3-1.7B-16K · RK3588 · SS', qwenCaption: 'bilingual strict success',
      serverLabel: 'Server reference · SS', serverCaption: 'FAR / REQ mean',
      note: 'Across the same State-Seeking families, all 18 tested local configurations score 0% on FAR and REQ. This floor effect does not rank local models or identify their failure causes. All 840 cases received expert review; aligned RK3588 latency, memory, and energy were not measured.'
    },
    chartLegend: ['State-Given', 'State-Seeking'], languageLegend: ['Chinese', 'English'],
    scene: { localTime: 'Local time', simulatedTime: 'Simulated time', schedule: 'Schedule', preference: 'Preference', snapshot: 'Snapshot', weekday: 'Every weekday · 7:00 AM', evening: 'Evening', now: 'Right now', occupied: 'Occupied', empty: 'Empty', available: 'Available', inspect: 'Inspect', reset: 'Reset 3D scene view', sceneLabel: 'Interactive 3D home scene. The camera follows the current task. Select a device to inspect; use arrow keys to rotate and plus or minus to zoom.' },
    steps: {
      DGC: [['Find the device', 'Locate the lamp beside the monitor.'], ['Control the target', 'Turn on only that lamp.'], ['Verify the result', 'Leave other devices unchanged.']],
      MSC: [['Check occupancy', 'Select lights in occupied rooms only.'], ['Control selected lights', 'Turn on the occupied-room light.'], ['Preserve other devices', 'Leave the empty-room light and both fans unchanged.']],
      AIR: [['Clarify intent', 'Ask which room and what should change.'], ['Apply the answer', 'Set the light to warm at 40%.'], ['Verify the result', 'Leave unrelated devices unchanged.']],
      FAR: [['Read the schedule', 'Trigger: weekdays at 7:00.'], ['Save the automation', 'Action: turn on the kitchen light.'], ['Trigger at 7:00', 'Turn on the kitchen light.']],
      DCR: [['Read the correction', 'The latest phrase replaces “the lamp”.'], ['Resolve the reference', 'Match “the one by the bed” to the bedside lamp.'], ['Act once', 'Turn on the bedside lamp.']],
      PMU: [['Retrieve the preference', 'Find the saved evening setting.'], ['Check relevance', 'Use the preference for this room and time.'], ['Apply the setting', 'Set the light to warm at 40%.']],
      REQ: [['Read current state', 'Count the lights that are on.'], ['Return the answer', 'Two lights are on.'], ['Make no changes', 'Keep every device as it is.']]
    },
    rooms: { Workspace: 'Workspace', 'Living room': 'Living room', Bedroom: 'Bedroom', Kitchen: 'Kitchen', 'Desk lamp': 'Desk lamp', 'Floor lamp': 'Floor lamp', 'Pedestal fan': 'Pedestal fan', 'Bedside lamp': 'Bedside lamp', 'Ceiling fan': 'Ceiling fan', 'Pendant light': 'Pendant light' }
  },
  zh: {
    nav: ['套件', '任务', '评测接口', '结果', '提交结果', '复现'],
    kicker: '基准评测套件 — 模块 01', lead: '面向本地小模型的可扩展基准套件首个模块，在模拟家庭环境中评测真实任务。',
    viewResults: '查看结果 ↓', dataset: '查看数据集 ↗', moduleLine: '让本地模型走进真实生活场景。',
    languages: '语言', setting: '环境', focus: '任务', languagePair: '中文 · English', simulatedHome: '模拟家庭', everydayTasks: '日常智能体任务',
    facts: ['中英双语样本', '任务类别', '交互接口', '已评测本地模型'],
    taskLabel: '01 / 任务类别', taskHeading: '家庭智能体评测任务', taskSummary: '探索智能体如何理解请求、获取上下文并操作家庭设备。',
    tasks: ['设备定位', '多设备控制', '歧义消解', '未来自动化', '对话上下文', '个性化记忆', '只读查询'],
    capabilities: '种能力', casesPerFamily: '条样本 / 类别', interfaces: '评测接口', interfaceHeading: '两种家庭状态交互方式。',
    interfaceDesc: ['请求中包含相关的家庭状态。', '模型先查询家庭状态，再作出判断。'],
    results: '评测结果', resultsHeading: '本地模型规模与表现。', resultsDesc: '统计中英文任务的严格微平均成功率；另以 4 个云端模型作为参考基线。',
    bandMeans: '按模型规模统计的平均值', landscape: '本地模型表现分布', languageTracks: '不同语言的表现', gapByModel: '各模型的接口差异',
    topLocal: '本地模型最佳', reference: '参考基线', leaderboard: '本地模型排名', all: '全部', ref: '参考模型',
    tableHeaders: ['模型', '规模', '平台', '已知状态', '查询状态', '平均'], tableNote: '优先展示本地模型；云端模型仅作参考基线。',
    submit: '提交结果', submitHeading: '分享一次评测结果。', submitDesc: '将评分报告和摘要直接发送至 EdgeBench 评审邮箱。', inbox: '结果接收邮箱',
    emailHelp: '请附上 report.md 和 summary.json，并注明模型版本、接口、语言、覆盖率、得分、数据集版本、EdgeBench commit 和 AIR 审核状态。', emailResults: '发送邮件 ↗', emailSubject: 'EdgeBench-Home 评测结果', emailBody: 'EdgeBench 团队，你们好：\n\n模型与版本：\n评测接口：\n语言：\n严格微平均成功率：\n覆盖率：\n数据集版本：\nEdgeBench commit：\n任务类别得分：\nAIR 审核状态：\n\n我已附上评分报告和摘要。',
    reproduce: '复现评测', reproduceHeading: '运行基准测试。', reproduceDesc: '使用公开运行器、评分器和 EdgeBench-Home 数据集。', quickStart: '快速开始 ↗',
    footerDataset: '数据集', license: 'Apache-2.0', you: '用户', assistant: '助手',
    taskTitles: ['设备定位与控制', '多设备选择与控制', '歧义与意图理解', '未来自动化设置', '对话上下文理解', '个性化记忆使用', '只读环境查询'],
    baseline: '基线', sourceData: '源数据 ↗', interfaceFlow: ['请求 + 状态', '模型', '请求', '查询 + 状态'],
    bandConfigs: ['7 个配置', '9 个配置', '2 个配置'], bandGap: '接口差值',
    highlights: {
      label: '评测结果', source: 'EdgeBench-Home · 查询状态',
      heading: '模型主动查询信息时的表现。',
      copy: 'Qwen3-1.7B-16K 在 RK3588 上的 State-Seeking 成功数为中文 23/420（5.5%）、英文 4/420（1.0%），双语合计 27/840（3.2%）。',
      qwenLabel: 'Qwen3-1.7B-16K · RK3588 · 查询状态', qwenCaption: '双语严格成功',
      serverLabel: 'Server 参考组 · 查询状态', serverCaption: 'FAR / REQ 平均值',
      note: '在相同的 State-Seeking 任务中，受测的 18 个本地配置在 FAR 和 REQ 上均为 0%。这是地板效应，无法区分本地模型，也不能确定失败原因。840 条案例均经过专家核查；没有测量对齐的 RK3588 延迟、内存和能耗。'
    },
    chartLegend: ['已知状态', '查询状态'], languageLegend: ['中文', 'English'],
    scene: { localTime: '本地时间', simulatedTime: '模拟时间', schedule: '日程', preference: '偏好', snapshot: '当前状态', weekday: '每个工作日 · 早上 7:00', evening: '晚间', now: '此刻', occupied: '有人', empty: '无人', available: '可用', inspect: '查看', reset: '重置 3D 视角', sceneLabel: '可交互的 3D 家庭场景。镜头会跟随当前任务。选择设备可查看状态；使用方向键旋转，使用加减键缩放。' },
    steps: {
      DGC: [['定位设备', '找到显示器旁边的台灯。'], ['控制目标设备', '只打开这盏台灯。'], ['确认结果', '其他设备保持原样。']],
      MSC: [['确认房间状态', '只选择有人房间里的灯。'], ['控制所选设备', '打开有人房间里的灯。'], ['保持其他设备不变', '空房间的灯和两台风扇都保持原样。']],
      AIR: [['确认具体需求', '询问所在房间以及要调整的内容。'], ['按答复执行', '把灯光调成 40% 暖光。'], ['确认结果', '其他无关设备保持原样。']],
      FAR: [['读取时间安排', '触发时间：每个工作日早上 7:00。'], ['保存自动化', '操作：打开厨房灯。'], ['到达 7:00', '打开厨房灯。']],
      DCR: [['理解补充说明', '最新描述替代了“那盏灯”。'], ['确定指代对象', '将“床边那盏”对应到床头灯。'], ['执行一次', '打开床头灯。']],
      PMU: [['读取已保存偏好', '找到晚间灯光设置。'], ['确认偏好适用', '结合房间和时间使用该偏好。'], ['应用设置', '把灯光调成 40% 暖光。']],
      REQ: [['读取当前状态', '统计当前已打开的灯。'], ['返回查询结果', '现在有两盏灯开着。'], ['不改变设备', '所有设备保持当前状态。']]
    },
    rooms: { Workspace: '工作区', 'Living room': '客厅', Bedroom: '卧室', Kitchen: '厨房', 'Desk lamp': '台灯', 'Floor lamp': '落地灯', 'Pedestal fan': '落地扇', 'Bedside lamp': '床头灯', 'Ceiling fan': '吊扇', 'Pendant light': '吊灯' }
  }
};

function percent(value) {
  return `${Number(value).toFixed(1)}%`;
}

function modelBrand(model) {
  const name = String(model.model || '').toLowerCase();
  if (name.startsWith('qwen')) return { key: 'qwen', label: 'Qwen', src: '../assets/model-logos/qwen-icon.png' };
  if (name.startsWith('minicpm')) return { key: 'minicpm', label: 'MiniCPM', src: '../assets/model-logos/minicpm-icon.png' };
  if (name.startsWith('deepseek')) return { key: 'deepseek', label: 'DeepSeek', src: '../assets/model-logos/deepseek-icon.png' };
  if (name.startsWith('lfm')) return { key: 'lfm', label: 'Liquid AI', src: '../assets/model-logos/lfm.png' };
  if (name.startsWith('glm')) return { key: 'glm', label: 'GLM / Z.ai', src: '../assets/model-logos/glm.png' };
  if (name.startsWith('mimo')) return { key: 'mimo', label: 'MiMo', src: '../assets/model-logos/mimo-wordmark.svg' };
  if (name.startsWith('minimax')) return { key: 'minimax', label: 'MiniMax', src: '../assets/model-logos/minimax-icon.png' };
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
    baselineLabel.textContent = copy[locale].baseline;
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

function summarizeSizeBands(models) {
  const definitions = [
    { label: '≤1B', band: '≤1B' },
    { label: '1–3B', band: '1--3B' },
    { label: '3–7B', band: '3--7B' }
  ];
  const roundOne = (value) => Math.floor((value + 1e-8) * 10 + 0.5) / 10;
  const mean = (rows, ...keys) => rows.length ? roundOne(rows.reduce((sum, row) => sum + keys.reduce((total, key) => total + row[key], 0), 0) / (rows.length * keys.length)) : 0;
  return definitions.map(({ label, band }) => {
    const rows = models.filter((model) => model.class === 'local' && model.band === band);
    return {
      label,
      models: rows.length,
      state_given_mean: mean(rows, 'chinese_sg', 'english_sg'),
      state_seeking_mean: mean(rows, 'chinese_ss', 'english_ss'),
      n_language_cases: 420,
      state_given_by_language: { Chinese: mean(rows, 'chinese_sg'), English: mean(rows, 'english_sg') },
      state_seeking_by_language: { Chinese: mean(rows, 'chinese_ss'), English: mean(rows, 'english_ss') }
    };
  });
}

function renderBandOverview(summary) {
  const plot = document.querySelector('.chart .plot');
  if (plot) {
    const grid = Array.from({ length: 6 }, () => {
      const line = document.createElement('div');
      line.className = 'gridline';
      return line;
    });
    const groups = summary.map((band) => {
      const group = document.createElement('div');
      group.className = 'group';
      [['sg', band.state_given_mean, 'State-Given'], ['ss', band.state_seeking_mean, 'State-Seeking']].forEach(([key, value, label]) => {
        const bar = document.createElement('div');
        bar.className = `bar ${key}`;
        bar.style.height = `${Math.max(0, Math.min(100, Number(value) / 25 * 100))}%`;
        bar.title = `${label} ${Number(value).toFixed(1)}%`;
        group.appendChild(bar);
      });
      const caption = document.createElement('label');
      caption.append(document.createTextNode(band.label));
      const detail = document.createElement('small');
      detail.textContent = `n=${band.models} · ${Number(band.state_given_mean).toFixed(1)} / ${Number(band.state_seeking_mean).toFixed(1)}`;
      caption.appendChild(detail);
      group.appendChild(caption);
      return group;
    });
    plot.replaceChildren(...grid, ...groups);
  }

  const bandFilterByLabel = { '≤1B': '≤1B', '1–3B': '1--3B', '3–7B': '3--7B' };
  summary.forEach((band) => {
    const card = [...document.querySelectorAll('.band-card')].find((item) => item.dataset.bandFilter === bandFilterByLabel[band.label]);
    if (!card) return;
    const sg = Number(band.state_given_mean);
    const ss = Number(band.state_seeking_mean);
    const labels = card.querySelectorAll('.band-card-head small');
    if (labels[0]) labels[0].textContent = locale === 'zh' ? `${band.models} 个配置` : `${band.models} configurations`;
    const bars = card.querySelectorAll('.band-bars em');
    if (bars[0]) bars[0].style.width = `${Math.max(0, Math.min(100, sg / 25 * 100))}%`;
    if (bars[1]) bars[1].style.width = `${Math.max(0, Math.min(100, ss / 25 * 100))}%`;
    const values = card.querySelectorAll('.band-bars strong');
    if (values[0]) values[0].textContent = `${sg.toFixed(1)}%`;
    if (values[1]) values[1].textContent = `${ss.toFixed(1)}%`;
    const gap = card.querySelector('.band-gap b');
    if (gap) gap.textContent = locale === 'zh' ? `${Math.abs(sg - ss).toFixed(1)} 个百分点` : `${Math.abs(sg - ss).toFixed(1)} pp`;
  });
}

function renderHighlights(data = loadedResults) {
  const update = data?.featured_results;
  const t = copy[locale].highlights;
  if (!update) return;
  const qwen = update.rk3588_qwen3_17_state_seeking;
  const contrast = update.state_seeking_floor_contrast;
  const text = (selector, value) => { const node = document.querySelector(selector); if (node) node.textContent = value; };
  text('#result-highlight-label', t.label);
  text('#result-highlight-source', t.source);
  text('#result-highlight-title', t.heading);
  text('#result-highlight-copy', t.copy);
  text('#result-qwen-label', t.qwenLabel);
  text('#result-qwen-value', `${qwen.bilingual.successes} / ${qwen.bilingual.cases}`);
  text('#result-qwen-caption', t.qwenCaption);
  text('#result-server-label', t.serverLabel);
  text('#result-server-value', `${Number(contrast.server_far_mean).toFixed(1)}% / ${Number(contrast.server_req_mean).toFixed(1)}%`);
  text('#result-server-caption', t.serverCaption);
  text('#result-highlight-note', t.note);
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

function applyLocale(nextLocale) {
  locale = nextLocale === 'zh' ? 'zh' : 'en';
  localStorage.setItem('edgebench-locale', locale);
  const t = copy[locale];
  document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en';
  const setText = (selector, value) => { const node = document.querySelector(selector); if (node) node.textContent = value; };
  document.querySelectorAll('.topbar nav [data-nav]').forEach((node, index) => { node.textContent = t.nav[index]; });
  const toggle = document.querySelector('.language-toggle');
  if (toggle) { toggle.textContent = locale === 'zh' ? 'English' : '中文'; toggle.setAttribute('aria-pressed', String(locale === 'zh')); toggle.setAttribute('aria-label', locale === 'zh' ? '切换到 English' : 'Switch language to Chinese'); }
  setText('.intro-kicker', t.kicker);
  setText('.intro .lead', t.lead);
  setText('.intro .button', t.viewResults);
  setText('.intro-secondary', t.dataset);
  setText('.intro-register > p', t.moduleLine);
  document.querySelectorAll('.intro-register dt').forEach((node, i) => { node.textContent = [t.languages, t.setting, t.focus][i]; });
  document.querySelectorAll('.intro-register dd').forEach((node, i) => { if (i === 0) node.textContent = t.languagePair; if (i === 1) node.textContent = t.simulatedHome; if (i === 2) node.textContent = t.everydayTasks; });
  document.querySelectorAll('.facts span').forEach((node, i) => { node.textContent = t.facts[i]; });
  setText('.tasks-heading .section-label', t.taskLabel);
  setText('.tasks-heading h2', t.taskHeading);
  setText('.tasks-summary p', t.taskSummary);
  document.querySelectorAll('.task-row .task-name').forEach((node, i) => { node.textContent = t.tasks[i]; });
  const summary = document.querySelector('.tasks-summary > span');
  if (summary) summary.innerHTML = `<b>7</b> ${t.capabilities} <i aria-hidden="true"></i> <b>60</b> ${t.casesPerFamily}`;
  setText('.interfaces > .section-label', t.interfaces);
  setText('.interfaces-intro h2', t.interfaceHeading);
  document.querySelectorAll('.interface-card p').forEach((node, i) => { node.textContent = t.interfaceDesc[i]; });
  setText('.results > .section-label', t.results);
  setText('.results .section-head h2', t.resultsHeading);
  setText('.results .section-head p', t.resultsDesc);
  setText('.trend-panel .panel-top > span:first-child', t.bandMeans);
  setText('.model-landscape .panel-top > span:first-child', t.landscape);
  setText('.analysis-panel .panel-top > span:first-child', t.languageTracks);
  setText('.gap-panel .panel-top > span:first-child', t.gapByModel);
  setText('.local-leader > span', t.topLocal);
  setText('.reference-mini > span', t.reference);
  setText('.table-head > span:first-child', t.leaderboard);
  document.querySelectorAll('.results-table thead th').forEach((node, i) => { node.textContent = t.tableHeaders[i]; });
  document.querySelectorAll('.filter').forEach((node, i) => { if (i === 0) node.textContent = t.all; if (node.dataset.filter === 'Server') node.textContent = t.ref; });
  document.querySelectorAll('.landscape-metric').forEach((node) => { node.textContent = node.dataset.landscapeMetric === 'sg' ? (locale === 'zh' ? '已知状态' : 'State-Given') : (locale === 'zh' ? '查询状态' : 'State-Seeking'); });
  document.querySelectorAll('.gap-filter').forEach((node) => { if (node.dataset.gapFilter === 'all') node.textContent = locale === 'zh' ? '全部本地' : 'All local'; });
  const tableNote = document.querySelector('.table-note');
  if (tableNote) {
    tableNote.firstChild.textContent = `${t.tableNote} `;
    const sourceLink = tableNote.querySelector('a');
    if (sourceLink) sourceLink.textContent = t.sourceData;
  }
  document.querySelectorAll('.interface-flow span').forEach((node, i) => { node.textContent = t.interfaceFlow[i]; });
  document.querySelectorAll('.results-overview .legend').forEach((node) => { [...node.childNodes].filter((child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim()).forEach((child, i) => { child.textContent = ` ${t.chartLegend[i]} `; }); });
  const languageLegend = document.querySelector('.analysis-panel:not(.gap-panel) .analysis-legend');
  if (languageLegend) languageLegend.childNodes.forEach((child) => { if (child.nodeType === Node.TEXT_NODE && child.textContent.trim()) child.textContent = ` ${t.languageLegend[child.textContent.includes('English') ? 1 : 0]} `; });
  document.querySelectorAll('.band-card-head small').forEach((node, i) => { node.textContent = t.bandConfigs[i]; });
  document.querySelectorAll('.band-gap').forEach((node) => { const value = node.querySelector('b'); node.firstChild.textContent = `${t.bandGap} `; if (value) value.textContent = `${value.textContent.replace(' pp', ' 个百分点').replace(' 个百分点', locale === 'en' ? ' pp' : ' 个百分点')}`; });
  document.querySelectorAll('.band-card').forEach((node) => { node.setAttribute('aria-label', `${node.dataset.bandFilter}, ${t.bandConfigs[[...document.querySelectorAll('.band-card')].indexOf(node)]}`); });
  document.querySelectorAll('.band-bars > span').forEach((row, i) => { const label = row.querySelector('i'); if (label) label.textContent = locale === 'zh' ? (i % 2 === 0 ? '已知' : '查询') : (i % 2 === 0 ? 'SG' : 'SS'); });
  document.querySelectorAll('.gap-panel .analysis-legend').forEach((node) => { [...node.childNodes].filter((child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim()).forEach((child, i) => { child.textContent = ` ${t.chartLegend[i]} `; }); });
  document.querySelector('.trend-panel .legend')?.setAttribute('aria-label', t.chartLegend.join(', '));
  document.querySelector('.analysis-panel:not(.gap-panel) .analysis-legend')?.setAttribute('aria-label', t.languageLegend.join(', '));
  document.querySelector('.landscape-controls')?.setAttribute('aria-label', locale === 'zh' ? '选择接口指标' : 'Choose interface metric');
  document.querySelector('.gap-panel .analysis-controls')?.setAttribute('aria-label', locale === 'zh' ? '筛选接口差值图' : 'Filter interface gap chart');
  document.querySelector('.task-list')?.setAttribute('aria-label', locale === 'zh' ? '选择任务类别' : 'Choose a task family');
  document.querySelector('.scene-timebar')?.setAttribute('aria-label', locale === 'zh' ? '家庭时间信息' : 'Home time context');
  document.querySelector('.agent-conversation')?.setAttribute('aria-label', locale === 'zh' ? '对话过程' : 'Conversation walkthrough');
  const sceneFallback = document.querySelector('.scene-fallback');
  if (sceneFallback) sceneFallback.textContent = locale === 'zh' ? '当前浏览器无法启动交互式 3D 场景，请启用 WebGL 后重试。' : 'This browser could not start the interactive 3D scene. Enable WebGL to explore the room.';
  setText('#submit-results > .section-label', t.submit);
  setText('#submit-results .section-head h2', t.submitHeading);
  setText('#submit-results .section-head p', t.submitDesc);
  setText('.direct-submit-label', t.inbox);
  const emailCopy = document.querySelector('.direct-submit-card p'); if (emailCopy) emailCopy.textContent = t.emailHelp;
  const emailButton = document.querySelector('.direct-submit-card .button'); if (emailButton) { emailButton.textContent = t.emailResults; emailButton.href = `mailto:yiliu.li@chico-future.com?subject=${encodeURIComponent(t.emailSubject)}&body=${encodeURIComponent(t.emailBody)}`; }
  setText('#reproduce > .section-label', t.reproduce);
  setText('#reproduce h2', t.reproduceHeading);
  setText('#reproduce .lead', t.reproduceDesc);
  const quickStart = document.querySelector('#reproduce .button'); if (quickStart) quickStart.textContent = t.quickStart;
  const skip = document.querySelector('.skip'); if (skip) skip.textContent = locale === 'zh' ? '跳转到正文' : 'Skip to content';
  document.querySelector('.intro-register')?.setAttribute('aria-label', locale === 'zh' ? '模块信息' : 'Module details');
  document.querySelector('.facts')?.setAttribute('aria-label', locale === 'zh' ? '基准套件数据' : 'Benchmark facts');
  document.querySelector('.scene-room-labels')?.setAttribute('aria-label', locale === 'zh' ? '场景中的房间' : 'Rooms in scene');
  document.querySelectorAll('.language-chart-panel h3').forEach((node, i) => { node.textContent = t.chartLegend[i]; });
  document.querySelector('.band-summary')?.setAttribute('aria-label', locale === 'zh' ? '按模型规模比较' : 'Size-band comparison');
  document.querySelectorAll('.results-table tbody .baseline-tag').forEach((node) => { node.textContent = t.baseline; });
  document.querySelectorAll('footer nav a').forEach((node, i) => { if (i === 0) node.textContent = t.footerDataset; if (i === 2) node.textContent = t.license; });
  document.querySelectorAll('.brand[aria-label]').forEach((node) => node.setAttribute('aria-label', locale === 'zh' ? 'EdgeBench 套件首页' : 'EdgeBench suite home'));
  document.title = locale === 'zh' ? 'EdgeBench-Home — EdgeBench' : 'EdgeBench-Home — EdgeBench';
  if (loadedModels.length) { render(loadedModels, document.querySelector('.filter.active')?.dataset.filter || 'all'); renderLandscape(loadedModels, landscapeMetric); renderLanguageChart(loadedBandSummary); renderGapChart(loadedModels, gapFilter); }
  renderHighlights();
  activeStep = Math.min(activeStep, currentTaskSteps().length - 1);
  conversationFamily = '';
  updateTaskStep();
  startWalk();
}

document.querySelector('.language-toggle')?.addEventListener('click', () => applyLocale(locale === 'en' ? 'zh' : 'en'));

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
  axis.appendChild(svgElement('text', { class: 'landscape-axis-label', x: plot.left, y: height - 5 }, locale === 'zh' ? '模型规模（参数量）' : 'Model size (parameters)'));
  axis.appendChild(svgElement('text', { class: 'landscape-axis-label', x: plot.left, y: 10 }, `${metric === 'sg' ? (locale === 'zh' ? '已知状态' : 'State-Given') : (locale === 'zh' ? '查询状态' : 'State-Seeking')} ${locale === 'zh' ? '严格成功率' : 'strict success'}`));
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
      'aria-label': `${model.model}, ${model.size}, ${metric === 'sg' ? (locale === 'zh' ? '已知状态' : 'State-Given') : (locale === 'zh' ? '查询状态' : 'State-Seeking')} ${percent(model[metric])}`
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
    const metricName = metric === 'sg' ? (locale === 'zh' ? '已知状态' : 'State-Given') : (locale === 'zh' ? '查询状态' : 'State-Seeking');
    head.textContent = `${topModel.model} · ${metricName} ${percent(topModel[metric])}`;
  }
}

function renderLanguageChart(summary) {
  const width = 520;
  const height = 210;
  const plot = { left: 46, right: 18, top: 18, bottom: 38 };
  const plotHeight = height - plot.top - plot.bottom;
  const yMax = 25;
  const y = (value) => plot.top + (1 - Math.min(Number(value) || 0, yMax) / yMax) * plotHeight;
  const groupX = [125, 260, 395];
  languageCharts.forEach(({ element, key, label }) => {
    if (!element) return;
    element.replaceChildren();
    const chartLabel = label === 'State-Given' ? (locale === 'zh' ? '已知状态' : label) : (locale === 'zh' ? '查询状态' : label);
    element.appendChild(svgElement('title', { id: `${element.id}-title` }, `${chartLabel} ${locale === 'zh' ? '按模型规模和语言划分的成功率' : 'success by local model size and language'}`));
    element.appendChild(svgElement('desc', { id: `${element.id}-desc` }, locale === 'zh' ? `按模型规模比较${chartLabel}接口下中文和英文任务的严格微平均成功率。` : `Grouped bars compare Chinese and English strict micro-success across local model size bands for ${label}.`));
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
      const chineseBar = svgElement('rect', { class: 'language-bar chinese', x: chineseX, y: y(chinese), width: 18, height: Math.max(baseY - y(chinese), 1), rx: 2, tabindex: '0', role: 'img', 'aria-label': `${chartLabel}, ${band.label}, ${locale === 'zh' ? '中文' : 'Chinese'} ${percent(chinese)}` });
      const englishBar = svgElement('rect', { class: 'language-bar english', x: englishX, y: y(english), width: 18, height: Math.max(baseY - y(english), 1), rx: 2, tabindex: '0', role: 'img', 'aria-label': `${chartLabel}, ${band.label}, English ${percent(english)}` });
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
  const rowHeight = 18;
  const height = Math.max(250, 42 + localModels.length * rowHeight);
  const plot = { left: 184, right: 35, top: 28, bottom: 20 };
  const plotWidth = width - plot.left - plot.right;
  const xMax = 32;
  const x = (value) => plot.left + (Math.min(Number(value) || 0, xMax) / xMax) * plotWidth;
  gapChart.setAttribute('viewBox', `0 0 ${width} ${height}`);
  gapChart.replaceChildren();
  gapChart.appendChild(svgElement('title', { id: 'gap-title' }, locale === 'zh' ? '各本地模型的已知状态与查询状态结果' : 'State-Given and State-Seeking results by local model'));
  gapChart.appendChild(svgElement('desc', { id: 'gap-desc' }, locale === 'zh' ? '每行连接同一模型的查询状态与已知状态得分，用于呈现接口差值。' : 'Each row connects a model\'s State-Seeking and State-Given scores, showing the interface gap.'));
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
    const ssPoint = svgElement('circle', { class: 'gap-point ss', cx: ssX, cy: rowY + 4, r: 4, tabindex: '0', role: 'img', 'aria-label': `${model.model} ${locale === 'zh' ? '查询状态' : 'State-Seeking'} ${percent(model.ss)}` });
    const sgPoint = svgElement('circle', { class: 'gap-point sg', cx: sgX, cy: rowY + 4, r: 4, tabindex: '0', role: 'img', 'aria-label': `${model.model} ${locale === 'zh' ? '已知状态' : 'State-Given'} ${percent(model.sg)}` });
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
    loadedResults = data;
    loadedModels = models;
    loadedBandSummary = summarizeSizeBands(models);
    renderBandOverview(loadedBandSummary);
    render(models);
    renderLandscape(models);
    renderLanguageChart(loadedBandSummary);
    renderGapChart(models);
    renderHighlights(data);
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
    title: 'Device Grounding and Control',
    prompt: 'Turn on the lamp beside the monitor.',
    steps: [
      ['01', 'Find the device', 'Locate the lamp beside the monitor.'],
      ['02', 'Control the target', 'Turn on only that lamp.'],
      ['03', 'Verify the result', 'Leave other devices unchanged.']
    ]
  },
  MSC: {
    title: 'Multi-device Selection and Control',
    prompt: 'Turn on lights in occupied rooms. Leave the fans unchanged.',
    steps: [
      ['01', 'Check occupancy', 'Select lights in occupied rooms only.'],
      ['02', 'Control selected lights', 'Turn on the occupied-room light.'],
      ['03', 'Preserve other devices', 'Leave the empty-room light and both fans unchanged.']
    ]
  },
  AIR: {
    title: 'Ambiguity and Intent Resolution',
    prompt: 'Make it comfortable in here.',
    steps: [
      ['01', 'Clarify intent', 'Ask which room and what should change.'],
      ['02', 'Apply the answer', 'Set the light to warm at 40%.'],
      ['03', 'Verify the result', 'Leave unrelated devices unchanged.']
    ]
  },
  FAR: {
    title: 'Future Automation Registration',
    prompt: 'At 7:00 every weekday, turn on the kitchen light.',
    steps: [
      ['01', 'Read the schedule', 'Trigger: weekdays at 7:00.'],
      ['02', 'Save the automation', 'Action: turn on the kitchen light.'],
      ['03', 'Trigger at 7:00', 'Turn on the kitchen light.']
    ]
  },
  DCR: {
    title: 'Dialogue-context Resolution',
    prompt: 'Turn on the lamp. Actually, the one by the bed.',
    steps: [
      ['01', 'Read the correction', 'The latest phrase replaces “the lamp”.'],
      ['02', 'Resolve the reference', 'Match “the one by the bed” to the bedside lamp.'],
      ['03', 'Act once', 'Turn on the bedside lamp.']
    ]
  },
  PMU: {
    title: 'Personalized Memory Use',
    prompt: 'Set the living-room light to my usual evening preference.',
    steps: [
      ['01', 'Retrieve the preference', 'Find the saved evening setting.'],
      ['02', 'Check relevance', 'Use the preference for this room and time.'],
      ['03', 'Apply the setting', 'Set the light to warm at 40%.']
    ]
  },
  REQ: {
    title: 'Read-only Environment Queries',
    prompt: 'How many lights are on right now?',
    steps: [
      ['01', 'Read current state', 'Count the lights that are on.'],
      ['02', 'Return the answer', 'Two lights are on.'],
      ['03', 'Make no changes', 'Keep every device as it is.']
    ]
  }
};

const taskRows = document.querySelectorAll('.task-row');
const taskDemo = document.querySelector('.task-demo');
const taskTitle = document.getElementById('task-demo-title');
const walkCounter = document.getElementById('walk-counter');
const agentConversation = document.querySelector('.agent-conversation');
const conversationThread = document.getElementById('conversation-thread');
let activeFamily = 'DGC';
let activeStep = 0;
let walkTimer;
let agentTimers = [];
let conversationFamily = '';
let airReplyAdded = false;
let dcrCorrectionAdded = false;
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
const sceneClock = document.getElementById('scene-clock');
const sceneClockLabel = document.getElementById('scene-clock-label');
const sceneTimeContext = document.getElementById('scene-time-context');
const sceneTimeLabel = document.getElementById('scene-time-label');
const sceneTimeValue = document.getElementById('scene-time-value');
const taskVideo = document.getElementById('task-video');
const taskVideoSources = {
  DGC: '../assets/dgc-workspace.mp4', MSC: '../assets/msc-multi-device.mp4',
  AIR: '../assets/air-clarification.mp4', FAR: '../assets/far-summer.mp4',
  DCR: '../assets/dcr-context.mp4', PMU: '../assets/pmu-personalized-memory.mp4',
  REQ: '../assets/req-read-only.mp4'
};
let taskVideoFamily = '';
const timeContextByFamily = {
  FAR: { label: 'schedule', value: 'weekday' },
  PMU: { label: 'preference', value: 'evening' },
  REQ: { label: 'snapshot', value: 'now' }
};
const localTimeFormats = {
  en: new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }),
  zh: new Intl.DateTimeFormat('zh-CN', { hour: 'numeric', minute: '2-digit', hour12: false })
};

function updateSceneTime() {
  if (!sceneClock) return;
  const isFar = activeFamily === 'FAR';
  const now = new Date();
  if (isFar) {
    now.setHours(activeStep >= 2 ? 7 : 6, activeStep >= 2 ? 0 : 59, 0, 0);
  }
  if (sceneClockLabel) sceneClockLabel.textContent = isFar ? copy[locale].scene.simulatedTime : copy[locale].scene.localTime;
  sceneClock.textContent = localTimeFormats[locale].format(now);
  sceneClock.dateTime = now.toISOString();
  const context = timeContextByFamily[activeFamily];
  if (sceneTimeContext) sceneTimeContext.hidden = !context;
  if (context) {
    sceneTimeLabel.textContent = copy[locale].scene[context.label];
    sceneTimeValue.textContent = copy[locale].scene[context.value];
  }
}

updateSceneTime();
window.setInterval(updateSceneTime, 15_000);

function currentTaskSteps() {
  return copy[locale].steps[activeFamily];
}

function updateFamilyIndicator() {
  taskRows.forEach((row) => {
    const selected = row.dataset.family === activeFamily;
    row.classList.toggle('selected', selected);
    row.setAttribute('aria-pressed', String(selected));
  });
}

function syncTaskVideo() {
  if (!taskVideo) return;
  const source = taskVideoSources[activeFamily];
  const nextSource = new URL(source, document.baseURI).href;
  const familyChanged = taskVideoFamily !== activeFamily;
  if (taskVideo.src !== nextSource) {
    taskVideoFamily = activeFamily;
    taskVideo.src = source;
    taskVideo.load();
    taskVideo.addEventListener('loadedmetadata', () => {
      if (taskVideoFamily !== activeFamily || !Number.isFinite(taskVideo.duration)) return;
      taskVideo.currentTime = Math.min(taskVideo.duration - 0.05, taskVideo.duration * activeStep / currentTaskSteps().length);
      if (!motionPreference.matches) taskVideo.play().catch(() => {});
    }, { once: true });
  } else if (familyChanged) {
    taskVideo.currentTime = 0;
    if (!motionPreference.matches) taskVideo.play().catch(() => {});
  }
  if (!familyChanged && taskVideo.readyState >= HTMLMediaElement.HAVE_METADATA && Number.isFinite(taskVideo.duration)) {
    const targetTime = Math.min(taskVideo.duration - 0.05, taskVideo.duration * activeStep / currentTaskSteps().length);
    if (Math.abs(taskVideo.currentTime - targetTime) > 0.75) taskVideo.currentTime = targetTime;
  }
  if (motionPreference.matches) taskVideo.pause();
  else taskVideo.play().catch(() => {});
}

const conversationData = {
  DGC: {
    completion: 'Done — I turned on the desk lamp beside your monitor.'
  },
  MSC: {
    completion: 'The living-room light is on. I left the bedroom light and both fans as they were.'
  },
  AIR: {
    clarification: 'Which room are you in, and would you like me to adjust the light or the temperature?',
    userReply: 'The living room. Make the light warm at 40%.',
    completion: 'I set the living-room light to warm at 40%.'
  },
  FAR: {
    completion: "It's 7:00 AM. The kitchen light is on, and the schedule will repeat every weekday."
  },
  DCR: {
    users: ['Turn on the lamp.', 'Actually, the one by the bed.'],
    correction: 'Actually, the one by the bed.',
    completion: 'Sure — I turned on the bedside lamp.'
  },
  PMU: {
    completion: 'I set the living-room light to your usual evening setting: warm at 40%.'
  },
  REQ: {
    completion: 'There are two lights on: one in the living room and one in the kitchen.'
  }
};

let assistantReply;

const conversationTranslations = {
      'Turn on the lamp beside the monitor.': '打开显示器旁边的台灯。',
      'Turn on lights in occupied rooms. Leave the fans unchanged.': '打开有人房间里的灯，风扇保持不变。',
      'Make it comfortable in here.': '把这里调得舒服一些。',
      'At 7:00 every weekday, turn on the kitchen light.': '每个工作日早上 7 点打开厨房灯。',
      'Turn on the lamp. Actually, the one by the bed.': '打开那盏灯。等等，是床边那盏。',
      'Set the living-room light to my usual evening preference.': '把客厅灯调成我平时晚上的偏好。',
      'How many lights are on right now?': '现在有几盏灯开着？',
      'Done — I turned on the desk lamp beside your monitor.': '好了，已经打开显示器旁边的台灯。',
      'The living-room light is on. I left the bedroom light and both fans as they were.': '客厅灯已打开；卧室灯和两台风扇都保持原样。',
      'Which room are you in, and would you like me to adjust the light or the temperature?': '你说的是哪个房间？想调灯光还是温度？',
      'The living room. Make the light warm at 40%.': '客厅，把灯调成暖光，亮度 40%。',
      'I set the living-room light to warm at 40%.': '客厅灯已调成暖光，亮度 40%。',
      "It's 7:00 AM. The kitchen light is on, and the schedule will repeat every weekday.": '现在是早上 7 点，厨房灯已打开；这个安排会在每个工作日重复。',
      'Turn on the lamp.': '打开那盏灯。',
      'Actually, the one by the bed.': '等等，是床边那盏。',
      'Sure — I turned on the bedside lamp.': '好的，床头灯已经打开。',
      'I set the living-room light to your usual evening setting: warm at 40%.': '客厅灯已按你平时的晚间偏好设置为暖光 40%。',
      'There are two lights on: one in the living room and one in the kitchen.': '现在有两盏灯开着，分别在客厅和厨房。'
};

function localizeConversationMessage(message) {
  if (locale !== 'zh') return message;
  message = conversationTranslations[message] || message;
    const statusQuestion = message.match(/^What’s the status of the (.+)\?$/);
    if (statusQuestion) message = `看看${statusQuestion[1]}现在是什么状态。`;
  return message;
}

function appendConversationMessage(speaker, message) {
  if (!message) return;
  const item = document.createElement('div');
  item.className = `conversation-message ${speaker}`;
  const label = document.createElement('span');
  label.className = 'conversation-speaker';
  label.textContent = copy[locale][speaker === 'user' ? 'you' : 'assistant'];
  const bubble = document.createElement('p');
  bubble.textContent = localizeConversationMessage(message);
  item.append(label, bubble);
  conversationThread.appendChild(item);
  conversationThread.scrollTop = conversationThread.scrollHeight;
  return bubble;
}

function setConversationReply(message) {
  if (!message) return;
  if (assistantReply?.isConnected) assistantReply.textContent = localizeConversationMessage(message);
  else assistantReply = appendConversationMessage('assistant', message);
}

function updateConversation() {
  if (conversationFamily !== activeFamily) {
    conversationThread.replaceChildren();
    conversationFamily = activeFamily;
    assistantReply = null;
    airReplyAdded = false;
    dcrCorrectionAdded = false;
    const userMessages = conversationData[activeFamily].users || [taskData[activeFamily].prompt];
    appendConversationMessage('user', userMessages[0]);
  }
}

function setAgentStage(stage) {
  agentConversation.dataset.liveStage = stage;
  if (stage === 'understand') {
    return;
  }
  const reply = conversationData[activeFamily];
  if (activeStep === 0 && stage === 'ground') {
    if (activeFamily === 'AIR') setConversationReply(reply.clarification);
  } else if (activeStep === 1 && stage === 'act') {
    if (activeFamily === 'DCR' && !dcrCorrectionAdded) {
      appendConversationMessage('user', reply.correction);
      dcrCorrectionAdded = true;
    }
    if (activeFamily !== 'FAR' && activeFamily !== 'DCR') setConversationReply(reply.completion);
  } else if (activeStep === 2 && stage === 'confirm') {
    setConversationReply(reply.completion);
  }
}

function playAgentFlow() {
  agentTimers.forEach(window.clearTimeout);
  agentTimers = [];
  setAgentStage('understand');
  const after = (delay, callback) => agentTimers.push(window.setTimeout(callback, delay));
  if (motionPreference.matches) {
    const stage = ['ground', 'act', 'confirm'][activeStep];
    setAgentStage(stage);
    return;
  }
  const stage = ['ground', 'act', 'confirm'][activeStep];
  after(220, () => setAgentStage(stage));
}

function updateTaskStep() {
  const steps = currentTaskSteps();
  const step = steps[activeStep];
  taskTitle.textContent = copy[locale].taskTitles[Object.keys(taskData).indexOf(activeFamily)];
  updateFamilyIndicator();
  updateSceneTime();
  syncTaskVideo();
  const visibleStep = activeStep === 0 ? -1 : activeStep - 1;
  walkCounter.textContent = `${locale === 'zh' ? '步骤' : 'STEP'} ${String(activeStep + 1).padStart(2, '0')} / ${String(steps.length).padStart(2, '0')}`;
  updateConversation();
  if (activeFamily === 'AIR' && activeStep === 1 && !airReplyAdded) {
    appendConversationMessage('user', conversationData.AIR.userReply);
    assistantReply = null;
    airReplyAdded = true;
  }
  taskDemo.dataset.phase = step[1];
  playAgentFlow();
}

function advanceWalk() {
  if (activeStep >= currentTaskSteps().length - 1) {
    window.clearInterval(walkTimer);
    walkTimer = undefined;
    return;
  }
  activeStep += 1;
  updateTaskStep();
}

function startWalk() {
  window.clearInterval(walkTimer);
  if (document.hidden || activeStep >= currentTaskSteps().length - 1) return;
  walkTimer = window.setInterval(() => {
    advanceWalk();
  }, activeFamily === 'FAR' ? (motionPreference.matches ? 650 : 500) : (motionPreference.matches ? 1800 : 1300));
}

document.querySelectorAll('.task-row').forEach((row) => {
  row.addEventListener('click', () => {
    if (!taskData[row.dataset.family]) return;
    activeFamily = row.dataset.family;
    activeStep = 0;
    conversationFamily = '';
    updateTaskStep();
    startWalk();
  });
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    agentTimers.forEach(window.clearTimeout);
  }
  else playAgentFlow();
});

document.addEventListener('visibilitychange', startWalk);
const handleMotionPreference = () => {
  startWalk();
  playAgentFlow();
  syncTaskVideo();
};
if (motionPreference.addEventListener) motionPreference.addEventListener('change', handleMotionPreference);
else motionPreference.addListener(handleMotionPreference);

// Locale initialization updates the task walkthrough and starts its dialogue.
applyLocale(locale);

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
