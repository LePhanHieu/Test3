const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const webapp = path.resolve(__dirname, '..', 'skin_cancer', 'webapp');
const stylesheetName = 'css/select-theme.css';

test('both role portals load the shared native select stylesheet', () => {
  for (const name of ['index.html', 'admin.html']) {
    const markup = fs.readFileSync(path.join(webapp, 'templates', name), 'utf8');
    assert.ok(markup.includes(stylesheetName), `${name} must load ${stylesheetName}`);
  }
});

test('native select options have explicit light and dark contrast rules', () => {
  const css = fs.readFileSync(path.join(webapp, 'static', stylesheetName), 'utf8');
  assert.match(css, /select\s+option/);
  assert.match(css, /select\s+optgroup/);
  assert.match(css, /html\[data-theme="dark"\]/);
  assert.match(css, /color-scheme:\s*dark/);
  assert.match(css, /background-color:/);
});
