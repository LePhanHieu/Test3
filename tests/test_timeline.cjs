"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../skin_cancer/webapp/static/js/timeline.js"), "utf8");

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.style = {};
    this.innerHTML = "";
    this.textContent = "";
    this.parentNode = null;
  }

  append(child) {
    child.parentNode = this;
    this.children.push(child);
  }

  insertRow() {
    const row = new FakeElement("tr");
    this.append(row);
    return row;
  }

  insertCell() {
    const cell = new FakeElement("td");
    this.append(cell);
    return cell;
  }
}

function descendants(element) {
  return [element, ...element.children.flatMap(descendants)];
}

function runTimeline({ Chart, data }) {
  const resultsState = new FakeElement("section");
  const document = {
    getElementById: (id) => (id === "resultsState" ? resultsState : null),
    createElement: (tag) => new FakeElement(tag),
  };
  const context = vm.createContext({ document, window: {}, console, ...(Chart ? { Chart } : {}) });
  vm.runInContext(source, context, { filename: "timeline.js" });
  context.data = data;
  vm.runInContext("renderTimeline(data)", context);
  return descendants(resultsState);
}

const points = [
  { date: "2026-01-01", case_code: "QA-1", predicted_class: "MEL", prob_malignant: 75, confidence: 90 },
  { date: "2026-02-01", case_code: "QA-2", predicted_class: "NV", prob_malignant: 20, confidence: 85 },
];

test("timeline keeps a readable table when Chart.js CDN is unavailable", () => {
  const elements = runTimeline({ data: { points } });
  assert.ok(elements.some((item) => item.tagName === "table"));
  assert.ok(elements.some((item) => item.textContent.includes("Biểu đồ") && item.textContent.includes("không khả dụng")));
});

test("timeline draws the chart when Chart.js is available", () => {
  let created = 0;
  class Chart {
    constructor(_canvas, options) {
      created += 1;
      assert.equal(options.type, "line");
      assert.equal(options.data.datasets[0].data.length, 2);
    }
  }
  const elements = runTimeline({ Chart, data: { points } });
  assert.equal(created, 1);
  assert.ok(elements.some((item) => item.tagName === "table"));
});

test("timeline treats API labels as text, never executable markup", () => {
  const unsafe = '<img src=x onerror="alert(1)">';
  const elements = runTimeline({
    Chart: class Chart {},
    data: { points: [{ ...points[0], predicted_class: unsafe }, points[1]], trend: { label: unsafe, change: 10 } },
  });
  const html = elements.map((item) => item.innerHTML).join("\n");
  assert.ok(!html.includes(unsafe), "Untrusted API text was inserted as raw HTML");
  assert.ok(html.includes("&lt;img"), "Escaped text is still shown to the user");
});
