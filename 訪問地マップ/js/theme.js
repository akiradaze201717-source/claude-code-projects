// theme.js — 地図テーマ（タイル着せ替え）管理
const ThemeManager = {
  STORAGE_KEY: 'visitedMap.theme',
  map: null,
  current: 'voyager',
  _layer: null,

  // CARTO / OSM の無料タイル（APIキー不要）。雰囲気の差はCSSフィルタで付ける
  themes: {
    voyager: {
      name: 'デフォルト',
      swatch: '#5b8def',
      tile: {
        url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20,
      },
    },
    dark: {
      name: 'ダークマター',
      swatch: '#0b1020',
      tile: {
        url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20,
      },
    },
    neon: {
      name: 'ネオン',
      swatch: '#ff2bd6',
      // ダークタイルにCSSで色相回転をかけてサイバー風に
      tile: {
        url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20,
      },
    },
    vintage: {
      name: 'ヴィンテージ',
      swatch: '#b5793f',
      // 明るいタイルにセピアフィルタで古地図風に
      tile: {
        url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20,
      },
    },
    mono: {
      name: 'モノクロ',
      swatch: '#3a3a3a',
      tile: {
        url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20,
      },
    },
  },

  order: ['voyager', 'dark', 'neon', 'vintage', 'mono'],

  getSaved() {
    const t = localStorage.getItem(this.STORAGE_KEY);
    return t && this.themes[t] ? t : 'voyager';
  },

  // 地図生成直後に初期テーマを適用
  applyToMap(map) {
    this.map = map;
    this.current = this.getSaved();
    this._setTileLayer(this.current);
    this._setBodyTheme(this.current);
  },

  _setTileLayer(id) {
    const t = this.themes[id];
    if (this._layer) this.map.removeLayer(this._layer);
    this._layer = L.tileLayer(t.tile.url, {
      attribution: t.tile.attribution,
      subdomains: t.tile.subdomains || 'abc',
      maxZoom: t.tile.maxZoom || 19,
    }).addTo(this.map);
  },

  _setBodyTheme(id) {
    document.body.dataset.theme = id;
  },

  set(id) {
    if (!this.themes[id]) return;
    this.current = id;
    localStorage.setItem(this.STORAGE_KEY, id);
    this._setTileLayer(id);
    this._setBodyTheme(id);
    this._markActive();
  },

  // 右上のテーマ切り替えUIを構築
  buildSwitcher() {
    const btn = document.getElementById('theme-toggle');
    const panel = document.getElementById('theme-panel');
    if (!btn || !panel) return;

    this.order.forEach((id) => {
      const t = this.themes[id];
      const opt = document.createElement('button');
      opt.type = 'button';
      opt.className = 'theme-option';
      opt.dataset.theme = id;
      opt.innerHTML =
        `<span class="theme-swatch" style="background:${t.swatch}"></span>` +
        `<span class="theme-name">${t.name}</span>`;
      opt.addEventListener('click', () => {
        this.set(id);
        panel.classList.add('hidden');
      });
      panel.appendChild(opt);
    });

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      panel.classList.toggle('hidden');
      this._markActive();
    });

    // パネル外クリックで閉じる
    document.addEventListener('click', () => panel.classList.add('hidden'));
    panel.addEventListener('click', (e) => e.stopPropagation());

    this._markActive();
  },

  _markActive() {
    document.querySelectorAll('.theme-option').forEach((el) => {
      el.classList.toggle('active', el.dataset.theme === this.current);
    });
  },
};
