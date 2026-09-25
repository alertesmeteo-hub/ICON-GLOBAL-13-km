(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  // Only drawing primitives from our Matplotlib exports enter the page.
  function safeSvg(text) {
    var parsed = new DOMParser().parseFromString(text, 'image/svg+xml');
    if (parsed.querySelector('parsererror')) throw Error('SVG invalide');
    var source = parsed.documentElement;
    if (source.localName !== 'svg') throw Error('SVG absent');
    var tags = new Set(['svg', 'g', 'path', 'defs', 'clipPath', 'rect', 'use']);
    var attrs = new Set(['viewBox', 'width', 'height', 'id', 'd', 'transform', 'x', 'y',
      'fill', 'stroke', 'stroke-width', 'clip-path', 'style', 'href']);
    function copy(node) {
      if (!tags.has(node.localName)) return null;
      var result = document.createElementNS(NS, node.localName);
      Array.from(node.attributes).forEach(function (attr) {
        var name = attr.localName, value = attr.value;
        if (!attrs.has(name)) return;
        if (name === 'href' && !/^#[\w.-]+$/.test(value)) return;
        if (name === 'clip-path' && !/^url\(#[\w.-]+\)$/.test(value)) return;
        if (name === 'style' && /url\s*\(|@|expression|javascript/i.test(value)) return;
        result.setAttribute(name, value);
      });
      Array.from(node.children).forEach(function (child) {
        var clean = copy(child); if (clean) result.appendChild(clean);
      });
      return result;
    }
    return copy(source);
  }
  window.IconVectorZoom = function (image) {
    var viewer = image.parentElement, vector = null, box = null, enabled = false;
    var sequence = 0, objectUrl = null, scale = 1, tx = 0, ty = 0, coordinates = null;
    function layout() {
      if (!vector || !enabled || !image.clientWidth || !image.clientHeight) return;
      var w = image.clientWidth * box[2], h = image.clientHeight * box[3];
      tx = Math.max(-(scale - 1) * w / 2, Math.min((scale - 1) * w / 2, tx));
      ty = Math.max(-(scale - 1) * h / 2, Math.min((scale - 1) * h / 2, ty));
      Object.assign(vector.style, {position: 'absolute', pointerEvents: 'none', zIndex: '1',
        left: (image.offsetLeft + image.clientWidth * box[0]) + 'px',
        top: (image.offsetTop + image.clientHeight * box[1]) + 'px',
        width: w + 'px', height: h + 'px', maxWidth: 'none', overflow: 'hidden', background: 'white'});
      var x = box[0] + box[2] * (.5 - (.5 + tx / w) / scale);
      var y = box[1] + box[3] * (.5 - (.5 + ty / h) / scale);
      vector.setAttribute('viewBox', [
        coordinates[0] + x * coordinates[2], coordinates[1] + y * coordinates[3],
        coordinates[2] * box[2] / scale, coordinates[3] * box[3] / scale
      ].join(' '));
    }
    function clear() {
      if (vector) vector.remove();
      vector = null; enabled = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    this.load = function (url, plotBox, interactive, fallback) {
      var current = ++sequence;
      clear(); scale = 1; tx = 0; ty = 0;
      image.style.transform = 'none';
      image.src = fallback;
      if (!url) return;
      fetch(url, {cache: 'no-cache'}).then(function (response) {
        if (!response.ok) throw Error('HTTP ' + response.status);
        return response.text();
      }).then(function (text) {
        if (current !== sequence) return;
        var clean = safeSvg(text);
        coordinates = clean.getAttribute('viewBox').trim().split(/\s+/).map(Number);
        if (coordinates.length !== 4 || !coordinates.every(Number.isFinite)) throw Error('Dimensions SVG invalides');
        objectUrl = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clean)], {type: 'image/svg+xml'}));
        image.src = objectUrl;
        if (!interactive) return;
        box = plotBox || [0, 0, 1, 1]; enabled = true; vector = clean;
        // Unique IDs prevent clipping paths from colliding across map widgets.
        var prefix = 'icon-' + Math.random().toString(36).slice(2) + '-';
        vector.querySelectorAll('[id]').forEach(function (node) { node.id = prefix + node.id; });
        vector.querySelectorAll('[href]').forEach(function (node) { node.setAttribute('href', '#' + prefix + node.getAttribute('href').slice(1)); });
        vector.querySelectorAll('[clip-path]').forEach(function (node) {
          node.setAttribute('clip-path', node.getAttribute('clip-path').replace('url(#', 'url(#' + prefix));
        });
        vector.setAttribute('preserveAspectRatio', 'none');
        vector.setAttribute('aria-hidden', 'true');
        viewer.appendChild(vector); layout();
      }).catch(function () {
        if (current === sequence) {
          clear();
          image.dispatchEvent(new CustomEvent('vector-unavailable'));
        }
      });
    };
    this.transform = function (nextScale, x, y) {
      // Never enlarge the fallback PNG while vector publication is pending.
      scale = nextScale; tx = x; ty = y; image.style.transform = 'none'; layout();
    };
    this.point = function (event, plotBox) {
      var rect = image.getBoundingClientRect(), b = plotBox || [0, 0, 1, 1];
      var x = ((event.clientX - rect.left) / rect.width - b[0]) / b[2];
      var y = ((event.clientY - rect.top) / rect.height - b[1]) / b[3];
      if (x < 0 || x > 1 || y < 0 || y > 1) return null;
      if (enabled) {
        x = .5 + (x - .5 - tx / (rect.width * b[2])) / scale;
        y = .5 + (y - .5 - ty / (rect.height * b[3])) / scale;
      }
      return [x, y];
    };
    image.addEventListener('load', layout);
    new ResizeObserver(layout).observe(image);
  };
}());
