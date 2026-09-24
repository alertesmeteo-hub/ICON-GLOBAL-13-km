<?php
/**
 * Plugin Name: ICON-GLOBAL DWD France — Prévisions communales
 * Plugin URI: https://github.com/alertesmeteo-hub/ICON-GLOBAL-13-km
 * Description: Prévisions communales horaires ICON-GLOBAL de DWD pour la France métropolitaine et la Corse.
 * Version: 2.0.0
 * Author: Alertes Météo Hub
 * Requires at least: 5.8
 * Requires PHP: 7.4
 * License: GPL-2.0-or-later
 */

if (!defined('ABSPATH')) {
    exit;
}

define('ICONG_VERSION', '2.0.0');
define('ICONG_RELEASE_DATE', '24/09/2026');
define('ICONG_OPTION_BASE_URL', 'icong_national_data_base_url');
define(
    'ICONG_DEFAULT_BASE_URL',
    'https://raw.githubusercontent.com/alertesmeteo-hub/ICON-GLOBAL-13-km/data'
);

add_action('wp_enqueue_scripts', 'icong_register_assets');
add_action('admin_init', 'icong_register_settings');
add_action('admin_menu', 'icong_add_settings_page');
add_shortcode('icon_global_meteo', 'icong_render_shortcode');
add_filter('plugin_action_links_' . plugin_basename(__FILE__), 'icong_plugin_action_links');

function icong_plugin_action_links($links) {
    $settings_link = sprintf(
        '<a href="%s">%s</a>',
        esc_url(admin_url('options-general.php?page=icon-global-13-km')),
        esc_html__('Réglages', 'icon-global-13-km')
    );
    array_unshift($links, $settings_link);

    $help_link = sprintf(
        '<a href="%s">%s</a>',
        esc_url(admin_url('options-general.php?page=icon-global-13-km')),
        esc_html__('Shortcodes / Aide', 'icon-global-13-km')
    );
    array_unshift($links, $help_link);

    return $links;
}

function icong_register_assets() {
    wp_register_style(
        'icong-table',
        plugin_dir_url(__FILE__) . 'assets/arome-meteo.css',
        array(),
        ICONG_VERSION
    );
    wp_register_script(
        'icong-table',
        plugin_dir_url(__FILE__) . 'assets/arome-meteo.js',
        array(),
        ICONG_VERSION,
        true
    );
    wp_register_script(
        'icong-maps',
        plugin_dir_url(__FILE__) . 'assets/icon-global-maps.js',
        array(),
        ICONG_VERSION,
        true
    );

}

function icong_register_settings() {
    register_setting(
        'icong_settings',
        ICONG_OPTION_BASE_URL,
        array(
            'type' => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default' => ICONG_DEFAULT_BASE_URL,
        )
    );

    add_settings_section(
        'icong_main_section',
        'Source des données nationales',
        '__return_false',
        'icon-global-13-km'
    );

    add_settings_field(
        'icong_data_base_url_field',
        'Adresse du dossier de données',
        'icong_render_url_field',
        'icon-global-13-km',
        'icong_main_section'
    );
}

function icong_render_url_field() {
    $value = get_option(ICONG_OPTION_BASE_URL, ICONG_DEFAULT_BASE_URL);
    printf(
        '<input type="url" class="regular-text code" name="%1$s" value="%2$s" autocomplete="off">',
        esc_attr(ICONG_OPTION_BASE_URL),
        esc_attr($value)
    );
    echo '<p class="description">Conservez l’adresse proposée : elle pointe vers la branche nationale « data » du dépôt.</p>';
}

function icong_add_settings_page() {
    add_options_page(
        'Tableau ICON-GLOBAL DWD France',
        'ICON-GLOBAL DWD',
        'manage_options',
        'icon-global-13-km',
        'icong_render_settings_page'
    );
}

function icong_render_settings_page() {
    if (!current_user_can('manage_options')) {
        return;
    }
    ?>
    <div class="wrap">
        <h1>ICON-GLOBAL DWD France</h1>
        <form action="options.php" method="post">
            <?php
            settings_fields('icong_settings');
            do_settings_sections('icon-global-13-km');
            submit_button();
            ?>
        </form>
        <p><strong>Version du module : <?php echo esc_html(ICONG_VERSION); ?> (<?php echo esc_html(ICONG_RELEASE_DATE); ?>)</strong></p>
        <h2>Shortcode unique</h2>
        <p><code>[icon_global_meteo]</code> : prévisions générales, orages, neige et graphiques.</p>
        <p><code>[icon_global_meteo code="75056" departement="75" ville="Paris" heures="180"]</code></p>
        <p><code>[icon_global_meteo code="66136" departement="66" ville="Perpignan" selecteur="non"]</code> : une seule ville, sans recherche.</p>
        <p>Le visiteur peut ensuite rechercher n’importe quelle commune ou saisir un code postal.</p>
    </div>
    <?php
}

function icong_base_url() {
    $url = get_option(ICONG_OPTION_BASE_URL, ICONG_DEFAULT_BASE_URL);
    return untrailingslashit(apply_filters('icong_national_data_base_url', $url));
}

function icong_department_code($value) {
    $code = strtoupper(trim((string) $value));
    return preg_match('/^(?:\d{2}|2A|2B)$/', $code) ? $code : '66';
}

function icong_commune_code($value) {
    $code = strtoupper(trim((string) $value));
    return preg_match('/^[0-9A-Z]{5}$/', $code) ? $code : '66136';
}

function icong_unique_identifier() {
    if (function_exists('wp_unique_id')) {
        return wp_unique_id('icong-city-');
    }
    return 'icong-city-' . wp_rand(1000, 999999);
}

function icong_render_shortcode($atts) {
    $atts = shortcode_atts(
        array(
            'ville' => 'Perpignan',
            'code' => '66136',
            'departement' => '66',
            'heures' => '180',
            'titre' => '',
            'selecteur' => 'oui',
        ),
        $atts,
        'icon_global_meteo'
    );

    $hours = max(1, min(180, absint($atts['heures'])));
    $city_name = sanitize_text_field($atts['ville']);
    if ($city_name === '') {
        $city_name = 'Perpignan';
    }
    $city_code = icong_commune_code($atts['code']);
    $department = icong_department_code($atts['departement']);
    $title_prefix = trim(sanitize_text_field($atts['titre']));
    if ($title_prefix === '') {
        $title_prefix = 'Prévisions ICON-GLOBAL';
    }
    $selector_value = strtolower(trim(sanitize_text_field($atts['selecteur'])));
    $show_selector = !in_array($selector_value, array('non', '0', 'false', 'off'), true);

    $input_id = icong_unique_identifier();
    $results_id = $input_id . '-results';
    $status_id = $input_id . '-status';

    wp_enqueue_style('icong-table');
    wp_enqueue_script('icong-table');
    wp_enqueue_script('icong-maps');

    ob_start();
    ?>
    <section
        class="icong-card icong-national"
        data-icong-app
        data-base-url="<?php echo esc_url(icong_base_url()); ?>"
        data-default-code="<?php echo esc_attr($city_code); ?>"
        data-default-department="<?php echo esc_attr($department); ?>"
        data-default-name="<?php echo esc_attr($city_name); ?>"
        data-hours="<?php echo esc_attr($hours); ?>"
        data-timezone="<?php echo esc_attr(wp_timezone_string()); ?>"
        data-title-prefix="<?php echo esc_attr($title_prefix); ?>"
        data-selector="<?php echo $show_selector ? '1' : '0'; ?>"
    >
        <header class="icong-header">
            <div>
                <p class="icong-kicker">MODÈLE GLOBAL DWD • FRANCE ET EUROPE</p>
                <h2 data-icong-title><?php echo esc_html($title_prefix . ' — ' . $city_name); ?></h2>
                <p class="icong-city-altitude" data-icong-altitude>Altitude de <?php echo esc_html($city_name); ?> : chargement…</p>
                <p class="icong-meta" data-icong-meta>Chargement du dernier run ICON-GLOBAL…</p>
            </div>
            <div class="icong-badge">ICON-GLOBAL<br><strong>13 km</strong></div>
        </header>

        <div class="icong-toolbar" <?php if (!$show_selector) : ?>hidden<?php endif; ?>>
            <div class="icong-search">
                <label for="<?php echo esc_attr($input_id); ?>">Choisissez votre commune</label>
                <div class="icong-search-control">
                    <span class="icong-search-icon" aria-hidden="true">⌕</span>
                    <input
                        id="<?php echo esc_attr($input_id); ?>"
                        class="icong-city-input"
                        type="search"
                        value="<?php echo esc_attr($city_name); ?>"
                        placeholder="Nom de commune ou code postal"
                        autocomplete="off"
                        spellcheck="false"
                        role="combobox"
                        aria-autocomplete="list"
                        aria-expanded="false"
                        aria-controls="<?php echo esc_attr($results_id); ?>"
                        aria-describedby="<?php echo esc_attr($status_id); ?>"
                    >
                </div>
                <button type="button" class="icong-locate-button" data-icong-locate>📍 Détecter ma ville</button>
                <div
                    id="<?php echo esc_attr($results_id); ?>"
                    class="icong-search-results"
                    role="listbox"
                    hidden
                ></div>
                <p
                    id="<?php echo esc_attr($status_id); ?>"
                    class="icong-search-status"
                    role="status"
                    aria-live="polite"
                >Saisissez au moins deux lettres ou un code postal.</p>
            </div>
            <div class="icong-coverage">
                <strong>34 746 communes</strong>
                <span>Métropole et Corse</span>
            </div>
        </div>

        <p class="icong-stale" data-icong-stale role="status" hidden>
            Attention : la dernière mise à jour disponible a plus de 8 heures.
        </p>

        <p>Au-delà de +78 h : valeurs horaires interpolées, pluie et neige réparties sur trois heures ; rafales affichées uniquement aux heures couvertes par les données sources.</p>
        <div class="icong-tabs" role="tablist" aria-label="Type de prévision ICON-GLOBAL">
            <button type="button" class="icong-tab icong-tab-map is-active" role="tab" aria-selected="true" data-icong-tab="map-fixed">Europe/France</button>
            <button type="button" class="icong-tab icong-tab-map" role="tab" aria-selected="false" data-icong-tab="map-france">France Zoom interactif</button>
            <button type="button" class="icong-tab icong-tab-map" role="tab" aria-selected="false" data-icong-tab="map-europe">Europe Zoom interactif</button>
            <span class="icong-table-label">TABLEAU :</span>
            <button
                type="button"
                class="icong-tab"
                role="tab"
                aria-selected="false"
                data-icong-tab="general"
            >🌤️ Général</button>
            <button
                type="button"
                class="icong-tab icong-tab-storm"
                role="tab"
                aria-selected="false"
                data-icong-tab="storms"
            >⛈️ Orages</button>
            <button
                type="button"
                class="icong-tab icong-tab-snow"
                role="tab"
                aria-selected="false"
                data-icong-tab="snow"
            >❄️ Neige</button>
        </div>

        <?php foreach (array('map-fixed' => array('france', '1'), 'map-france' => array('france', '0'), 'map-europe' => array('europe', '0')) as $map_view => $map_config) : ?>
        <section class="icong-panel icong-map-panel" data-icong-panel="<?php echo esc_attr($map_view); ?>" <?php if ($map_view !== 'map-fixed') : ?>hidden<?php endif; ?>>
            <div class="icong-map-widget" data-icong-map data-region="<?php echo esc_attr($map_config[0]); ?>" data-fixed="<?php echo esc_attr($map_config[1]); ?>">
                <div class="icong-map-tools">
                    <div class="icong-map-products" aria-label="Paramètre météo"></div>
                    <?php if ($map_config[1] === '1') : ?><div class="icong-map-regions"><button type="button" data-region="france" aria-pressed="true">France</button><button type="button" data-region="europe" aria-pressed="false">Europe</button></div><?php endif; ?>
                    <div class="icong-map-leads" aria-label="Échéance"></div>
                </div>
                <p class="icong-map-summary"></p>
                <div class="icong-map-viewer">
                    <img class="icong-map-image" alt="Carte ICON-GLOBAL 13 km">
                    <div class="icong-map-probe" hidden><strong></strong><span></span></div>
                    <?php if ($map_config[1] === '0') : ?><div class="icong-map-zoom"><button type="button" data-zoom="in">+</button><button type="button" data-zoom="out">−</button><button type="button" data-zoom="reset">⌂</button></div><?php endif; ?>
                    <p class="icong-map-status" role="status">Chargement de la carte…</p>
                </div>
            </div>
        </section>
        <?php endforeach; ?>

        <div class="icong-panel" data-icong-panel="general" hidden>
            <div class="icong-table-wrap icong-general-wrap" role="region" aria-label="Prévisions horaires générales" tabindex="0">
                <table class="icong-table">
                    <thead>
                        <tr>
                            <th scope="col">Date</th>
                            <th scope="col">Heure</th>
                            <th scope="col">Temps</th>
                            <th scope="col">T°</th>
                            <th scope="col">Hum.</th>
                            <th scope="col">Pluie</th>
                            <th scope="col">Nuages</th>
                            <th scope="col">Vent</th>
                            <th scope="col">Rafales</th>
                            <th scope="col">Pression</th>
                        </tr>
                    </thead>
                    <tbody data-icong-body-general>
                        <tr>
                            <td colspan="10" class="icong-loading">Chargement des prévisions…</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <section class="icong-charts" data-icong-charts aria-label="Diagrammes ICON-GLOBAL">
                <article class="icong-chart-card">
                    <h3 data-icong-chart-title-temperature>Diagramme températures (°C)</h3>
                    <div class="icong-chart" data-icong-chart-temperature></div>
                </article>
                <article class="icong-chart-card">
                    <h3 data-icong-chart-title-pressure>Diagramme pression ramenée au niveau de la mer (hPa)</h3>
                    <div class="icong-chart" data-icong-chart-pressure></div>
                </article>
                <article class="icong-chart-card">
                    <h3 data-icong-chart-title-rain>Diagramme précipitations (mm)</h3>
                    <p class="icong-chart-total" data-icong-rain-total>Précipitations cumulées : —</p>
                    <div class="icong-chart" data-icong-chart-rain></div>
                </article>
                <article class="icong-chart-card">
                    <h3 data-icong-chart-title-wind>Diagramme rafales et vent moyen</h3>
                    <div class="icong-chart" data-icong-chart-wind></div>
                </article>
            </section>
        </div>

        <div class="icong-panel" data-icong-panel="storms" hidden>
            <p class="icong-storm-summary" data-icong-storm-summary>
                Diagnostic convectif ICON-GLOBAL 13 km : chargement…
            </p>
            <div class="icong-top-scroll" data-icong-top-scroll="storms" aria-label="Navigation horizontale du tableau orages" hidden><div></div></div>
            <div class="icong-table-wrap icong-storm-wrap" data-icong-scroll-wrap="storms" role="region" aria-label="Prévisions horaires d'orages" tabindex="0">
                <table class="icong-table icong-storm-table">
                    <thead>
                        <tr>
                            <th scope="col">Date</th>
                            <th scope="col">Heure</th>
                            <th scope="col">Risque orage</th>
                            <th scope="col">CAPE</th>
                            <th scope="col">LCL estimé</th>
                            <th scope="col">Foudre</th>
                            <th scope="col">Grêle</th>
                            <th scope="col">Pluie conv.</th>
                            <th scope="col">Graupel</th>
                            <th scope="col">Pluie 1 h</th>
                            <th scope="col">Rafales</th>
                            <th scope="col">Type</th>
                            <th scope="col">Détails</th>
                        </tr>
                    </thead>
                    <tbody data-icong-body-storms>
                        <tr>
                            <td colspan="13" class="icong-loading">Chargement du diagnostic orageux…</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <p class="icong-storm-note">
                <strong>Lecture expert :</strong> la CAPE de couche mélangée est une sortie directe ICON-GLOBAL. Le risque orage est indicatif et dérivé de la CAPE et des rafales. La réflectivité, la foudre, la grêle et le type d’orage sont indisponibles et affichés par un tiret.
            </p>
        </div>

        <div class="icong-panel" data-icong-panel="snow" hidden>
            <p class="icong-snow-summary" data-icong-snow-summary>
                Diagnostic neige ICON-GLOBAL 13 km : chargement…
            </p>
            <div class="icong-top-scroll" data-icong-top-scroll="snow" aria-label="Navigation horizontale du tableau neige" hidden><div></div></div>
            <div class="icong-table-wrap icong-snow-wrap" data-icong-scroll-wrap="snow" role="region" aria-label="Risque horaire de neige" tabindex="0">
                <table class="icong-table icong-snow-table">
                    <thead>
                        <tr>
                            <th scope="col">Date</th>
                            <th scope="col">Heure</th>
                            <th scope="col">Risque neige</th>
                            <th scope="col">Phase</th>
                            <th scope="col">Neige 1 h</th>
                            <th scope="col">Neige 3 h</th>
                            <th scope="col">Neige 6 h</th>
                            <th scope="col">Tenue</th>
                            <th scope="col">Pres. hPa</th>
                            <th scope="col">Hum.</th>
                            <th scope="col">Vent moy. / raf.</th>
                            <th scope="col">Cumul neige fraîche</th>
                            <th scope="col">Détails</th>
                        </tr>
                    </thead>
                    <tbody data-icong-body-snow>
                        <tr>
                            <td colspan="13" class="icong-loading">Chargement du risque de neige…</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <p class="icong-snow-note">
                <strong>Lecture neige :</strong> les cumuls de neige sont des sorties directes ICON-GLOBAL. La neige fraîche et la tenue sont estimées à partir du cumul en eau, de la température à 2 m et de l’altitude du point de grille.
            </p>
        </div>

        <footer class="icong-footer">
            <span data-icong-generated>Mise à jour en cours de lecture…</span>
            <span>
                Données météo directes :
                <a href="https://opendata.dwd.de/weather/nwp/icon/grib/" target="_blank" rel="noopener noreferrer">ICON-GLOBAL 13 km — DWD Open Data</a>
                • Recherche des communes :
                <a href="https://geo.api.gouv.fr/decoupage-administratif/communes" target="_blank" rel="noopener noreferrer">API officielle française</a>
                • <strong class="icong-brand">www.alertes-meteo.com</strong>
            </span>
            <span class="icong-plugin-version">Module ICON-GLOBAL v<?php echo esc_html(ICONG_VERSION); ?> (<?php echo esc_html(ICONG_RELEASE_DATE); ?>)</span>
        </footer>

        <noscript>
            <p class="icong-message icong-error">JavaScript doit être activé pour rechercher une commune.</p>
        </noscript>
    </section>
    <?php
    return ob_get_clean();
}
