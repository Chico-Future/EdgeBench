const tableBody = document.getElementById('model-rows');
const filterButtons = document.querySelectorAll('.filter');

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

fetch('data/results.json')
  .then((response) => {
    if (!response.ok) throw new Error(`Could not load results: ${response.status}`);
    return response.json();
  })
  .then((data) => {
    const models = data.models || [];
    render(models);
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

document.querySelectorAll('.task-row').forEach((row) => {
  row.addEventListener('click', () => {
    document.querySelectorAll('.task-row').forEach((item) => item.classList.remove('selected'));
    row.classList.add('selected');
  });
});
