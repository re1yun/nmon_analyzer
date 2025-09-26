(function () {
  const uploadForm = document.getElementById('upload-form');
  const fileInput = document.getElementById('file-input');
  const dropArea = document.getElementById('drop-area');
  const tableBody = document.getElementById('files-table-body');
  const summaryNodes = {
    total: document.getElementById('summary-total'),
    ok: document.getElementById('summary-ok'),
    warn: document.getElementById('summary-warn'),
    crit: document.getElementById('summary-crit'),
    warnChecks: document.getElementById('summary-warn-checks'),
    critChecks: document.getElementById('summary-crit-checks'),
  };

  async function refreshData() {
    const response = await fetch('/api/files');
    if (!response.ok) {
      console.error('Failed to load files');
      return;
    }
    const payload = await response.json();
    renderSummary(payload.summary || {});
    renderTable(payload.files || []);
  }

  function renderSummary(summary) {
    if (!summaryNodes.total) return;
    summaryNodes.total.textContent = summary.total_files ?? 0;
    summaryNodes.ok.textContent = summary.ok_files ?? 0;
    summaryNodes.warn.textContent = summary.warn_files ?? 0;
    summaryNodes.crit.textContent = summary.crit_files ?? 0;
    summaryNodes.warnChecks.textContent = summary.warn_checks ?? 0;
    summaryNodes.critChecks.textContent = summary.crit_checks ?? 0;
  }

  function badge(level) {
    const span = document.createElement('span');
    span.classList.add('badge');
    if (level === 'CRIT') span.classList.add('crit');
    else if (level === 'WARN') span.classList.add('warn');
    else span.classList.add('ok');
    span.textContent = level || 'OK';
    return span;
  }

  function renderTable(files) {
    if (!tableBody) return;
    tableBody.innerHTML = '';
    files.forEach((file) => {
      const row = document.createElement('tr');
      const fileCell = document.createElement('td');
      const link = document.createElement('a');
      link.href = `/file/${file.file_id}`;
      link.textContent = file.file_id;
      fileCell.appendChild(link);
      row.appendChild(fileCell);

      const hostCell = document.createElement('td');
      hostCell.textContent = file.hostname || '—';
      row.appendChild(hostCell);

      const startCell = document.createElement('td');
      startCell.textContent = file.start_time ? new Date(file.start_time).toLocaleString() : '—';
      row.appendChild(startCell);

      const overallCell = document.createElement('td');
      overallCell.appendChild(badge(file.overall || 'OK'));
      row.appendChild(overallCell);

      tableBody.appendChild(row);
    });
  }

  function preventDefaults(event) {
    event.preventDefault();
    event.stopPropagation();
  }

  function highlight() {
    dropArea && dropArea.classList.add('dragover');
  }

  function unhighlight() {
    dropArea && dropArea.classList.remove('dragover');
  }

  async function handleFiles(files) {
    const body = new FormData();
    Array.from(files).forEach((file) => body.append('files', file));
    const response = await fetch('/upload', { method: 'POST', body });
    if (!response.ok) {
      console.error('Upload failed');
      return;
    }
    await refreshData();
  }

  if (uploadForm && fileInput) {
    uploadForm.addEventListener('submit', (event) => {
      event.preventDefault();
      if (fileInput.files.length === 0) return;
      handleFiles(fileInput.files);
      fileInput.value = '';
    });
  }

  if (dropArea) {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach((eventName) => {
      dropArea.addEventListener(eventName, preventDefaults, false);
    });
    ['dragenter', 'dragover'].forEach((eventName) => {
      dropArea.addEventListener(eventName, highlight, false);
    });
    ['dragleave', 'drop'].forEach((eventName) => {
      dropArea.addEventListener(eventName, unhighlight, false);
    });
    dropArea.addEventListener('drop', (event) => {
      const dt = event.dataTransfer;
      if (!dt) return;
      handleFiles(dt.files);
    });
    dropArea.addEventListener('click', () => fileInput && fileInput.click());
  }

  document.addEventListener('DOMContentLoaded', () => {
    refreshData();
  });

  // Detail page rendering
  const detailRoot = document.getElementById('file-detail-root');
  if (detailRoot) {
    const fileId = detailRoot.dataset.fileId;
    fetch(`/api/file/${fileId}`)
      .then((response) => response.json())
      .then((payload) => {
        if (!payload.series) return;
        renderDetailCharts(payload.series, payload.analysis);
      });
  }

  function renderDetailCharts(seriesData, analysis) {
    const emmcKey = Object.keys(seriesData).find((name) => name.startsWith('disk_write_kbps::'));
    const memoryKey = seriesData.mem_active_kb ? 'mem_active_kb' : Object.keys(seriesData).find((name) => name.startsWith('mem_'));
    const chartConfigs = [
      {
        canvasId: 'cpu-chart',
        seriesName: 'cpu_busy_pct',
        label: 'CPU Busy %',
      },
      {
        canvasId: 'memory-chart',
        seriesName: memoryKey,
        label: 'Memory Active (KB)',
      },
      {
        canvasId: 'emmc-chart',
        seriesName: emmcKey,
        label: 'eMMC Writes (KB/s)',
      },
      {
        canvasId: 'network-chart',
        seriesName: 'net_total_kbps',
        label: 'Network Throughput (KB/s)',
      },
    ];

    chartConfigs.forEach((config) => {
      const canvas = document.getElementById(config.canvasId);
      if (!canvas) return;
      const series = seriesData[config.seriesName];
      if (!series) return;
      const ctx = canvas.getContext('2d');
      new Chart(ctx, {
        type: 'line',
        data: {
          labels: series.timestamps.map((value) => new Date(value).toLocaleString()),
          datasets: [
            {
              label: config.label,
              data: series.values,
              borderColor: '#1b4d89',
              fill: false,
              pointRadius: 0,
            },
          ],
        },
        options: {
          responsive: true,
          scales: {
            x: { display: false },
            y: { beginAtZero: false },
          },
        },
      });
    });

    const checksTable = document.getElementById('checks-table-body');
    if (!checksTable || !analysis) return;
    checksTable.innerHTML = '';
    (analysis.checks || []).forEach((check) => {
      const row = document.createElement('tr');
      const ruleCell = document.createElement('td');
      ruleCell.textContent = check.rule;
      row.appendChild(ruleCell);

      const levelCell = document.createElement('td');
      levelCell.appendChild(badge(check.level));
      row.appendChild(levelCell);

      const summaryCell = document.createElement('td');
      summaryCell.textContent = check.summary;
      row.appendChild(summaryCell);

      checksTable.appendChild(row);
    });
  }
})();
