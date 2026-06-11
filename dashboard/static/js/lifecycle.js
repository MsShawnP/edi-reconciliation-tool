/**
 * PO Lifecycle D3 visual — live version for the exception dashboard.
 *
 * Fetches /api/lifecycle for real corpus numbers.
 * Falls back to the canonical example (150/138/150/131) when the DB is offline.
 *
 * Requires D3 v7 on the page before this script loads.
 * Renders into #lifecycle-chart.
 */
(function () {
  "use strict";

  const CANONICAL = { ordered: 150, shipped: 138, invoiced: 150, paid: 131 };

  // Design tokens (mirror lailara.css CSS vars — not readable from JS directly)
  const C = {
    canvas:   "#f5f3ee",
    ink:      "#0d0d0d",
    border:   "#d9d9d9",
    sub:      "#595959",
    muted:    "#959595",
    navy:     "#1f2e7a",
    rose:     "#b82d4a",
    roseSurf: "#fbe9ed",
    roseBrd:  "#e68a9a",
    orange:   "#ee8a2a",
    orSurf:   "#fdeee0",
    orBrd:    "#f6b97c",
    red:      "#cc100a",
    serif:    "'Playfair Display', Georgia, serif",
    sans:     "'Source Sans 3', 'Helvetica Neue', Arial, sans-serif",
  };

  // Layout constants
  const W = 1120, H = 480;          // inner SVG dimensions
  const BOX_W = 170, BOX_H = 145;
  const BOX_TOP = 88;
  const BOX_CX = [130, 390, 650, 910]; // box center-x for 4 stages
  const ARROW_Y = BOX_TOP + BOX_H / 2;
  const CALL_TOP = BOX_TOP + BOX_H + 24;
  const CALL_W = 150, CALL_H = 88;

  const STAGES = [
    { key: "ordered",  label: "ORDERED",  color: C.ink },
    { key: "shipped",  label: "SHIPPED",  color: C.rose },
    { key: "invoiced", label: "INVOICED", color: C.orange },
    { key: "paid",     label: "PAID",     color: C.rose },
  ];

  function fmtDelta(a, b) {
    const d = b - a;
    return (d >= 0 ? "+" : "−") + Math.abs(d).toLocaleString() + " cases";
  }

  function calloutFill(a, b) {
    const d = b - a;
    if (d > 0) return { fill: C.orSurf, stroke: C.orBrd, color: C.orange };
    return { fill: C.roseSurf, stroke: C.roseBrd, color: C.rose };
  }

  function calloutDesc(i, data) {
    if (i === 0) return ["not shipped", "OTIF exposure"];
    if (i === 1) return data.invoiced > data.shipped
      ? ["invoiced, not in ASN", "unbilled risk"]
      : ["ASN qty > invoice", "shipped-not-invoiced"];
    return ["short-paid on remittance", "30-day dispute window"];
  }

  function render(data) {
    const container = document.getElementById("lifecycle-chart");
    if (!container) return;
    container.innerHTML = "";

    const svg = d3.select(container)
      .append("svg")
      .attr("viewBox", `0 0 ${W} ${H}`)
      .attr("width", "100%")
      .style("max-width", `${W}px`)
      .attr("role", "img")
      .attr("aria-label", `PO Lifecycle: ${data.ordered} ordered, ${data.shipped} shipped, ${data.invoiced} invoiced, ${data.paid} paid`);

    // Background
    svg.append("rect").attr("width", W).attr("height", H).attr("fill", C.canvas);

    // Title
    svg.append("text")
      .attr("x", 20).attr("y", 32)
      .style("font-family", C.serif)
      .style("font-size", "18px")
      .style("font-weight", "700")
      .style("fill", C.ink)
      .text("PO Lifecycle");

    svg.append("text")
      .attr("x", 20).attr("y", 54)
      .style("font-family", C.sans)
      .style("font-size", "13px")
      .style("fill", C.sub)
      .text(data.source === "live" ? "Live from exception mart" : "Canonical example — connect database for live numbers");

    // Boxes
    STAGES.forEach((stage, i) => {
      const cx = BOX_CX[i];
      const bx = cx - BOX_W / 2;

      svg.append("rect")
        .attr("x", bx).attr("y", BOX_TOP)
        .attr("width", BOX_W).attr("height", BOX_H)
        .attr("fill", "#fff").attr("stroke", C.border).attr("stroke-width", 1)
        .attr("rx", 2);

      svg.append("text")
        .attr("x", cx).attr("y", BOX_TOP + 20)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "10px")
        .style("letter-spacing", "0.06em")
        .style("fill", C.sub)
        .text(stage.label);

      svg.append("text")
        .attr("x", cx).attr("y", BOX_TOP + 85)
        .attr("text-anchor", "middle")
        .style("font-family", C.serif)
        .style("font-size", "48px")
        .style("font-weight", "700")
        .style("fill", stage.color)
        .text(data[stage.key].toLocaleString());

      svg.append("text")
        .attr("x", cx).attr("y", BOX_TOP + 112)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "13px")
        .style("fill", C.sub)
        .text("cases");
    });

    // Arrows + callouts
    const vals = [data.ordered, data.shipped, data.invoiced, data.paid];
    for (let i = 0; i < 3; i++) {
      const x1 = BOX_CX[i]   + BOX_W / 2;
      const x2 = BOX_CX[i+1] - BOX_W / 2;
      const mx = (x1 + x2) / 2;

      // Arrow shaft + head
      svg.append("line")
        .attr("x1", x1).attr("y1", ARROW_Y)
        .attr("x2", x2 - 8).attr("y2", ARROW_Y)
        .attr("stroke", C.border).attr("stroke-width", 1.5);
      svg.append("polygon")
        .attr("points", `${x2},${ARROW_Y} ${x2-10},${ARROW_Y-5} ${x2-10},${ARROW_Y+5}`)
        .attr("fill", C.border);

      // Dashed stem
      svg.append("line")
        .attr("x1", mx).attr("y1", BOX_TOP + BOX_H + 2)
        .attr("x2", mx).attr("y2", CALL_TOP - 2)
        .attr("stroke", C.border).attr("stroke-width", 1)
        .attr("stroke-dasharray", "3,3");

      // Callout box
      const style = calloutFill(vals[i], vals[i+1]);
      svg.append("rect")
        .attr("x", mx - CALL_W / 2).attr("y", CALL_TOP)
        .attr("width", CALL_W).attr("height", CALL_H)
        .attr("fill", style.fill).attr("stroke", style.stroke).attr("stroke-width", 1)
        .attr("rx", 2);

      // Delta text
      svg.append("text")
        .attr("x", mx).attr("y", CALL_TOP + 24)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "16px")
        .style("font-weight", "700")
        .style("fill", style.color)
        .text(fmtDelta(vals[i], vals[i+1]));

      // Description
      const descs = calloutDesc(i, data);
      svg.append("text")
        .attr("x", mx).attr("y", CALL_TOP + 46)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "12px")
        .style("fill", C.sub)
        .text(descs[0]);

      svg.append("text")
        .attr("x", mx).attr("y", CALL_TOP + 63)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "12px")
        .style("fill", C.muted)
        .text(descs[1]);
    }

    // Footnote
    svg.append("line")
      .attr("x1", 20).attr("y1", H - 32).attr("x2", W - 20).attr("y2", H - 32)
      .attr("stroke", C.border).attr("stroke-width", 1);
    svg.append("text")
      .attr("x", 20).attr("y", H - 16)
      .style("font-family", C.sans)
      .style("font-size", "11px")
      .style("fill", C.muted)
      .text("Dollar impact at $47.50/case wholesale. Synthetic corpus — Cinderhaven platform.");
  }

  async function init() {
    try {
      const resp = await fetch("/api/lifecycle");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      render(data);
    } catch (_) {
      render({ ...CANONICAL, source: "canonical" });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
