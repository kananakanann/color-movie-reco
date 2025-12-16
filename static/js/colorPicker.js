// static/js/colorPicker.js
// - color_top2.json を読み込んで色→感情マッピング
// - ピンク系は love にバイアス
// - 複数色から感情スコアを集計して、上位2つまで推定
// - 推定された各感情ごとに映画リストを表示（love 用リスト・joy 用リストなど）
// - 推定後にログAPI(/api/log_color_experiment)へ1回だけ送信

const colorInput = document.getElementById("color-input");
const addBtn = document.getElementById("add-color-btn");
const clearBtn = document.getElementById("clear-btn");
const recBtn = document.getElementById("recommend-btn");
const showEmoBtn  = document.getElementById("show-emotion-btn");
const chips = document.getElementById("chips");
//const preview = document.getElementById("preview");
const results = document.getElementById("results");
const errorBox = document.getElementById("error");
const count = document.getElementById("count");
const inferredEl = document.getElementById("inferred-emotion");
const inferredRow = document.getElementById("inferred-row");

const GENRE_MAP = {
    28: "アクション",
    12: "アドベンチャー",
    16: "アニメーション",
    35: "コメディ",
    80: "犯罪",
    99: "ドキュメンタリー",
    18: "ドラマ",
    10751: "ファミリー",
    14: "ファンタジー",
    36: "歴史",
    27: "ホラー",
    10402: "音楽",
    9648: "ミステリー",
    10749: "ロマンス",
    878: "SF",
    10770: "TV映画",
    53: "スリラー",
    10752: "戦争",
    37: "西部劇"
};

let selected = []; // [{hex, rgb, top1:{label,pct}, top2:{label,pct}}]
let palette = [];

const COLOR_MAP_URL = "/static/data/color_top2.json";

// サーバ側の ALLOWED_EMOTIONS に対応させる
const EMO_MAP = { "リラックス": "joy" };
const ALLOWED = new Set(["joy", "sadness", "anger", "fear", "love", "surprise"]);

// ---------- Utils ----------
function normalizeHex(h) {
  if (!h) return null;
  let s = String(h).trim();
  if (s[0] !== "#") s = "#" + s;
  return s.toLowerCase();
}

function hexToRgbArray(hex) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!m) return [0, 0, 0];
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
}

function rgbDist(a, b) {
  return Math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2);
}

// RGB -> HSL（ピンク判定用）
function rgbToHsl([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h, s, l = (max + min) / 2;
  if (max === min) { h = s = 0; }
  else {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
    }
    h *= 60;
  }
  return [h, s, l];
}

// ピンク寄り判定
function isPinkish(rgb) {
  const [h, s, l] = rgbToHsl(rgb); 
  const isRed = (h >= 340 || h <= 20); 
  const isMagenta = (h >= 300 && h < 340); 
  const bright = l >= 0.65; const vivid = s >= 0.20; 
  return (isRed || isMagenta) && bright && vivid; 
}

//黄色バイアス
function isYellowish(rgb) {
  const [h, s, l] = rgbToHsl(rgb);
  return h >= 40 && h <= 70;
}


//ジャンル
function genreIdsToNames(ids) {
  if (!Array.isArray(ids)) return [];
  return ids.map(id => GENRE_MAP[id] || "Unknown");
}

// ---------- 年齢制限（日本基準） ----------
function formatJpRating(m) {
  // JPだけを見る
  const jp = (m.jp_certification || "").trim();

  // nullの場合
  if (!jp) return "年齢制限：なし";

  // 日本の想定ラベル：G / PG12 / R15+ / R18+
  if (jp === "G") return "年齢制限：なし（G）";
  if (jp === "PG12") return "年齢制限：PG12";
  if (jp === "R15+") return "年齢制限：R15+";
  if (jp === "R18+") return "年齢制限：R18+";

  // 想定外の表記が来たときも、そのまま表示しておく（安全）
  return `年齢制限： ${jp}`;
}



// ---------- color_top2.json -> palette ----------
function normalizeColorMapFromArray(arr) {
  const byHex = new Map();
  for (const item of arr) {
    if (!item) continue;
    const hex = normalizeHex(item.color_code);
    if (!hex) continue;
    const emos = Array.isArray(item.top_emotions) ? item.top_emotions : [];
    const probs = Array.isArray(item.probs) ? item.probs : [];
    const top = emos.slice(0, 2).map((lab, idx) => ({
      label: String(lab),
      pct: (typeof probs[idx] === "number")
        ? Math.round(probs[idx] * 1000) / 10
        : null
    }));
    const entry = {
      hex,
      rgb: hexToRgbArray(hex),
      name: item.color_name || undefined,
      top: top.length ? top : [{ label: "unknown", pct: null }]
    };
    const prev = byHex.get(hex);
    const prevScore = prev?.top?.[0]?.pct ?? -1;
    const currScore = entry.top?.[0]?.pct ?? -1;
    if (!prev || currScore > prevScore) byHex.set(hex, entry);
  }
  return [...byHex.values()];
}

async function loadColorMap() {
  addBtn.disabled = true;
  try {
    const res = await fetch(COLOR_MAP_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await res.json();
    if (!Array.isArray(raw)) throw new Error("JSON root is not an array");
    palette = normalizeColorMapFromArray(raw);
    errorBox.textContent = "";
  } catch (err) {
    console.warn("[colorPicker] mapping load failed:", err);
    errorBox.textContent = "色→感情マッピングの読み込みに失敗しました（color_top2.json）。";
    palette = [];
  } finally {
    addBtn.disabled = false;
  }
}

function nearestEntryByRgb(hex) {
  if (!palette || palette.length === 0) return null;
  const rgb = hexToRgbArray(hex);
  let best = null, minD = Infinity;
  for (const entry of palette) {
    const d = rgbDist(rgb, entry.rgb);
    if (d < minD) { minD = d; best = entry; }
  }
  return best;
}

// ---------- 推定感情（上位2つまで返す） ----------
function calcDominantEmotions(colors, k = 2) {
  if (!colors || colors.length === 0) return [];
  const score = new Map();
  for (const c of colors) {
    if (c.top1 && c.top1.label) {
      const label1 = (EMO_MAP[c.top1.label] || c.top1.label).toLowerCase();
      if (ALLOWED.has(label1)) {
        const w1 = (typeof c.top1.pct === "number" ? c.top1.pct : 60);
        score.set(label1, (score.get(label1) || 0) + w1);
      }
    }
    if (c.top2 && c.top2.label) {
      const label2 = (EMO_MAP[c.top2.label] || c.top2.label).toLowerCase();
      if (ALLOWED.has(label2)) {
        const w2 = (typeof c.top2.pct === "number" ? c.top2.pct : 40) * 0.5;
        score.set(label2, (score.get(label2) || 0) + w2);
      }
    }
  }
  if (score.size === 0) return [];
  const sorted = [...score.entries()].sort((a, b) => b[1] - a[1]);
  return sorted.slice(0, k).map(([label]) => label);
}

// ---------- UI描画 ----------
function render() {
  chips.innerHTML = "";
  selected.forEach((c, i) => {
    const el = document.createElement("div");
    el.className = "chip";
    const top1 = c.top1 ? `${c.top1.label}${c.top1.pct != null ? ` (${c.top1.pct}%)` : ""}` : "unknown";
    const top2 = c.top2 ? `${c.top2.label}${c.top2.pct != null ? ` (${c.top2.pct}%)` : ""}` : null;

    el.innerHTML = `
      <span class="swatch" style="background:${c.hex}"></span>
      <div class="chip-text">
        <div>${c.hex.toUpperCase()} ( ${c.rgb.join(",")} )</div>
        <!--<div class="emotion-label">→ ${top1}${top2 ? `, ${top2}` : ""}</div>-->
      </div>
      <button class="remove" aria-label="削除" data-index="${i}">×</button>
    `;
    chips.appendChild(el);
  });

/*
  if (selected.length > 0) {
    const stops = selected.map((c, i) => `${c.hex} ${Math.round((i / Math.max(1, selected.length - 1)) * 100)}%`);
    preview.style.background = `linear-gradient(90deg, ${stops.join(",")})`;
    preview.textContent = "";
  } else {
    preview.style.background = "none";
    preview.textContent = "（ここにグラデーションプレビュー）";
  }
  */

  count.textContent = selected.length;
  addBtn.disabled = selected.length >= 1;

 // 推定感情（ボタンの活性/非活性だけ管理） 
  const emos = calcDominantEmotions(selected, 2);
  const hasEmos = emos.length > 0;

  // 映画検索ボタン・推定感情ボタンの有効/無効
  recBtn.disabled = emos.length === 0;
  showEmoBtn.disabled = !hasEmos;

  // 色がなくなった / 感情推定できない時は表示も消す
  if (!hasEmos) {
    inferredRow.style.display = "none";
    inferredEl.textContent = "";
  }
}



// ---------- ログ送信 ----------
async function logColorExperiment(emos, recommendResults) {
  try {
    const payload = {
      selected_colors: selected.map(c => c.hex),
      inferred_emotions: emos,
      color_details: selected,        // hex, rgb, top1, top2 など
      topk: 10,
      min_review_count: 5,
      use_boost: true,
      recommend_results: recommendResults
    };

    await fetch("/api/log_color_experiment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (e) {
    console.warn("log_color_experiment failed:", e);
  }
}

// ---------- イベント ----------
addBtn.addEventListener("click", () => {
  if (selected.length >= 1) return;
  const hex = normalizeHex(colorInput.value);
  const rgb = hexToRgbArray(hex);

  let entry = palette.find(e => e.hex === hex);
  if (!entry && palette.length > 0) {
    entry = nearestEntryByRgb(hex);
  }

  let top1 = { label: "love", pct: null };
  let top2 = null;

  if (entry && entry.top && entry.top.length) {
    top1 = entry.top[0] || top1;
    top2 = entry.top[1] || null;
  } else if (palette.length === 0) {
    errorBox.textContent = "マッピングが空のため推定できません。color_top2.json の配置・形式を確認してください。";
  }

  if (isPinkish(rgb)) {
    const hasLoveTop1 = top1 && top1.label === "love";
    const hasLoveTop2 = top2 && top2.label === "love";
    if (!hasLoveTop1) {
      if (hasLoveTop2) {
        const tmp = top1; top1 = top2; top2 = tmp;
      } else {
        const prev = top1;
        top1 = { label: "love", pct: (prev?.pct ?? 50) + 10 };
        top2 = prev && prev.label !== "unknown" ? prev : top2;
      }
    }
  }

  //黄色バイアス
  if (isYellowish(rgb) && top1 && top1.label === "love") {
    top1 = { label: "joy", pct: top1.pct ?? 60 };
    top2 = { label: "love", pct:top2?.pct ?? 40}
  }
   
  selected.push({ hex, rgb, top1, top2 });
  render();
});

chips.addEventListener("click", (e) => {
  if (e.target.classList.contains("remove")) {
    const idx = Number(e.target.dataset.index);
    selected.splice(idx, 1);
    render();
  }
});

clearBtn.addEventListener("click", () => {
  selected = [];
  results.innerHTML = "";
  errorBox.textContent = "";
  inferredRow.style.display = "none";
  inferredEl.textContent = "";
  render();
});

// 映画レコメンド：推定感情2つの結果を合算して上位10件だけ表示 & ログ送信
recBtn.addEventListener("click", async () => {
  const emos = calcDominantEmotions(selected, 2);
  if (emos.length === 0) return;

  results.innerHTML = "<p>計算中…</p>";
  errorBox.textContent = "";

  try {
    results.innerHTML = ""; // いったんクリア

    const recommendResultsPerEmotion = {};   // emotion → 映画リスト（ログ用）
    const combinedMap = new Map();          // movie.id → 映画オブジェクト（ベストスコアを保持）

    // それぞれの感情について API 叩く
    for (const emo of emos) {
      const payload = {
        emotion: emo,
        topk: 10,
        min_review_count: 5,
        use_boost: true,
      };

      const res = await fetch("/api/recommend_by_emotion_from_color", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || `Server error for emotion=${emo}`);
      }

      const list = data.results || [];
      recommendResultsPerEmotion[emo] = list; // ログ用に保存

      // 合算用マップに詰める（同じ映画が複数感情に出たら、emotion_score が高いほうを採用）
      list.forEach((m) => {
        const existing = combinedMap.get(m.id);
        const newScore = m.emotion_score ?? 0;
        const oldScore = existing?.emotion_score ?? -Infinity;

        if (!existing || newScore > oldScore) {
          combinedMap.set(m.id, m);
        }
      });
    }

    // Map → 配列に変換して、emotion_score でソート
    const combinedList = Array.from(combinedMap.values()).sort(
      (a, b) => (b.emotion_score ?? 0) - (a.emotion_score ?? 0)
    );

    // 上位10件だけ取る
    const top10 = combinedList.slice(0, 10);

    // 画面表示：1つのブロックにまとめて表示
    const block = document.createElement("section");
    block.className = "result-block";
    block.innerHTML = `
      
      <ol class="result-list"></ol>
    `;
    results.appendChild(block);
    const listEl = block.querySelector("ol");

    if (top10.length === 0) {
      const li = document.createElement("li");
      li.textContent = "候補が見つかりませんでした。";
      listEl.appendChild(li);
    } else {
      top10.forEach((m, idx) => {
        const li = document.createElement("li");

        // ジャンル名
        let genreNames = [];
        if (Array.isArray(m.genre_ids)) {
          genreNames = genreIdsToNames(m.genre_ids);
        } else if (Array.isArray(m.genres)) {
          genreNames = m.genres;
        }

        const jpRatingText = formatJpRating(m);

        li.className = "result-item";
        li.innerHTML = `
          <div><strong>${idx + 1}. ${m.title} (${m.year || "?"})</strong></div>
          <!--<div>emotion score (${m.emotion}): ${m.emotion_score}</div>-->
          <div>vote avg: ${m.vote_average}/10  (${m.vote_count} votes)</div>
          <p><b>${jpRatingText}</b></p>
          <p><b>ジャンル：</b> ${genreNames.join(", ")}</p>

          <details class="overview-details">
            <summary class="overview-summary">あらすじを読む</summary>
            <p class="overview-text">${m.overview || ""}</p>
          </details>
        `;
        listEl.appendChild(li);
      });
    }

    // ログには「感情別のリスト」と「合算Top10」の両方入れておくと分析しやすい
    const recommendResultsForLog = {
      per_emotion: recommendResultsPerEmotion,
      combined_top10: top10,
    };
    await logColorExperiment(emos, recommendResultsForLog);

  } catch (err) {
    console.error(err);
    results.innerHTML = "";
    errorBox.textContent = `エラー: ${err.message}`;
  }
});

// 推定感情を表示ボタン
showEmoBtn.addEventListener("click", () => {
  const emos = calcDominantEmotions(selected, 2);
  if (!emos.length) return;

  inferredEl.textContent = emos.join(", ");
  inferredRow.style.display = "block";
});


// ---------- 初期処理 ----------
render();
loadColorMap();