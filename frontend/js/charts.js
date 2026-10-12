/* AURA Predictive AI - Chart.js live telemetry stream (rotational speed) */
const TelemetryChart = (() => {
  const MAX_POINTS = 40;
  let chart = null;
  const labels = [], points = [];   // kept so the stream survives re-renders of the panel
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  function create(canvas) {
    if (typeof Chart === "undefined") {
      canvas.parentElement.innerHTML = '<p class="empty">Chart library could not load. Check your internet connection.</p>';
      return null;
    }
    return new Chart(canvas, {
      type: "line",
      data: { labels: [], datasets: [{ label: "Rotational speed (RPM)", data: [], borderColor: css("--gold"),
        backgroundColor: "rgba(217,167,74,.12)", fill: true, borderWidth: 2, pointRadius: 0, tension: 0.3 }] },
      options: {
        animation: false, responsive: true, maintainAspectRatio: false, interaction: { intersect: false },
        scales: { y: { ticks: { color: css("--ink-3"), maxTicksLimit: 4 }, grid: { color: css("--line") } },
                  x: { ticks: { maxTicksLimit: 5, color: css("--ink-3") }, grid: { display: false } } },
        plugins: { legend: { display: false } },
      },
    });
  }

  /** Charts need a visible canvas: the canvas is re-created each time diagnostics render. */
  function attach(canvas) {
    if (chart) chart.destroy();
    chart = create(canvas);
    if (chart) { chart.data.labels.push(...labels); chart.data.datasets[0].data.push(...points); chart.update("none"); }
  }

  function push(label, rpm) {
    labels.push(label); points.push(rpm);
    if (labels.length > MAX_POINTS) { labels.shift(); points.shift(); }
    if (!chart) return;
    chart.data.labels = [...labels]; chart.data.datasets[0].data = [...points];
    chart.update("none");
  }

  function restyle() {
    if (!chart) return;
    chart.data.datasets[0].borderColor = css("--gold");
    chart.options.scales.y.ticks.color = chart.options.scales.x.ticks.color = css("--ink-3");
    chart.options.scales.y.grid.color = css("--line");
    chart.update("none");
  }
  return { attach, push, restyle };
})();
