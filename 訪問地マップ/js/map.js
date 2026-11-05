// map.js — 地図操作 (Leaflet)
const MapManager = {
  map: null,
  markers: {},
  pendingLatLng: null,

  init() {
    this.map = L.map('map').setView([35.6762, 139.6503], 12);

    // タイルレイヤーはテーマ管理に委譲（着せ替え対応）
    ThemeManager.applyToMap(this.map);

    // 地図クリックでピン追加
    this.map.on('click', (e) => {
      this.pendingLatLng = e.latlng;
      UI.openModal(e.latlng.lat, e.latlng.lng);
    });
  },

  updateCounter() {
    document.getElementById('counter-num').textContent = Object.keys(this.markers).length;
  },

  _pinIcon() {
    return L.divIcon({
      className: 'pin-icon',
      html: '<span class="map-pin"></span>',
      iconSize: [16, 16],
      iconAnchor: [8, 8],
      popupAnchor: [0, -12],
    });
  },

  addMarker(pin) {
    const marker = L.marker([pin.lat, pin.lng], { icon: this._pinIcon() }).addTo(this.map);

    let popupContent = '<div class="popup-content">';
    if (pin.photoBlob) {
      const url = URL.createObjectURL(pin.photoBlob);
      popupContent += `<img src="${url}" alt="${this._escapeHtml(pin.title)}" class="popup-photo" loading="lazy">`;
    }
    popupContent += `<h3 class="popup-title">${this._escapeHtml(pin.title)}</h3>`;
    if (pin.memo) {
      popupContent += `<p class="popup-memo">${this._escapeHtml(pin.memo)}</p>`;
    }
    popupContent += `<div class="popup-meta">${this._formatDate(pin.createdAt)}</div>`;
    popupContent += `<button class="btn btn-danger btn-small popup-delete" data-pin-id="${pin.id}">削除</button>`;
    popupContent += '</div>';

    marker.bindPopup(popupContent, { maxWidth: 250, minWidth: 160, autoPanPadding: [20, 20] });

    marker.on('popupopen', () => {
      const deleteBtn = document.querySelector(`.popup-delete[data-pin-id="${pin.id}"]`);
      if (deleteBtn) {
        deleteBtn.addEventListener('click', () => {
          UI.confirmDelete(pin.id);
        });
      }
    });

    this.markers[pin.id] = marker;
    this.updateCounter();
  },

  removeMarker(id) {
    if (this.markers[id]) {
      this.map.removeLayer(this.markers[id]);
      delete this.markers[id];
      this.updateCounter();
    }
  },

  async loadAllPins() {
    const pins = await PinDB.getAll();
    pins.forEach((pin) => this.addMarker(pin));
  },

  goToCurrentLocation() {
    if (!navigator.geolocation) {
      alert('お使いのブラウザは位置情報に対応していません。');
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        this.map.setView([latitude, longitude], 15);
        this.pendingLatLng = L.latLng(latitude, longitude);
        UI.openModal(latitude, longitude);
      },
      (err) => {
        switch (err.code) {
          case err.PERMISSION_DENIED:
            alert(
              '位置情報の取得が許可されていません。\n地図をタップして手動でピンを追加できます。',
            );
            break;
          case err.POSITION_UNAVAILABLE:
            alert('位置情報を取得できませんでした。');
            break;
          case err.TIMEOUT:
            alert('位置情報の取得がタイムアウトしました。');
            break;
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  },

  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },

  _formatDate(isoString) {
    const d = new Date(isoString);
    return `${d.getFullYear()}/${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')}`;
  },
};
