/* AURA Predictive AI - semicircle "Risk Index" gauge (SVG) */
const Gauge = (() => {
  const ARC = "M10 62 A50 50 0 0 1 110 62";

  function mount(el) {
    el.innerHTML = `<svg viewBox="0 0 120 76" role="img" aria-label="Risk index">
      <path class="g-track" d="${ARC}" pathLength="100"/>
      <path class="g-arc" d="${ARC}" pathLength="100" stroke-dasharray="0 100"/>
      <text class="g-num" x="60" y="52">--</text><text class="g-unit" x="60" y="66">RISK INDEX</text></svg>`;
    const arc = el.querySelector(".g-arc"), num = el.querySelector(".g-num");
    return {
      set(percent, statusClass) {
        const pct = Math.max(0, Math.min(100, percent));
        arc.setAttribute("stroke-dasharray", `${pct} 100`);
        arc.setAttribute("class", `g-arc ${statusClass || ""}`);
        num.textContent = `${Math.round(pct)}%`;
      },
    };
  }
  return { mount };
})();
