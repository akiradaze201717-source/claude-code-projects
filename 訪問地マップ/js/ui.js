// ui.js — UI操作（モーダル・フォーム・写真処理）
const UI = {
  pendingPhotoBlob: null,
  deleteTargetId: null,

  init() {
    // モーダル制御
    document.getElementById('modal-close').addEventListener('click', () => this.closeModal());
    document.getElementById('btn-cancel').addEventListener('click', () => this.closeModal());
    document.getElementById('modal-overlay').addEventListener('click', (e) => {
      if (e.target === e.currentTarget) this.closeModal();
    });

    // 写真選択
    document
      .getElementById('pin-photo')
      .addEventListener('change', (e) => this._handlePhotoSelect(e));
    document.getElementById('photo-remove').addEventListener('click', () => this._removePhoto());

    // フォーム送信
    document.getElementById('pin-form').addEventListener('submit', (e) => this._handleSubmit(e));

    // FABボタン
    document.getElementById('fab-add').addEventListener('click', () => {
      MapManager.goToCurrentLocation();
    });

    // 削除確認
    document
      .getElementById('delete-cancel')
      .addEventListener('click', () => this.closeDeleteModal());
    document
      .getElementById('delete-confirm')
      .addEventListener('click', () => this._executeDelete());
    document.getElementById('delete-overlay').addEventListener('click', (e) => {
      if (e.target === e.currentTarget) this.closeDeleteModal();
    });

    // Escキーでモーダルを閉じる
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.closeModal();
        this.closeDeleteModal();
      }
    });
  },

  openModal(lat, lng) {
    document.getElementById('pin-lat').value = lat;
    document.getElementById('pin-lng').value = lng;
    document.getElementById('location-display').textContent =
      `緯度: ${lat.toFixed(6)}, 経度: ${lng.toFixed(6)}`;
    document.getElementById('modal-overlay').classList.remove('hidden');
    document.getElementById('pin-title').focus();
  },

  closeModal() {
    document.getElementById('modal-overlay').classList.add('hidden');
    document.getElementById('pin-form').reset();
    this._removePhoto();
  },

  confirmDelete(pinId) {
    this.deleteTargetId = pinId;
    // ポップアップを閉じる
    MapManager.map.closePopup();
    document.getElementById('delete-overlay').classList.remove('hidden');
  },

  closeDeleteModal() {
    document.getElementById('delete-overlay').classList.add('hidden');
    this.deleteTargetId = null;
  },

  async _executeDelete() {
    if (this.deleteTargetId === null) return;
    const id = this.deleteTargetId;
    await PinDB.delete(id);
    MapManager.removeMarker(id);
    this.closeDeleteModal();
  },

  async _handleSubmit(e) {
    e.preventDefault();

    const title = document.getElementById('pin-title').value.trim();
    if (!title) return;

    const pinData = {
      lat: parseFloat(document.getElementById('pin-lat').value),
      lng: parseFloat(document.getElementById('pin-lng').value),
      title: title,
      memo: document.getElementById('pin-memo').value.trim(),
      photoBlob: this.pendingPhotoBlob,
    };

    const id = await PinDB.add(pinData);
    const savedPin = await PinDB.getById(id);
    MapManager.addMarker(savedPin);

    this.closeModal();
  },

  async _handlePhotoSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    // 画像ファイルかチェック
    if (!file.type.startsWith('image/')) {
      alert('画像ファイルを選択してください。');
      e.target.value = '';
      return;
    }

    try {
      const resizedBlob = await this._resizeImage(file, 800);
      this.pendingPhotoBlob = resizedBlob;

      // プレビュー表示
      const previewImg = document.getElementById('preview-img');
      previewImg.src = URL.createObjectURL(resizedBlob);
      document.getElementById('photo-preview').classList.remove('hidden');

      // EXIF GPS取得
      try {
        const gps = await exifr.gps(file);
        if (gps && gps.latitude && gps.longitude) {
          document.getElementById('pin-lat').value = gps.latitude;
          document.getElementById('pin-lng').value = gps.longitude;
          document.getElementById('location-display').textContent =
            `📷 写真の位置情報: 緯度 ${gps.latitude.toFixed(6)}, 経度 ${gps.longitude.toFixed(6)}`;
          MapManager.map.setView([gps.latitude, gps.longitude], 15);
        }
      } catch (_) {
        // GPS情報なし、無視
      }
    } catch (err) {
      alert('画像の読み込みに失敗しました。');
      e.target.value = '';
    }
  },

  _removePhoto() {
    this.pendingPhotoBlob = null;
    document.getElementById('pin-photo').value = '';
    document.getElementById('photo-preview').classList.add('hidden');
    const previewImg = document.getElementById('preview-img');
    if (previewImg.src) {
      URL.revokeObjectURL(previewImg.src);
      previewImg.src = '';
    }
  },

  _resizeImage(file, maxSize) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const reader = new FileReader();

      reader.onload = (e) => {
        img.onload = () => {
          let { width, height } = img;

          // 長辺がmaxSize以下ならリサイズ不要
          if (width <= maxSize && height <= maxSize) {
            resolve(file);
            return;
          }

          // アスペクト比を維持してリサイズ
          if (width > height) {
            height = Math.round((height * maxSize) / width);
            width = maxSize;
          } else {
            width = Math.round((width * maxSize) / height);
            height = maxSize;
          }

          const canvas = document.createElement('canvas');
          canvas.width = width;
          canvas.height = height;

          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, width, height);

          canvas.toBlob(
            (blob) => {
              if (blob) resolve(blob);
              else reject(new Error('Canvas toBlob failed'));
            },
            'image/jpeg',
            0.85,
          );
        };
        img.onerror = reject;
        img.src = e.target.result;
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  },
};
