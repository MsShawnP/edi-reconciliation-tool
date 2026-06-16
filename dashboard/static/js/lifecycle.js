/**
 * PO Lifecycle D3 visual — live version for the exception dashboard.
 *
 * Reads lifecycle numbers from the #lifecycle-data JSON block injected
 * server-side. Falls back to the canonical example (150/138/150/131)
 * when the DB is not connected.
 *
 * Requires D3 v7 on the page before this script loads.
 * Renders into #lifecycle-visual.
 */
(function () {
  "use strict";

  // Canonical fallback (plan spec: 150 ordered → 138 shipped → 150 invoiced → 131 paid)
  var CANONICAL = { ordered: 150, shipped: 138, invoiced: 150, paid: 131, source: "canonical" };

  // Lailara design system tokens (LAILARA_DESIGN_SYSTEM.md v2.0)
  var C = {
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
    serif:    "'Playfair Display', Georgia, serif",
    sans:     "'Source Sans 3', 'Source Sans Pro', 'Helvetica Neue', Arial, sans-serif",
  };

  // Layout constants (internal SVG coordinate space)
  var W = 1120, H = 480;
  var BOX_W = 170, BOX_H = 145;
  var BOX_TOP = 88;
  var BOX_CX = [130, 390, 650, 910];   // center-x for each of the 4 stage boxes
  var ARROW_Y = BOX_TOP + BOX_H / 2;
  var CALL_TOP = BOX_TOP + BOX_H + 24;
  var CALL_W = 150, CALL_H = 88;

  var STAGES = [
    { key: "ordered",  label: "ORDERED",  color: C.ink    },
    { key: "shipped",  label: "SHIPPED",  color: C.rose   },
    { key: "invoiced", label: "INVOICED", color: C.orange },
    { key: "paid",     label: "PAID",     color: C.rose   },
  ];

  function fmtCompact(n) {
    var abs = Math.abs(n);
    if (abs >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (abs >= 10000) return (n / 1e3).toFixed(1) + "K";
    return n.toLocaleString();
  }

  function fontSizeForValue(n) {
    if (Math.abs(n) >= 1e6) return "36px";
    if (Math.abs(n) >= 10000) return "40px";
    return "48px";
  }

  function fmtDelta(a, b) {
    var d = b - a;
    return (d >= 0 ? "+" : "−") + fmtCompact(Math.abs(d)) + " cases";
  }

  function calloutStyle(a, b) {
    return (b > a)
      ? { fill: C.orSurf,   stroke: C.orBrd,  color: C.orange }
      : { fill: C.roseSurf, stroke: C.roseBrd, color: C.rose   };
  }

  function calloutDesc(i, data) {
    if (i === 0) return ["not shipped", "OTIF exposure"];
    if (i === 1) return data.invoiced > data.shipped
      ? ["invoiced without ASN", "chargeback exposure"]
      : ["ASN qty > invoice qty", "shipped-not-invoiced"];
    return ["short-paid on remittance", "30-day dispute window"];
  }

  function render(data) {
    var container = document.getElementById("lifecycle-visual");
    if (!container) return;
    container.innerHTML = "";

    var svg = d3.select(container)
      .append("svg")
      .attr("viewBox", "0 0 " + W + " " + H)
      .attr("width", "100%")
      .style("max-width", W + "px")
      .style("display", "block")
      .attr("role", "img")
      .attr("aria-label",
        "PO Lifecycle: " + data.ordered + " ordered, " + data.shipped + " shipped, " +
        data.invoiced + " invoiced, " + data.paid + " paid");

    // Canvas background
    svg.append("rect").attr("width", W).attr("height", H).attr("fill", C.canvas);

    // Section title
    svg.append("text")
      .attr("x", 20).attr("y", 32)
      .style("font-family", C.serif)
      .style("font-size", "18px")
      .style("font-weight", "700")
      .style("fill", C.ink)
      .text("PO Lifecycle — Four-Way EDI Match");

    svg.append("text")
      .attr("x", 20).attr("y", 54)
      .style("font-family", C.sans)
      .style("font-size", "13px")
      .style("fill", C.sub)
      .text(data.source === "live"
        ? "Live from exception mart (edi_marts.int_four_way_match)"
        : "Canonical example — connect to Postgres and run dbt for live numbers");

    // Stage boxes
    STAGES.forEach(function (stage, i) {
      var cx = BOX_CX[i];
      var bx = cx - BOX_W / 2;

      // Box border
      svg.append("rect")
        .attr("x", bx).attr("y", BOX_TOP)
        .attr("width", BOX_W).attr("height", BOX_H)
        .attr("fill", "#ffffff")
        .attr("stroke", C.border)
        .attr("stroke-width", 1)
        .attr("rx", 2);

      // Stage label (uppercase, small)
      svg.append("text")
        .attr("x", cx).attr("y", BOX_TOP + 22)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "10px")
        .style("letter-spacing", "0.07em")
        .style("fill", C.sub)
        .text(stage.label);

      // Main quantity number
      var val = data[stage.key];
      svg.append("text")
        .attr("x", cx).attr("y", BOX_TOP + 88)
        .attr("text-anchor", "middle")
        .style("font-family", C.serif)
        .style("font-size", fontSizeForValue(val))
        .style("font-weight", "700")
        .style("fill", stage.color)
        .text(fmtCompact(val));

      // "cases" unit
      svg.append("text")
        .attr("x", cx).attr("y", BOX_TOP + 112)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "13px")
        .style("fill", C.sub)
        .text("cases");
    });

    // Arrows + callout boxes between each pair of stages
    var vals = [data.ordered, data.shipped, data.invoiced, data.paid];
    for (var i = 0; i < 3; i++) {
      var x1 = BOX_CX[i]     + BOX_W / 2;
      var x2 = BOX_CX[i + 1] - BOX_W / 2;
      var mx = (x1 + x2) / 2;

      // Arrow shaft
      svg.append("line")
        .attr("x1", x1).attr("y1", ARROW_Y)
        .attr("x2", x2 - 8).attr("y2", ARROW_Y)
        .attr("stroke", C.border)
        .attr("stroke-width", 1.5);

      // Arrowhead
      svg.append("polygon")
        .attr("points", x2 + "," + ARROW_Y + " " + (x2 - 10) + "," + (ARROW_Y - 5) + " " + (x2 - 10) + "," + (ARROW_Y + 5))
        .attr("fill", C.border);

      // Dashed drop stem from arrow to callout
      svg.append("line")
        .attr("x1", mx).attr("y1", BOX_TOP + BOX_H + 2)
        .attr("x2", mx).attr("y2", CALL_TOP - 2)
        .attr("stroke", C.border)
        .attr("stroke-width", 1)
        .attr("stroke-dasharray", "3,3");

      // Callout box (colored by direction of change)
      var style = calloutStyle(vals[i], vals[i + 1]);
      svg.append("rect")
        .attr("x", mx - CALL_W / 2).attr("y", CALL_TOP)
        .attr("width", CALL_W).attr("height", CALL_H)
        .attr("fill", style.fill)
        .attr("stroke", style.stroke)
        .attr("stroke-width", 1)
        .attr("rx", 2);

      // Delta quantity
      svg.append("text")
        .attr("x", mx).attr("y", CALL_TOP + 26)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "16px")
        .style("font-weight", "700")
        .style("fill", style.color)
        .text(fmtDelta(vals[i], vals[i + 1]));

      // First description line
      var descs = calloutDesc(i, data);
      svg.append("text")
        .attr("x", mx).attr("y", CALL_TOP + 48)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "12px")
        .style("fill", C.sub)
        .text(descs[0]);

      // Second description line
      svg.append("text")
        .attr("x", mx).attr("y", CALL_TOP + 65)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "12px")
        .style("fill", C.muted)
        .text(descs[1]);
    }

    // Footnote rule + text
    svg.append("line")
      .attr("x1", 20).attr("y1", H - 32)
      .attr("x2", W - 20).attr("y2", H - 32)
      .attr("stroke", C.border)
      .attr("stroke-width", 1);

    svg.append("text")
      .attr("x", 20).attr("y", H - 16)
      .style("font-family", C.sans)
      .style("font-size", "11px")
      .style("fill", C.muted)
      .text("Synthetic corpus — Walmart · UNFI · KeHE. UoM normalized to cases before comparison.");
  }

  // Read server-injected data; fall back to canonical
  var el = document.getElementById("lifecycle-data");
  var serverData = null;
  try { serverData = el ? JSON.parse(el.textContent) : null; } catch (_) {}

  var data = (serverData && serverData.ordered > 0)
    ? serverData
    : CANONICAL;

  // Render immediately (data is already available inline)
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { render(data); });
  } else {
    render(data);
  }

}());
