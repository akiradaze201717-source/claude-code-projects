import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'life-rpg-v1';

const STATS_DEF = [
  { key: 'intel', label: '知識', icon: '📖', color: '#88ccff' },
  { key: 'strength', label: '体力', icon: '❤️', color: '#ff6666' },
  { key: 'wealth', label: '財力', icon: '💰', color: '#ffdd44' },
  { key: 'tech', label: '技術', icon: '⚙️', color: '#88ffcc' },
  { key: 'lingua', label: '言語', icon: '🌐', color: '#cc88ff' },
  { key: 'life', label: '生活', icon: '🌿', color: '#88ff88' },
];

const CLASSES = [
  { id: 'engineer', label: '機械エンジニア', icon: '⚙️', req: { intel: 20, tech: 15 } },
  { id: 'investor', label: '投資家', icon: '📈', req: { intel: 15, wealth: 20 } },
  { id: 'scholar', label: '学者', icon: '📚', req: { intel: 30 } },
  { id: 'athlete', label: '戦士', icon: '⚔️', req: { strength: 25 } },
  { id: 'polyglot', label: '言語使い', icon: '🌍', req: { lingua: 25 } },
  { id: 'hacker', label: 'テックハッカー', icon: '💻', req: { tech: 30, intel: 10 } },
  { id: 'sage', label: '賢者', icon: '🔮', req: { intel: 40, lingua: 20, tech: 20 } },
  { id: 'adventurer', label: '冒険者', icon: '🗡️', req: {} },
];

const TITLES_DEF = [
  { id: 'first_blood', label: '最初の一歩', icon: '🩸', condition: (s) => s.totalXp >= 1 },
  { id: 'grinder', label: '勤勉なる者', icon: '⚒️', condition: (s) => s.dailyDone >= 30 },
  { id: 'brainiac', label: '知識の探求者', icon: '🧬', condition: (s) => s.stats.intel >= 50 },
  { id: 'iron_will', label: '鋼の意志', icon: '🦾', condition: (s) => s.stats.strength >= 50 },
  { id: 'moneymind', label: 'マネーマインド', icon: '🏦', condition: (s) => s.stats.wealth >= 50 },
  { id: 'level10', label: 'Lv.10達成', icon: '⭐', condition: (s) => s.level >= 10 },
  { id: 'level25', label: 'Lv.25達成', icon: '🌟', condition: (s) => s.level >= 25 },
  { id: 'weekly_hero', label: '週間英雄', icon: '🦸', condition: (s) => s.weeklyDone >= 10 },
  {
    id: 'allstat',
    label: 'オールラウンダー',
    icon: '🎯',
    condition: (s) => Object.values(s.stats).every((v) => v >= 10),
  },
  { id: 'streak7', label: '7日連続', icon: '🔥', condition: (s) => s.streak >= 7 },
  { id: 'xp1000', label: 'XP 1000突破', icon: '💎', condition: (s) => s.totalXp >= 1000 },
];

// 曜日取得（0=日,1=月...5=金,6=土）
function getDayOfWeek() {
  return new Date().getDay();
}

// 曜日ごとの授業デイリークエスト
const LECTURE_BY_DAY = {
  1: [
    // 月
    {
      id: 'lec_mon1',
      text: 'コンピュータプログラミング 予習・復習',
      xp: 35,
      stat: 'intel',
      icon: '💻',
    },
    { id: 'lec_mon2', text: '流体力学 予習・復習', xp: 40, stat: 'intel', icon: '🌊' },
  ],
  2: [
    // 火
    { id: 'lec_tue1', text: '制御工学I 予習・復習', xp: 35, stat: 'intel', icon: '🎛️' },
  ],
  3: [
    // 水
    { id: 'lec_wed2', text: '機械力学I 予習・復習', xp: 35, stat: 'intel', icon: '🔩' },
    { id: 'lec_wed3', text: '電気回路 予習・復習', xp: 30, stat: 'intel', icon: '⚡' },
  ],
  4: [
    // 木
    { id: 'lec_thu1', text: '信号センシングと解析 予習・復習', xp: 35, stat: 'intel', icon: '📡' },
    { id: 'lec_thu2', text: '機械材料I 予習・復習', xp: 30, stat: 'intel', icon: '🔬' },
  ],
  5: [
    // 金
    { id: 'lec_fri1', text: 'メカトロニクスI 予習・復習', xp: 35, stat: 'tech', icon: '🤖' },
    { id: 'lec_fri2', text: '熱力学II 予習・復習', xp: 40, stat: 'intel', icon: '🔥' },
  ],
};

const DAILY_TEMPLATES_BASE = [
  { id: 'd2', text: '水を2L飲む', xp: 10, stat: 'life', icon: '💧' },
  { id: 'd3', text: '30分以上歩く／バスケ', xp: 20, stat: 'strength', icon: '🏃' },
  { id: 'd4', text: 'TOEIC単語10個', xp: 20, stat: 'lingua', icon: '📝' },
  { id: 'd5', text: '投資チェック（10分）', xp: 15, stat: 'wealth', icon: '📈' },
  { id: 'd6', text: 'Obsidianにメモ記録', xp: 10, stat: 'tech', icon: '🗒️' },
  { id: 'd7', text: '7時間以上睡眠', xp: 15, stat: 'life', icon: '😴' },
];

// 当日の授業クエスト＋ベースクエストを結合
function getDailyTemplates() {
  const day = getDayOfWeek();
  const lectures = LECTURE_BY_DAY[day] || [];
  return [...lectures, ...DAILY_TEMPLATES_BASE];
}

const DAILY_TEMPLATES = getDailyTemplates();

const WEEKLY_TEMPLATES = [
  {
    id: 'w_lec1',
    text: 'コンピュータプログラミング 週まとめ復習',
    xp: 60,
    stat: 'intel',
    icon: '💻',
  },
  { id: 'w_lec2', text: '流体力学 週まとめ復習', xp: 70, stat: 'intel', icon: '🌊' },
  { id: 'w_lec3', text: '制御工学I 週まとめ復習', xp: 60, stat: 'intel', icon: '🎛️' },
  { id: 'w_lec5', text: '機械力学I 週まとめ復習', xp: 60, stat: 'intel', icon: '🔩' },
  { id: 'w_lec6', text: '電気回路 週まとめ復習', xp: 50, stat: 'intel', icon: '⚡' },
  { id: 'w_lec7', text: '信号センシングと解析 週まとめ復習', xp: 60, stat: 'intel', icon: '📡' },
  { id: 'w_lec8', text: '機械材料I 週まとめ復習', xp: 50, stat: 'intel', icon: '🔬' },
  { id: 'w_lec9', text: 'メカトロニクスI 週まとめ復習', xp: 60, stat: 'tech', icon: '🤖' },
  { id: 'w_lec10', text: '熱力学II 週まとめ復習', xp: 70, stat: 'intel', icon: '🔥' },
  { id: 'w1', text: '課題・レポートを完成させる', xp: 120, stat: 'intel', icon: '📄' },
  { id: 'w3', text: '差動歯車の設計を進める', xp: 100, stat: 'tech', icon: '⚙️' },
  { id: 'w4', text: '3日以上運動する', xp: 80, stat: 'strength', icon: '🏋️' },
  { id: 'w5', text: '株のスクリーニングをまとめる', xp: 80, stat: 'wealth', icon: '💹' },
  { id: 'w6', text: '英語コンテンツを1本消化', xp: 60, stat: 'lingua', icon: '🎧' },
  { id: 'w7', text: 'Claudeで新しいツールを作る', xp: 90, stat: 'tech', icon: '🤖' },
];

const STAT_COLOR = Object.fromEntries(STATS_DEF.map((s) => [s.key, s.color]));
const TABS = [
  { id: 'home', label: 'ステータス', icon: '👤' },
  { id: 'daily', label: 'デイリー', icon: '📋' },
  { id: 'weekly', label: '週間', icon: '📅' },
  { id: 'status', label: '能力', icon: '⚔️' },
  { id: 'achieve', label: '実績', icon: '🏆' },
];

function xpToLevel(xp) {
  return Math.floor(Math.sqrt(xp / 50)) + 1;
}
function levelToXp(lv) {
  return (lv - 1) ** 2 * 50;
}
function todayStr() {
  return new Date().toISOString().slice(0, 10);
}
function weekKey() {
  const d = new Date();
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(new Date().setDate(diff)).toISOString().slice(0, 10);
}
function getClass(stats) {
  const unlocked = CLASSES.filter((c) =>
    Object.entries(c.req).every(([k, v]) => (stats[k] || 0) >= v),
  );
  return (
    unlocked.sort(
      (a, b) =>
        Object.values(b.req).reduce((s, v) => s + v, 0) -
        Object.values(a.req).reduce((s, v) => s + v, 0),
    )[0] || CLASSES.find((c) => c.id === 'adventurer')
  );
}
function defaultState() {
  return {
    totalXp: 0,
    level: 1,
    stats: { intel: 0, strength: 0, wealth: 0, tech: 0, lingua: 0, life: 0 },
    dailyDone: 0,
    weeklyDone: 0,
    streak: 0,
    lastDate: null,
    dailyChecked: {},
    weeklyChecked: {},
    customQuests: [],
    customDailyQuests: null,
    customWeeklyQuests: null,
    unlockedTitles: [],
    activeTitle: null,
    activeClass: 'adventurer',
    log: [],
  };
}
async function loadState() {
  try {
    const r = await window.storage.get(STORAGE_KEY);
    if (!r) return defaultState();
    const s = JSON.parse(r.value);
    if (s.dailyChecked)
      Object.keys(s.dailyChecked).forEach((k) => {
        s.dailyChecked[k] = new Set(s.dailyChecked[k]);
      });
    if (s.weeklyChecked)
      Object.keys(s.weeklyChecked).forEach((k) => {
        s.weeklyChecked[k] = new Set(s.weeklyChecked[k]);
      });
    return { ...defaultState(), ...s };
  } catch {
    return defaultState();
  }
}
async function saveState(s) {
  try {
    const toSave = { ...s };
    const dc = {};
    Object.keys(s.dailyChecked || {}).forEach((k) => {
      dc[k] = [
        ...(s.dailyChecked[k] instanceof Set ? s.dailyChecked[k] : new Set(s.dailyChecked[k])),
      ];
    });
    const wc = {};
    Object.keys(s.weeklyChecked || {}).forEach((k) => {
      wc[k] = [
        ...(s.weeklyChecked[k] instanceof Set ? s.weeklyChecked[k] : new Set(s.weeklyChecked[k])),
      ];
    });
    toSave.dailyChecked = dc;
    toSave.weeklyChecked = wc;
    await window.storage.set(STORAGE_KEY, JSON.stringify(toSave));
  } catch (e) {
    console.error(e);
  }
}

// ── Components ──
function DQBox({ children, style = {} }) {
  return (
    <div
      style={{
        position: 'relative',
        background: '#1a0e00',
        border: '4px solid #2a1a00',
        outline: '2px solid #8b6914',
        outlineOffset: '-6px',
        boxShadow: 'inset 2px 2px 0 #fff8e044, inset -2px -2px 0 #2a1a0088, 4px 4px 0 #00000088',
        padding: '12px 14px',
        imageRendering: 'pixelated',
        ...style,
      }}
    >
      {children}
    </div>
  );
}
function PixelBar({ value, max, color, height = 12 }) {
  const pct = Math.min(100, (value / Math.max(max, 1)) * 100);
  const segments = 20;
  return (
    <div style={{ display: 'flex', gap: 2, height }}>
      {Array.from({ length: segments }).map((_, i) => {
        const filled = (i / segments) * 100 < pct;
        return (
          <div
            key={i}
            style={{
              flex: 1,
              height: '100%',
              background: filled ? color : '#1a1200',
              border: `1px solid ${filled ? color + 'aa' : '#2a2000'}`,
              boxShadow: filled ? `0 0 4px ${color}88` : 'none',
            }}
          />
        );
      })}
    </div>
  );
}
function DQButton({ children, onClick, color = '#4488ff', style = {} }) {
  const [pressed, setPressed] = useState(false);
  return (
    <button
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      onMouseLeave={() => setPressed(false)}
      onClick={onClick}
      style={{
        background: pressed ? '#0a0600' : '#1a0e00',
        border: '3px solid #2a1a00',
        outline: `2px solid ${color}88`,
        outlineOffset: '-5px',
        boxShadow: pressed ? 'none' : `2px 2px 0 #00000099, inset 1px 1px 0 #fff8e022`,
        color,
        fontFamily: "'Press Start 2P', monospace",
        fontSize: 9,
        padding: '8px 12px',
        cursor: 'pointer',
        imageRendering: 'pixelated',
        transform: pressed ? 'translate(2px,2px)' : 'none',
        transition: 'none',
        letterSpacing: 1,
        ...style,
      }}
    >
      {children}
    </button>
  );
}
function MsgWindow({ lines }) {
  return (
    <DQBox style={{ marginBottom: 12 }}>
      {lines.map((l, i) => (
        <div
          key={i}
          style={{
            fontFamily: "'Press Start 2P', monospace",
            fontSize: 9,
            color: '#f8f0d0',
            lineHeight: 2,
            letterSpacing: 1,
          }}
        >
          {l}
        </div>
      ))}
    </DQBox>
  );
}

// ── クエスト編集フォーム（独立コンポーネント - 再レンダリング対策）──
function QuestEditForm({ quest, onSave, onCancel }) {
  const [text, setText] = useState(quest.text);
  const [xp, setXp] = useState(quest.xp);
  const [stat, setStat] = useState(quest.stat);
  return (
    <div style={{ background: '#2a1a00', border: '2px solid #ffe566', padding: '10px' }}>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        autoFocus
        style={{
          width: '100%',
          background: '#160e00',
          border: '2px solid #5a3e10',
          padding: '8px 10px',
          color: '#fff8e0',
          fontSize: 9,
          fontFamily: "'Press Start 2P', monospace",
          marginBottom: 8,
          outline: 'none',
          boxSizing: 'border-box',
        }}
      />
      <div style={{ display: 'flex', gap: 4, marginBottom: 8, flexWrap: 'wrap' }}>
        {STATS_DEF.map((s) => (
          <button
            key={s.key}
            onClick={() => setStat(s.key)}
            style={{
              background: stat === s.key ? '#2e1e00' : '#160e00',
              border: `2px solid ${stat === s.key ? s.color : '#5a3e10'}`,
              color: stat === s.key ? s.color : '#b09060',
              fontSize: 7,
              fontFamily: "'Press Start 2P', monospace",
              padding: '4px 7px',
              cursor: 'pointer',
            }}
          >
            {s.icon} {s.label}
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <span style={{ fontSize: 7, color: '#c8a96e', flexShrink: 0 }}>XP:</span>
        <input
          type="number"
          value={xp}
          onChange={(e) => setXp(e.target.value)}
          style={{
            width: 64,
            background: '#160e00',
            border: '2px solid #5a3e10',
            padding: '6px',
            color: '#ffe566',
            fontSize: 9,
            fontFamily: "'Press Start 2P', monospace",
            outline: 'none',
          }}
        />
        <button
          onClick={() =>
            onSave({ ...quest, text: text.trim() || quest.text, xp: Number(xp) || quest.xp, stat })
          }
          style={{
            flex: 1,
            minHeight: 36,
            background: '#160e00',
            border: '2px solid #66ff99',
            color: '#66ff99',
            fontFamily: "'Press Start 2P', monospace",
            fontSize: 8,
            cursor: 'pointer',
          }}
        >
          保存
        </button>
        <button
          onClick={onCancel}
          style={{
            minHeight: 36,
            background: '#160e00',
            border: '2px solid #ff9977',
            color: '#ff9977',
            fontFamily: "'Press Start 2P', monospace",
            fontSize: 8,
            padding: '0 8px',
            cursor: 'pointer',
          }}
        >
          ×
        </button>
      </div>
    </div>
  );
}

// ── PC Left Sidebar Nav ──
function PCSidebar({ tab, setTab, state, todayChecked, weekChecked }) {
  const currentClass = CLASSES.find((c) => c.id === state.activeClass) || CLASSES.at(-1);
  const activeTitle = TITLES_DEF.find((t) => t.id === state.activeTitle);
  const curLevelXp = levelToXp(state.level);
  const nextLevelXp = levelToXp(state.level + 1);
  const dlLen = getDailyTemplates().length;
  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <DQBox style={{ padding: '12px 14px' }}>
        <div style={{ fontSize: 14, color: '#ffe566', marginBottom: 6, letterSpacing: 2 }}>
          HERO
        </div>
        <div style={{ fontSize: 10, color: '#aaddff', marginBottom: 3 }}>
          {currentClass.icon} {currentClass.label}
        </div>
        {activeTitle && (
          <div style={{ fontSize: 9, color: '#dd99ff', marginBottom: 8 }}>
            【{activeTitle.label}】
          </div>
        )}
        <div style={{ fontSize: 10, color: '#c8a96e', marginBottom: 4 }}>
          Lv.{state.level}　{state.totalXp} XP
        </div>
        <PixelBar
          value={state.totalXp - curLevelXp}
          max={nextLevelXp - curLevelXp}
          color="#ffe566"
          height={10}
        />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6, marginTop: 10 }}>
          {[
            { label: '連続', val: `${state.streak}日`, color: '#ff9977', icon: '🔥' },
            { label: 'D完了', val: `${todayChecked.size}/${dlLen}`, color: '#66ff99', icon: '📋' },
            {
              label: 'W完了',
              val: `${weekChecked.size}/${WEEKLY_TEMPLATES.length}`,
              color: '#dd99ff',
              icon: '📅',
            },
          ].map((c) => (
            <div key={c.label} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 16, marginBottom: 2 }}>{c.icon}</div>
              <div style={{ fontSize: 11, color: c.color }}>{c.val}</div>
              <div style={{ fontSize: 8, color: '#c8a96e', marginTop: 2 }}>{c.label}</div>
            </div>
          ))}
        </div>
      </DQBox>
      <DQBox style={{ padding: '8px 0' }}>
        <div
          style={{
            fontSize: 9,
            color: '#c8a96e',
            letterSpacing: 2,
            padding: '0 14px',
            marginBottom: 6,
          }}
        >
          ▼ MENU
        </div>
        {TABS.map((t) => {
          const active = tab === t.id;
          return (
            <div
              key={t.id}
              role="button"
              tabIndex={0}
              onClick={() => setTab(t.id)}
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setTab(t.id)}
              aria-pressed={active}
              aria-label={t.label}
              className="dq-menu-item"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '10px 14px',
                minHeight: 44,
                cursor: 'pointer',
                background: active ? '#2e1e00' : 'transparent',
                borderLeft: active ? '4px solid #ffe566' : '4px solid transparent',
                outline: 'none',
              }}
            >
              <span
                style={{
                  fontSize: 10,
                  color: active ? '#ffe566' : 'transparent',
                  animation: active ? 'blink 0.8s step-end infinite' : 'none',
                  width: 10,
                  flexShrink: 0,
                }}
              >
                ▶
              </span>
              <span style={{ fontSize: 18 }}>{t.icon}</span>
              <span
                style={{ fontSize: 10, color: active ? '#ffe566' : '#e0c080', letterSpacing: 1 }}
              >
                {t.label}
              </span>
            </div>
          );
        })}
      </DQBox>
      <DQBox style={{ padding: '12px 14px' }}>
        <div style={{ fontSize: 9, color: '#c8a96e', letterSpacing: 2, marginBottom: 10 }}>
          ▼ 能力
        </div>
        {STATS_DEF.map((s) => (
          <div key={s.key} style={{ marginBottom: 9 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 10,
                marginBottom: 3,
              }}
            >
              <span style={{ color: '#e8d8b0' }}>
                {s.icon} {s.label}
              </span>
              <span style={{ color: s.color, fontWeight: 'bold' }}>{state.stats[s.key] || 0}</span>
            </div>
            <PixelBar
              value={state.stats[s.key] || 0}
              max={Math.max(...Object.values(state.stats), 10)}
              color={s.color}
              height={8}
            />
          </div>
        ))}
      </DQBox>
    </div>
  );
}

// ── Mobile Bottom Nav ──
function MobileBottomNav({ tab, setTab }) {
  return (
    <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 100 }}>
      <div style={{ maxWidth: 480, margin: '0 auto', padding: '0 10px 8px' }}>
        <div
          style={{
            background: '#0f0800',
            border: '4px solid #3a2800',
            outline: '2px solid #c8941a',
            outlineOffset: '-6px',
            boxShadow: 'inset 2px 2px 0 #fff8e022, 0 -4px 0 #00000088',
            padding: '10px 10px 8px',
          }}
        >
          <div
            style={{
              textAlign: 'center',
              fontSize: 8,
              color: '#ffe566',
              marginBottom: 8,
              letterSpacing: 2,
              animation: 'blink 1.5s step-end infinite',
            }}
          >
            ▶ {TABS.find((t) => t.id === tab)?.icon} {TABS.find((t) => t.id === tab)?.label}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {TABS.map((t) => {
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  aria-pressed={active}
                  aria-label={t.label}
                  style={{
                    minHeight: 48,
                    background: active ? '#2e1e00' : '#160e00',
                    border: `3px solid ${active ? '#ffe566' : '#7a5e30'}`,
                    padding: '10px 6px 8px',
                    cursor: 'pointer',
                    fontFamily: "'Press Start 2P', monospace",
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-start',
                    gap: 8,
                    transition: 'none',
                  }}
                >
                  <span
                    style={{
                      fontSize: 9,
                      color: active ? '#ffe566' : 'transparent',
                      flexShrink: 0,
                      width: 9,
                      animation: active ? 'blink 0.8s step-end infinite' : 'none',
                    }}
                  >
                    ▶
                  </span>
                  <span style={{ fontSize: 16, flexShrink: 0 }}>{t.icon}</span>
                  <span
                    style={{
                      fontSize: 8,
                      color: active ? '#ffe566' : '#e0c080',
                      letterSpacing: 0.5,
                      lineHeight: 1.6,
                    }}
                  >
                    {t.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════
export default function App() {
  const [state, setState] = useState(null);
  const [tab, setTab] = useState('home');
  const [floats, setFloats] = useState([]);
  const [toast, setToast] = useState(null);
  const [customText, setCustomText] = useState('');
  const [customStat, setCustomStat] = useState('intel');
  const [customXp, setCustomXp] = useState(30);
  const [loading, setLoading] = useState(true);
  const [isPC, setIsPC] = useState(window.innerWidth >= 768);
  const [editMode, setEditMode] = useState(null); // null | "daily" | "weekly"
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState('');
  const [editXp, setEditXp] = useState(30);
  const [editStat, setEditStat] = useState('intel');

  // 曜日ごとに授業クエストを動的生成（カスタムリストが保存されていればそちらを使う）
  const dailyTemplates = state?.customDailyQuests ?? getDailyTemplates();
  const weeklyTemplates = state?.customWeeklyQuests ?? WEEKLY_TEMPLATES;

  useEffect(() => {
    const onResize = () => setIsPC(window.innerWidth >= 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    loadState().then((s) => {
      setState(s);
      setLoading(false);
    });
  }, []);
  useEffect(() => {
    if (state && !loading) saveState(state);
  }, [state]);

  const showFloat = useCallback((msg, color) => {
    const id = Date.now() + Math.random();
    setFloats((p) => [...p, { id, msg, color }]);
    setTimeout(() => setFloats((p) => p.filter((f) => f.id !== id)), 1600);
  }, []);
  const showToast = useCallback((msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }, []);

  const applyXp = useCallback(
    (xp, statKey, label) => {
      setState((prev) => {
        const newStats = {
          ...prev.stats,
          [statKey]: (prev.stats[statKey] || 0) + Math.floor(xp * 0.3),
        };
        const newTotalXp = prev.totalXp + xp;
        const newLevel = xpToLevel(newTotalXp);
        const leveledUp = newLevel > prev.level;
        const mockState = {
          totalXp: newTotalXp,
          level: newLevel,
          stats: newStats,
          dailyDone: prev.dailyDone + 1,
          weeklyDone: prev.weeklyDone,
          streak: prev.streak,
        };
        const newTitles = TITLES_DEF.filter(
          (t) => !prev.unlockedTitles.includes(t.id) && t.condition(mockState),
        );
        if (leveledUp) setTimeout(() => showToast(`レベルが上がった！  Lv.${newLevel}！`), 100);
        newTitles.forEach((t) => setTimeout(() => showToast(`${t.icon} ${t.label}  解除！`), 300));
        return {
          ...prev,
          totalXp: newTotalXp,
          level: newLevel,
          stats: newStats,
          activeClass: getClass(newStats).id,
          unlockedTitles: [...prev.unlockedTitles, ...newTitles.map((t) => t.id)],
          activeTitle: prev.activeTitle || (newTitles[0]?.id ?? null),
          log: [
            {
              time: new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' }),
              text: label,
              xp,
              stat: statKey,
            },
            ...(prev.log || []).slice(0, 19),
          ],
        };
      });
      showFloat(`＋${xp}EXP`, STAT_COLOR[statKey] || '#ffdd44');
    },
    [showFloat, showToast],
  );

  const completeDaily = useCallback(
    (q) => {
      const today = todayStr();
      setState((prev) => {
        const checked = new Set(prev.dailyChecked[today] || []);
        if (checked.has(q.id)) return prev;
        checked.add(q.id);
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        const yStr = yesterday.toISOString().slice(0, 10);
        const streak =
          prev.lastDate === yStr ? prev.streak + 1 : prev.lastDate === today ? prev.streak : 1;
        return {
          ...prev,
          dailyChecked: { ...prev.dailyChecked, [today]: checked },
          dailyDone: prev.dailyDone + 1,
          lastDate: today,
          streak,
        };
      });
      applyXp(q.xp, q.stat, `[デイリー] ${q.text}`);
    },
    [applyXp],
  );

  const completeWeekly = useCallback(
    (q) => {
      const wk = weekKey();
      setState((prev) => {
        const checked = new Set(prev.weeklyChecked[wk] || []);
        if (checked.has(q.id)) return prev;
        checked.add(q.id);
        return {
          ...prev,
          weeklyChecked: { ...prev.weeklyChecked, [wk]: checked },
          weeklyDone: prev.weeklyDone + 1,
        };
      });
      applyXp(q.xp, q.stat, `[ウィークリー] ${q.text}`);
    },
    [applyXp],
  );

  const addCustom = useCallback(() => {
    if (!customText.trim()) return;
    setState((prev) => ({
      ...prev,
      customQuests: [
        ...prev.customQuests,
        {
          id: `c${Date.now()}`,
          text: customText.trim(),
          xp: Number(customXp),
          stat: customStat,
          icon: '⚡',
        },
      ],
    }));
    setCustomText('');
  }, [customText, customXp, customStat]);

  // ── クエスト編集ヘルパー ──
  const startEditMode = useCallback((type, templates) => {
    setEditMode(type);
    setEditingId(null);
  }, []);

  const saveEditedQuest = useCallback((type, updated) => {
    setState((prev) => {
      const base =
        type === 'daily'
          ? (prev.customDailyQuests ?? getDailyTemplates())
          : (prev.customWeeklyQuests ?? WEEKLY_TEMPLATES);
      const list = base.map((q) => (q.id === updated.id ? updated : q));
      return type === 'daily'
        ? { ...prev, customDailyQuests: list }
        : { ...prev, customWeeklyQuests: list };
    });
  }, []);

  const deleteQuest = useCallback((type, id) => {
    setState((prev) => {
      const base =
        type === 'daily'
          ? (prev.customDailyQuests ?? getDailyTemplates())
          : (prev.customWeeklyQuests ?? WEEKLY_TEMPLATES);
      const updated = base.filter((q) => q.id !== id);
      return type === 'daily'
        ? { ...prev, customDailyQuests: updated }
        : { ...prev, customWeeklyQuests: updated };
    });
  }, []);

  const addNewQuest = useCallback((type) => {
    const newQ = {
      id: `custom_${Date.now()}`,
      text: '新しいクエスト',
      xp: 30,
      stat: 'intel',
      icon: '⚡',
    };
    setState((prev) => {
      const base =
        type === 'daily'
          ? (prev.customDailyQuests ?? getDailyTemplates())
          : (prev.customWeeklyQuests ?? WEEKLY_TEMPLATES);
      const updated = [...base, newQ];
      return type === 'daily'
        ? { ...prev, customDailyQuests: updated }
        : { ...prev, customWeeklyQuests: updated };
    });
    setEditingId(newQ.id);
    setEditText('新しいクエスト');
    setEditXp(30);
    setEditStat('intel');
  }, []);

  const resetToDefault = useCallback((type) => {
    setState((prev) =>
      type === 'daily'
        ? { ...prev, customDailyQuests: null }
        : { ...prev, customWeeklyQuests: null },
    );
  }, []);

  const completeCustom = useCallback(
    (q) => {
      setState((prev) => ({
        ...prev,
        customQuests: prev.customQuests.filter((x) => x.id !== q.id),
      }));
      applyXp(q.xp, q.stat, `[カスタム] ${q.text}`);
    },
    [applyXp],
  );

  if (loading || !state) {
    return (
      <div
        style={{
          minHeight: '100vh',
          background: '#0a0600',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 16,
        }}
      >
        <div
          style={{
            fontFamily: "'Press Start 2P', monospace",
            fontSize: 10,
            color: '#f8f0d0',
            animation: 'blink 1s step-end infinite',
          }}
        >
          NOW LOADING...
        </div>
        <style>{`@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap'); @keyframes blink{0%,100%{opacity:1}50%{opacity:0}}`}</style>
      </div>
    );
  }

  const today = todayStr();
  const wk = weekKey();
  const todayChecked =
    state.dailyChecked[today] instanceof Set
      ? state.dailyChecked[today]
      : new Set(state.dailyChecked[today] || []);
  const weekChecked =
    state.weeklyChecked[wk] instanceof Set
      ? state.weeklyChecked[wk]
      : new Set(state.weeklyChecked[wk] || []);
  const currentClass = CLASSES.find((c) => c.id === state.activeClass) || CLASSES.at(-1);
  const curLevelXp = levelToXp(state.level);
  const nextLevelXp = levelToXp(state.level + 1);
  const activeTitle = TITLES_DEF.find((t) => t.id === state.activeTitle);
  const maxStat = Math.max(...Object.values(state.stats), 1);

  const HeroSprite = () => (
    <div style={{ width: 32, height: 40, imageRendering: 'pixelated', flexShrink: 0 }}>
      <svg viewBox="0 0 8 10" width="32" height="40" style={{ imageRendering: 'pixelated' }}>
        <rect x="2" y="0" width="4" height="4" fill="#f5c27a" />
        <rect x="2" y="0" width="4" height="1" fill="#3a2000" />
        <rect x="1" y="1" width="1" height="2" fill="#3a2000" />
        <rect x="3" y="2" width="1" height="1" fill="#1a0a00" />
        <rect x="5" y="2" width="1" height="1" fill="#1a0a00" />
        <rect x="2" y="4" width="4" height="3" fill="#3366cc" />
        <rect x="1" y="4" width="1" height="3" fill="#3366cc" />
        <rect x="6" y="4" width="1" height="3" fill="#3366cc" />
        <rect x="2" y="7" width="2" height="3" fill="#222288" />
        <rect x="4" y="7" width="2" height="3" fill="#222288" />
        <rect x="7" y="3" width="1" height="4" fill="#aaaaaa" />
        <rect x="6" y="4" width="2" height="1" fill="#885500" />
      </svg>
    </div>
  );

  // ── Main content (shared between PC and mobile) ──
  const MainContent = () => {
    const fs = isPC
      ? { title: 12, body: 11, sub: 10, tiny: 9, label: 9 }
      : { title: 9, body: 8, sub: 7, tiny: 6, label: 7 };
    const iconSize = isPC ? 20 : 14;
    const rowPad = isPC ? '14px 16px' : '12px 12px';
    const C = {
      heading: '#ffe566',
      text: '#fff8e0',
      sub: '#e0c080',
      muted: '#b09060',
      done: '#6a5030',
    };
    return (
      <>
        {tab === 'home' && (
          <>
            <DQBox style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <div style={{ animation: 'walk 1s step-end infinite' }}>
                  <HeroSprite />
                </div>
                <div style={{ flex: 1 }}>
                  <div
                    style={{ fontSize: 11, color: '#ffdd44', marginBottom: 6, letterSpacing: 1 }}
                  >
                    HERO
                  </div>
                  <div style={{ fontSize: 8, color: '#aaccff', marginBottom: 2 }}>
                    {currentClass.icon} {currentClass.label}
                  </div>
                  {activeTitle && (
                    <div style={{ fontSize: 7, color: '#cc88ff', marginBottom: 6 }}>
                      【{activeTitle.label}】
                    </div>
                  )}
                  <div style={{ fontSize: 7, color: '#887755', marginBottom: 2 }}>
                    レベル　{state.level}
                  </div>
                  <div style={{ fontSize: 7, color: '#887755', marginBottom: 4 }}>
                    経験値 {state.totalXp} / {levelToXp(state.level + 1)}
                  </div>
                  <PixelBar
                    value={state.totalXp - curLevelXp}
                    max={nextLevelXp - curLevelXp}
                    color="#ffdd44"
                    height={10}
                  />
                </div>
              </div>
            </DQBox>
            {!isPC && (
              <DQBox style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 7, color: '#887755', marginBottom: 8, letterSpacing: 2 }}>
                  ▼ 能力参照
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px' }}>
                  {STATS_DEF.map((s) => (
                    <div key={s.key}>
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          fontSize: 7,
                          marginBottom: 2,
                        }}
                      >
                        <span style={{ color: '#f8f0d0' }}>{s.label}</span>
                        <span style={{ color: s.color }}>{state.stats[s.key] || 0}</span>
                      </div>
                      <PixelBar
                        value={state.stats[s.key] || 0}
                        max={Math.max(maxStat, 10)}
                        color={s.color}
                        height={7}
                      />
                    </div>
                  ))}
                </div>
              </DQBox>
            )}
            {!isPC && (
              <DQBox style={{ marginBottom: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                  {[
                    { label: '連続', val: `${state.streak}日`, color: '#ff8866', icon: '🔥' },
                    {
                      label: 'デイリー',
                      val: `${todayChecked.size}/${dailyTemplates.length}`,
                      color: '#88ff88',
                      icon: '📋',
                    },
                    {
                      label: '週間',
                      val: `${weekChecked.size}/${WEEKLY_TEMPLATES.length}`,
                      color: '#cc88ff',
                      icon: '📅',
                    },
                  ].map((c) => (
                    <div key={c.label} style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 14, marginBottom: 4 }}>{c.icon}</div>
                      <div style={{ fontSize: 9, color: c.color, letterSpacing: 1 }}>{c.val}</div>
                      <div style={{ fontSize: 6, color: '#665500', marginTop: 2 }}>{c.label}</div>
                    </div>
                  ))}
                </div>
              </DQBox>
            )}
            <DQBox>
              <div style={{ fontSize: 7, color: '#887755', marginBottom: 8, letterSpacing: 2 }}>
                ▼ 最近の記録
              </div>
              {(state.log || []).length === 0 ? (
                <div
                  style={{ fontSize: 8, color: '#554433', textAlign: 'center', padding: '8px 0' }}
                >
                  記録がありません
                </div>
              ) : (
                state.log.slice(0, isPC ? 8 : 4).map((l, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: 7,
                      color: '#887755',
                      padding: '3px 0',
                      borderBottom: '1px solid #2a1a00',
                    }}
                  >
                    <span
                      style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        flex: 1,
                        marginRight: 8,
                      }}
                    >
                      <span style={{ color: STAT_COLOR[l.stat] }}>■</span>{' '}
                      {l.text.slice(0, isPC ? 30 : 18)}
                    </span>
                    <span style={{ color: '#ffdd44', flexShrink: 0 }}>+{l.xp}</span>
                  </div>
                ))
              )}
            </DQBox>
          </>
        )}

        {tab === 'daily' && (
          <>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <MsgWindow lines={[`今日 ${todayChecked.size}/${dailyTemplates.length} 完了`]} />
              <DQButton
                onClick={() => setEditMode(editMode === 'daily' ? null : 'daily')}
                color={editMode === 'daily' ? '#ff9977' : '#ffe566'}
                style={{
                  fontSize: 8,
                  padding: '6px 10px',
                  minHeight: 36,
                  marginLeft: 8,
                  flexShrink: 0,
                }}
              >
                {editMode === 'daily' ? '完了' : '✏️ 編集'}
              </DQButton>
            </div>

            {/* 編集モード */}
            {editMode === 'daily' && (
              <DQBox style={{ marginBottom: 10 }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 10,
                  }}
                >
                  <div style={{ fontSize: fs.sub, color: '#ffe566' }}>▼ クエスト編集</div>
                  <button
                    onClick={() => resetToDefault('daily')}
                    style={{
                      background: 'none',
                      border: '1px solid #554433',
                      color: '#887755',
                      fontSize: 7,
                      fontFamily: "'Press Start 2P', monospace",
                      padding: '3px 6px',
                      cursor: 'pointer',
                    }}
                  >
                    リセット
                  </button>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {dailyTemplates.map((q) => (
                    <div key={q.id}>
                      {editingId === q.id ? (
                        <QuestEditForm
                          quest={q}
                          onSave={(updated) => {
                            saveEditedQuest('daily', updated);
                            setEditingId(null);
                          }}
                          onCancel={() => setEditingId(null)}
                        />
                      ) : (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            background: '#160e00',
                            border: '2px solid #3a2800',
                            padding: '8px 10px',
                          }}
                        >
                          <span style={{ fontSize: 14, flexShrink: 0 }}>{q.icon}</span>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: fs.tiny, color: '#e0c080' }}>{q.text}</div>
                            <div style={{ fontSize: 7, color: STAT_COLOR[q.stat], marginTop: 2 }}>
                              {STATS_DEF.find((s) => s.key === q.stat)?.label} +{q.xp}XP
                            </div>
                          </div>
                          <button
                            onClick={() => setEditingId(q.id)}
                            style={{
                              background: 'none',
                              border: '1px solid #5a3e10',
                              color: '#ffe566',
                              fontSize: 9,
                              fontFamily: "'Press Start 2P', monospace",
                              padding: '4px 7px',
                              cursor: 'pointer',
                              minHeight: 32,
                            }}
                          >
                            ✏️
                          </button>
                          <button
                            onClick={() => deleteQuest('daily', q.id)}
                            style={{
                              background: 'none',
                              border: '1px solid #5a3e10',
                              color: '#ff9977',
                              fontSize: 9,
                              fontFamily: "'Press Start 2P', monospace",
                              padding: '4px 7px',
                              cursor: 'pointer',
                              minHeight: 32,
                            }}
                          >
                            🗑
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 10 }}>
                  <DQButton
                    onClick={() => addNewQuest('daily')}
                    color="#66ff99"
                    style={{ width: '100%', fontSize: 8, minHeight: 40 }}
                  >
                    ＋ クエスト追加
                  </DQButton>
                </div>
              </DQBox>
            )}

            {/* 通常表示 */}
            {editMode !== 'daily' && (
              <>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
                  {dailyTemplates.map((q) => {
                    const done = todayChecked.has(q.id);
                    return (
                      <div
                        key={q.id}
                        role="button"
                        tabIndex={done ? -1 : 0}
                        aria-label={`${q.text}（${done ? '完了' : '未完了'}）`}
                        className="dq-menu-item"
                        onClick={() => !done && completeDaily(q)}
                        onKeyDown={(e) =>
                          !done && (e.key === 'Enter' || e.key === ' ') && completeDaily(q)
                        }
                        style={{
                          background: done ? '#160e00' : '#221400',
                          border: `3px solid ${done ? '#3a2800' : '#6a4e20'}`,
                          padding: rowPad,
                          minHeight: 48,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 10,
                          opacity: done ? 0.55 : 1,
                          cursor: done ? 'default' : 'pointer',
                          boxShadow: done ? 'none' : '2px 2px 0 #00000099',
                        }}
                      >
                        <div
                          style={{
                            fontSize: fs.sub,
                            color: done ? C.done : C.heading,
                            width: 12,
                            flexShrink: 0,
                          }}
                        >
                          {done ? '✓' : '▶'}
                        </div>
                        <div style={{ fontSize: iconSize, flexShrink: 0 }}>
                          {done ? '✅' : q.icon}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div
                            style={{
                              fontSize: fs.body,
                              color: done ? C.done : C.text,
                              textDecoration: done ? 'line-through' : 'none',
                              lineHeight: 1.8,
                            }}
                          >
                            {q.text}
                          </div>
                          <div
                            style={{
                              fontSize: fs.sub,
                              color: done ? C.done : STAT_COLOR[q.stat],
                              marginTop: 3,
                            }}
                          >
                            {STATS_DEF.find((s) => s.key === q.stat)?.label}　＋{q.xp}EXP
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <DQBox style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: fs.sub, color: C.muted, marginBottom: 8 }}>
                    ▼ 今日だけのクエスト追加
                  </div>
                  <input
                    value={customText}
                    onChange={(e) => setCustomText(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && addCustom()}
                    placeholder="クエスト名..."
                    style={{
                      width: '100%',
                      background: '#160e00',
                      border: '3px solid #5a3e10',
                      padding: '8px 10px',
                      color: '#fff8e0',
                      fontSize: fs.body,
                      fontFamily: "'Press Start 2P', monospace",
                      marginBottom: 8,
                      outline: 'none',
                      minHeight: 44,
                    }}
                  />
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
                    {STATS_DEF.map((s) => (
                      <button
                        key={s.key}
                        onClick={() => setCustomStat(s.key)}
                        style={{
                          background: customStat === s.key ? '#2e1e00' : '#160e00',
                          border: `2px solid ${customStat === s.key ? s.color : '#5a3e10'}`,
                          color: customStat === s.key ? s.color : '#b09060',
                          fontSize: fs.tiny,
                          fontFamily: "'Press Start 2P', monospace",
                          padding: '4px 6px',
                          cursor: 'pointer',
                        }}
                      >
                        {s.icon}
                        {s.label}
                      </button>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      type="number"
                      value={customXp}
                      onChange={(e) => setCustomXp(e.target.value)}
                      style={{
                        width: 60,
                        background: '#160e00',
                        border: '3px solid #5a3e10',
                        padding: '6px',
                        color: '#ffe566',
                        fontSize: fs.body,
                        fontFamily: "'Press Start 2P', monospace",
                        outline: 'none',
                        minHeight: 44,
                      }}
                    />
                    <DQButton onClick={addCustom} color="#66ff99" style={{ flex: 1, fontSize: 8 }}>
                      追加
                    </DQButton>
                  </div>
                </DQBox>
                {state.customQuests.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {state.customQuests.map((q) => (
                      <div
                        key={q.id}
                        role="button"
                        tabIndex={0}
                        className="dq-menu-item"
                        onClick={() => completeCustom(q)}
                        style={{
                          background: '#221400',
                          border: '3px solid #7a5e20',
                          padding: rowPad,
                          minHeight: 48,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 10,
                          cursor: 'pointer',
                          boxShadow: '2px 2px 0 #00000099',
                        }}
                      >
                        <div style={{ fontSize: fs.sub, color: C.heading }}>▶</div>
                        <div style={{ fontSize: iconSize }}>⚡</div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: fs.body, color: C.text, lineHeight: 1.8 }}>
                            {q.text}
                          </div>
                          <div
                            style={{ fontSize: fs.sub, color: STAT_COLOR[q.stat], marginTop: 2 }}
                          >
                            ＋{q.xp}EXP
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        )}

        {tab === 'weekly' && (
          <>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <MsgWindow lines={[`今週 ${weekChecked.size}/${weeklyTemplates.length} 完了`]} />
              <DQButton
                onClick={() => setEditMode(editMode === 'weekly' ? null : 'weekly')}
                color={editMode === 'weekly' ? '#ff9977' : '#ffe566'}
                style={{
                  fontSize: 8,
                  padding: '6px 10px',
                  minHeight: 36,
                  marginLeft: 8,
                  flexShrink: 0,
                }}
              >
                {editMode === 'weekly' ? '完了' : '✏️ 編集'}
              </DQButton>
            </div>

            {editMode === 'weekly' && (
              <DQBox style={{ marginBottom: 10 }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 10,
                  }}
                >
                  <div style={{ fontSize: fs.sub, color: '#ffe566' }}>▼ クエスト編集</div>
                  <button
                    onClick={() => resetToDefault('weekly')}
                    style={{
                      background: 'none',
                      border: '1px solid #554433',
                      color: '#887755',
                      fontSize: 7,
                      fontFamily: "'Press Start 2P', monospace",
                      padding: '3px 6px',
                      cursor: 'pointer',
                    }}
                  >
                    リセット
                  </button>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {weeklyTemplates.map((q) => (
                    <div key={q.id}>
                      {editingId === q.id ? (
                        <QuestEditForm
                          quest={q}
                          onSave={(updated) => {
                            saveEditedQuest('weekly', updated);
                            setEditingId(null);
                          }}
                          onCancel={() => setEditingId(null)}
                        />
                      ) : (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            background: '#160e00',
                            border: '2px solid #3a2800',
                            padding: '8px 10px',
                          }}
                        >
                          <span style={{ fontSize: 14, flexShrink: 0 }}>{q.icon}</span>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: fs.tiny, color: '#e0c080' }}>{q.text}</div>
                            <div style={{ fontSize: 7, color: STAT_COLOR[q.stat], marginTop: 2 }}>
                              {STATS_DEF.find((s) => s.key === q.stat)?.label} +{q.xp}XP
                            </div>
                          </div>
                          <button
                            onClick={() => setEditingId(q.id)}
                            style={{
                              background: 'none',
                              border: '1px solid #5a3e10',
                              color: '#ffe566',
                              fontSize: 9,
                              fontFamily: "'Press Start 2P', monospace",
                              padding: '4px 7px',
                              cursor: 'pointer',
                              minHeight: 32,
                            }}
                          >
                            ✏️
                          </button>
                          <button
                            onClick={() => deleteQuest('weekly', q.id)}
                            style={{
                              background: 'none',
                              border: '1px solid #5a3e10',
                              color: '#ff9977',
                              fontSize: 9,
                              fontFamily: "'Press Start 2P', monospace",
                              padding: '4px 7px',
                              cursor: 'pointer',
                              minHeight: 32,
                            }}
                          >
                            🗑
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 10 }}>
                  <DQButton
                    onClick={() => addNewQuest('weekly')}
                    color="#66ff99"
                    style={{ width: '100%', fontSize: 8, minHeight: 40 }}
                  >
                    ＋ クエスト追加
                  </DQButton>
                </div>
              </DQBox>
            )}

            {editMode !== 'weekly' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {weeklyTemplates.map((q) => {
                  const done = weekChecked.has(q.id);
                  return (
                    <div
                      key={q.id}
                      role="button"
                      tabIndex={done ? -1 : 0}
                      className="dq-menu-item"
                      onClick={() => !done && completeWeekly(q)}
                      onKeyDown={(e) =>
                        !done && (e.key === 'Enter' || e.key === ' ') && completeWeekly(q)
                      }
                      style={{
                        background: done ? '#160e00' : '#221400',
                        border: `3px solid ${done ? '#3a2800' : '#6a4e20'}`,
                        padding: rowPad,
                        minHeight: 48,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        opacity: done ? 0.55 : 1,
                        cursor: done ? 'default' : 'pointer',
                        boxShadow: done ? 'none' : '2px 2px 0 #00000099',
                      }}
                    >
                      <div
                        style={{ fontSize: fs.sub, color: done ? C.done : C.heading, width: 12 }}
                      >
                        {done ? '✓' : '▶'}
                      </div>
                      <div style={{ fontSize: iconSize + 2, flexShrink: 0 }}>
                        {done ? '✅' : q.icon}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div
                          style={{
                            fontSize: fs.body,
                            color: done ? C.done : C.text,
                            textDecoration: done ? 'line-through' : 'none',
                            lineHeight: 1.8,
                          }}
                        >
                          {q.text}
                        </div>
                        <div
                          style={{
                            fontSize: fs.sub,
                            color: done ? C.done : STAT_COLOR[q.stat],
                            marginTop: 3,
                          }}
                        >
                          {STATS_DEF.find((s) => s.key === q.stat)?.label}　＋{q.xp}EXP
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {tab === 'status' && (
          <>
            <MsgWindow lines={['能力表', `総経験値 ${state.totalXp}`]} />
            <DQBox style={{ marginBottom: 10 }}>
              {STATS_DEF.map((s) => (
                <div key={s.key} style={{ marginBottom: 10 }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: 8,
                      marginBottom: 4,
                    }}
                  >
                    <span style={{ color: '#f8f0d0' }}>
                      {s.icon} {s.label}
                    </span>
                    <span style={{ color: s.color }}>{state.stats[s.key] || 0}</span>
                  </div>
                  <PixelBar
                    value={state.stats[s.key] || 0}
                    max={Math.max(maxStat, 10)}
                    color={s.color}
                    height={10}
                  />
                </div>
              ))}
            </DQBox>
            <DQBox>
              <div style={{ fontSize: 7, color: '#887755', marginBottom: 8, letterSpacing: 2 }}>
                ▼ クラス解放状況
              </div>
              {CLASSES.map((c) => {
                const unlocked = Object.entries(c.req).every(
                  ([k, v]) => (state.stats[k] || 0) >= v,
                );
                const isActive = state.activeClass === c.id;
                return (
                  <div
                    key={c.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '5px 0',
                      borderBottom: '1px solid #2a1a00',
                      opacity: unlocked ? 1 : 0.35,
                    }}
                  >
                    <span style={{ fontSize: 14 }}>{c.icon}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 7, color: isActive ? '#ffdd44' : '#887755' }}>
                        {c.label}
                        {isActive ? '　←現在のクラス' : ''}
                      </div>
                      <div style={{ fontSize: 6, color: '#554433', marginTop: 1 }}>
                        {Object.entries(c.req)
                          .map(([k, v]) => `${STATS_DEF.find((s) => s.key === k)?.label}${v}`)
                          .join(' / ') || '初期クラス'}
                      </div>
                    </div>
                    <div style={{ fontSize: 6, color: unlocked ? '#88ff88' : '#554433' }}>
                      {unlocked ? '解放済' : '未解放'}
                    </div>
                  </div>
                );
              })}
            </DQBox>
          </>
        )}

        {tab === 'achieve' && (
          <>
            <MsgWindow
              lines={['実績・称号', `${state.unlockedTitles.length} / ${TITLES_DEF.length} 解除`]}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {TITLES_DEF.map((t) => {
                const unlocked = state.unlockedTitles.includes(t.id);
                const isActive = state.activeTitle === t.id;
                return (
                  <div
                    key={t.id}
                    className="dq-menu-item"
                    onClick={() =>
                      unlocked && setState((p) => ({ ...p, activeTitle: isActive ? null : t.id }))
                    }
                    style={{
                      background: unlocked ? '#1a0e00' : '#0a0600',
                      border: `3px solid ${unlocked ? (isActive ? '#ffdd44' : '#4a3000') : '#1a1000'}`,
                      outline: isActive ? '1px solid #ffdd4488' : 'none',
                      outlineOffset: '-4px',
                      padding: '10px 12px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      opacity: unlocked ? 1 : 0.3,
                      cursor: unlocked ? 'pointer' : 'default',
                      boxShadow: unlocked ? '2px 2px 0 #00000099' : 'none',
                    }}
                  >
                    <div style={{ fontSize: 7, color: '#ffdd44', width: 10 }}>
                      {isActive ? '▶' : '　'}
                    </div>
                    <div style={{ fontSize: 20 }}>{unlocked ? t.icon : '🔒'}</div>
                    <div style={{ flex: 1 }}>
                      <div
                        style={{
                          fontSize: 8,
                          color: unlocked ? (isActive ? '#ffdd44' : '#f8f0d0') : '#554433',
                        }}
                      >
                        【{t.label}】
                      </div>
                      {isActive && (
                        <div style={{ fontSize: 6, color: '#cc88ff', marginTop: 2 }}>装備中</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </>
    );
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#0a0600',
        fontFamily: "'Press Start 2P', monospace",
        color: '#f8f0d0',
        paddingBottom: isPC ? 20 : 150,
        position: 'relative',
        imageRendering: 'pixelated',
      }}
    >
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
        * { box-sizing: border-box; }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes floatUp { 0%{opacity:1;transform:translateX(-50%) translateY(0)} 100%{opacity:0;transform:translateX(-50%) translateY(-60px)} }
        @keyframes toastSlide { 0%{opacity:0;transform:translateX(-50%) translateY(10px)} 15%{opacity:1;transform:translateX(-50%) translateY(0)} 80%{opacity:1} 100%{opacity:0} }
        @keyframes starPulse { 0%,100%{opacity:.6} 50%{opacity:1} }
        @keyframes walk { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-2px)} }
        .dq-menu-item:hover { background: #2a1a00 !important; }
        .dq-menu-item { transition: background .05s; }
        input { caret-color: #f8f0d0; }
        input:focus { outline: 2px solid #4488ff88 !important; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #1a0e00; }
        ::-webkit-scrollbar-thumb { background: #4a3000; border: 1px solid #2a1a00; }
      `}</style>

      {/* Stars */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 0,
          overflow: 'hidden',
          pointerEvents: 'none',
        }}
      >
        {Array.from({ length: 30 }).map((_, i) => (
          <div
            key={i}
            style={{
              position: 'absolute',
              width: 2,
              height: 2,
              background: '#fff8e0',
              left: `${(i * 37 + 11) % 100}%`,
              top: `${(i * 53 + 7) % 60}%`,
              opacity: 0.3 + (i % 5) * 0.1,
              animation: `starPulse ${2 + (i % 4)}s ease-in-out infinite`,
              animationDelay: `${i * 0.2}s`,
            }}
          />
        ))}
      </div>

      {/* Floats */}
      {floats.map((f) => (
        <div
          key={f.id}
          style={{
            position: 'fixed',
            top: '22%',
            left: '50%',
            zIndex: 9999,
            pointerEvents: 'none',
            animation: 'floatUp 1.6s ease-out forwards',
            fontSize: 11,
            color: f.color,
            textShadow: `0 0 8px ${f.color}, 2px 2px 0 #000`,
            letterSpacing: 1,
          }}
        >
          {f.msg}
        </div>
      ))}

      {/* Toast */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            bottom: isPC ? 20 : 160,
            left: '50%',
            zIndex: 9998,
            animation: 'toastSlide 3.5s ease forwards',
            width: '90%',
            maxWidth: 380,
          }}
        >
          <DQBox style={{ padding: '10px 14px' }}>
            <div style={{ fontSize: 8, color: '#ffdd44', lineHeight: 2, letterSpacing: 1 }}>
              ▶ {toast}
            </div>
          </DQBox>
        </div>
      )}

      {/* ── PC layout: side-by-side ── */}
      {isPC ? (
        <div
          style={{
            display: 'flex',
            gap: 16,
            maxWidth: 1100,
            margin: '0 auto',
            padding: '16px 16px',
          }}
        >
          <div style={{ width: 260, flexShrink: 0 }}>
            <PCSidebar
              tab={tab}
              setTab={setTab}
              state={state}
              todayChecked={todayChecked}
              weekChecked={weekChecked}
            />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={{ fontSize: 9, color: '#885500', letterSpacing: 2 }}>LIFE RPG v1.0</div>
              <div style={{ fontSize: 9, color: '#665500' }}>{todayStr()}</div>
            </div>
            <MainContent />
          </div>
        </div>
      ) : (
        /* ── Mobile layout: single column + bottom nav ── */
        <div
          style={{
            position: 'relative',
            zIndex: 1,
            maxWidth: 480,
            margin: '0 auto',
            padding: '0 10px',
          }}
        >
          <div
            style={{
              paddingTop: 12,
              marginBottom: 10,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <div style={{ fontSize: 7, color: '#885500', letterSpacing: 2 }}>LIFE RPG v1.0</div>
            <div style={{ fontSize: 7, color: '#665500' }}>{todayStr()}</div>
          </div>
          <MainContent />
          <MobileBottomNav tab={tab} setTab={setTab} />
        </div>
      )}
    </div>
  );
}
