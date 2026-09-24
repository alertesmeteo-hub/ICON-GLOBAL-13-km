(function () {
    'use strict';
    function fetchJson(url) {
        return fetch(url, { cache: 'no-cache' }).then(function (response) {
            if (!response.ok) { throw new Error('HTTP ' + response.status); }
            return response.json();
        });
    }
    function nearest(values, target) {
        var best = 0, distance = Infinity;
        values.forEach(function (value, index) {
            var next = Math.abs(Number(value) - target);
            if (next < distance) { best = index; distance = next; }
        });
        return best;
    }
    function init(widget) {
        if (widget.dataset.ready) { return; }
        widget.dataset.ready = '1';
        var app = widget.closest('[data-icong-app]');
        var base = (app.dataset.baseUrl || '').replace(/\/+$/, '') + '/';
        var fixed = widget.dataset.fixed === '1';
        var region = widget.dataset.region || 'france';
        var productKey = 'precipitation', lead = 180, manifest = null, item = null, grid = null;
        var scale = 1, translateX = 0, translateY = 0, dragging = false, dragStart = null, probeSequence = 0;
        var image = widget.querySelector('.icong-map-image');
        var status = widget.querySelector('.icong-map-status');
        var summary = widget.querySelector('.icong-map-summary');
        var probe = widget.querySelector('.icong-map-probe');
        var products = widget.querySelector('.icong-map-products');
        var leads = widget.querySelector('.icong-map-leads');
        var regions = widget.querySelector('.icong-map-regions');
        function hideProbe() { probe.hidden = true; }
        function transform() {
            image.style.transform = 'translate(' + translateX + 'px,' + translateY + 'px) scale(' + scale + ')';
            image.style.cursor = fixed ? 'default' : (dragging ? 'grabbing' : 'grab');
        }
        function reset() { scale = 1; translateX = 0; translateY = 0; transform(); hideProbe(); }
        function loadGrid(selected) {
            var sequence = ++probeSequence; grid = null; hideProbe();
            if (fixed || !selected.values) { return; }
            fetchJson(base + selected.values).then(function (payload) {
                if (sequence === probeSequence) { grid = payload; }
            }).catch(function () { if (sequence === probeSequence) { grid = null; } });
        }
        function render() {
            if (!manifest) { return; }
            var product = manifest.products[productKey];
            item = product.maps.find(function (candidate) {
                return candidate.region === region && Number(candidate.lead_hour) === Number(lead);
            });
            if (!item) { status.textContent = 'Carte indisponible.'; return; }
            status.textContent = 'Chargement de la carte…';
            summary.textContent = product.label + ' · ' + (region === 'france' ? 'France' : 'Europe') + ' · H+' + lead;
            image.alt = 'Carte ICON-GLOBAL ' + product.label + ', ' + region + ', H+' + lead;
            image.src = base + item.image;
            reset(); loadGrid(item);
            products.querySelectorAll('button').forEach(function (button) { button.setAttribute('aria-pressed', String(button.dataset.product === productKey)); });
            leads.querySelectorAll('button').forEach(function (button) { button.setAttribute('aria-pressed', String(Number(button.dataset.lead) === lead)); });
            if (regions) { regions.querySelectorAll('button').forEach(function (button) { button.setAttribute('aria-pressed', String(button.dataset.region === region)); }); }
        }
        function build() {
            Object.keys(manifest.products).forEach(function (key) {
                var button = document.createElement('button'); button.type = 'button'; button.dataset.product = key;
                button.textContent = manifest.products[key].label;
                button.addEventListener('click', function () { productKey = key; render(); }); products.appendChild(button);
            });
            manifest.steps.forEach(function (value) {
                var button = document.createElement('button'); button.type = 'button'; button.dataset.lead = value;
                button.textContent = '+' + value + 'h'; button.addEventListener('click', function () { lead = Number(value); render(); }); leads.appendChild(button);
            });
            render();
        }
        function showProbe(event) {
            if (fixed || dragging || !grid || !item) { hideProbe(); return; }
            var rect = image.getBoundingClientRect(), viewer = image.parentElement.getBoundingClientRect();
            var box = item.plot_box || [0, 0, 1, 1];
            var x = ((event.clientX - rect.left) / rect.width - box[0]) / box[2];
            var y = ((event.clientY - rect.top) / rect.height - box[1]) / box[3];
            if (x < 0 || x > 1 || y < 0 || y > 1) { hideProbe(); return; }
            var bounds = grid.bounds, lon = bounds[0] + x * (bounds[1] - bounds[0]);
            var lat = bounds[3] - y * (bounds[3] - bounds[2]);
            var value = grid.values[nearest(grid.lats, lat)][nearest(grid.lons, lon)];
            if (value == null || !Number.isFinite(Number(value))) { hideProbe(); return; }
            var unit = manifest.products[productKey].unit;
            var shown = unit === 'km/h' ? Math.round(Number(value) / 5) * 5 : Math.round(Number(value) * 10) / 10;
            probe.querySelector('strong').textContent = shown.toLocaleString('fr-FR') + ' ' + unit;
            probe.querySelector('span').textContent = manifest.products[productKey].label + ' · H+' + lead;
            probe.hidden = false;
            var left = event.clientX - viewer.left + 14, top = event.clientY - viewer.top + 14;
            if (left + probe.offsetWidth > viewer.width - 8) { left -= probe.offsetWidth + 28; }
            if (top + probe.offsetHeight > viewer.height - 8) { top -= probe.offsetHeight + 28; }
            probe.style.left = Math.max(8, left) + 'px'; probe.style.top = Math.max(8, top) + 'px';
        }
        image.addEventListener('load', function () { status.textContent = ''; });
        image.addEventListener('error', function () { status.textContent = 'Carte temporairement indisponible.'; });
        image.addEventListener('pointerdown', function (event) {
            if (fixed || scale === 1) { return; } dragging = true;
            dragStart = [event.clientX - translateX, event.clientY - translateY]; image.setPointerCapture(event.pointerId); transform();
        });
        image.addEventListener('pointermove', function (event) {
            if (dragging) { translateX = event.clientX - dragStart[0]; translateY = event.clientY - dragStart[1]; transform(); hideProbe(); }
            else { showProbe(event); }
        });
        image.addEventListener('pointerup', function (event) { dragging = false; transform(); showProbe(event); });
        image.addEventListener('pointerleave', hideProbe);
        image.addEventListener('wheel', function (event) {
            if (fixed) { return; } event.preventDefault(); scale = Math.max(1, Math.min(5, scale + (event.deltaY < 0 ? .2 : -.2))); transform();
        }, { passive: false });
        widget.querySelectorAll('[data-zoom]').forEach(function (button) {
            button.addEventListener('click', function () {
                if (button.dataset.zoom === 'reset') { reset(); return; }
                scale = Math.max(1, Math.min(5, scale + (button.dataset.zoom === 'in' ? .35 : -.35))); transform();
            });
        });
        if (regions) { regions.querySelectorAll('button').forEach(function (button) { button.addEventListener('click', function () { region = button.dataset.region; render(); }); }); }
        fetchJson(base + 'maps/manifest.json').then(function (payload) { manifest = payload; build(); })
            .catch(function () { status.textContent = 'Les cartes seront disponibles après la prochaine production GitHub.'; });
    }
    function start() { document.querySelectorAll('[data-icong-map]').forEach(init); }
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', start); } else { start(); }
}());
