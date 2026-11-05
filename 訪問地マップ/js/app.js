// app.js — アプリ初期化
document.addEventListener('DOMContentLoaded', async () => {
  MapManager.init();
  ThemeManager.buildSwitcher();
  UI.init();
  await MapManager.loadAllPins();
});
