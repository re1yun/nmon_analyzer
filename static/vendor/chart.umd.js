(function (global) {
  function Chart(context, config) {
    this.ctx = context;
    this.config = config;
    this.draw();
  }

  Chart.prototype.draw = function () {
    const dataset = (this.config.data.datasets || [])[0] || { data: [] };
    const labels = this.config.data.labels || [];
    const ctx = this.ctx;
    const width = ctx.canvas.width;
    const height = ctx.canvas.height;
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = dataset.borderColor || '#1b4d89';
    ctx.lineWidth = 2;
    const values = dataset.data;
    if (!values.length) return;
    const min = Math.min.apply(null, values);
    const max = Math.max.apply(null, values);
    const padding = 20;
    const scaleY = max === min ? 0 : (height - padding * 2) / (max - min);
    const scaleX = values.length <= 1 ? 0 : (width - padding * 2) / (values.length - 1);
    ctx.beginPath();
    values.forEach((value, index) => {
      const x = padding + scaleX * index;
      const y = height - padding - (scaleY ? (value - min) * scaleY : 0);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };

  global.Chart = Chart;
})(typeof window !== 'undefined' ? window : this);
