/* ==========================================================================
   Habit Quest · Emberdeep Ledger
   Vanilla JS: pixel sprites, procedural sigils, animated embers and a tiny
   client for the local JSON API.
   ========================================================================== */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function readPreference(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function writePreference(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* private windows may refuse storage; sound still works for this visit */
    }
  }

  const app = {
    dashboard: null,
    busy: false,
    sound: readPreference("hq-sound") === "on",
    booted: false,
    removeTarget: null,
    audio: null,
    previousFocus: null,
  };

  /* ---------------------------------------------------------------------- *
   * Pixel art
   * ---------------------------------------------------------------------- */

  const HERO_PALETTE = {
    g: "#e8c173",
    G: "#a97c35",
    o: "#0a0d18",
    h: "#2a3454",
    H: "#3f4f78",
    f: "#e8b58d",
    e: "#8ff5e2",
    r: "#8f2540",
    R: "#d8475f",
    s: "#aab6d4",
    w: "#fff6dd",
  };

  const HERO_SPRITE = [
    "....................",
    "....................",
    "....................",
    "........ghhg........",
    ".......ghhhhg.......",
    "......ghhhhhhg......",
    ".....ghhhhhhhhg.....",
    "....gGhhhhhhhhGg....",
    "....gGhhoooohhGg....",
    "....gGhheffehhGg....",
    "....gGhhffffhhGg....",
    "....gGhhoooohhGg....",
    ".....GrrrrrrrrG.....",
    "....GrrrrrrrrrrG....",
    "...orrrrRRRRrrrro...",
    "..orrrrrRRRRrrrrro..",
    "..orrrrrggggrrrrro..",
    "...orrrrRRRRrrrro...",
    ".....orrRRRRrro.....",
    ".......orrrro.......",
  ];

  const BOSS_PALETTE = {
    o: "#140f24",
    p: "#3b2b5e",
    P: "#5b4488",
    r: "#8f2540",
    R: "#e2506b",
    e: "#ff4d5e",
    E: "#ffdfe3",
    w: "#ffe6ea",
  };

  const BOSS_SPRITE = [
    "........................",
    "..o..................o..",
    "..oRo..............oRo..",
    "...oRo............oRo...",
    "....oRoo........ooRo....",
    ".....oRRooooooooRRo.....",
    "...oooooooooooooooooo...",
    "..ooppppppppppppppppoo..",
    ".oppppppppppppppppppppo.",
    ".opppPppppppppppppppppo.",
    "oppppRRpppppppppppRRpppo",
    "oppppRRpppppppppppRRpppo",
    "oppppppppppppppppppppppo",
    "oppppppppppppppppppppppo",
    "opppppppwwwwwwwwpppppppo",
    ".oppppwpwppppwpwppppppo.",
    ".ooppppppppppppppppppoo.",
    "..oooooooooooooooooooo..",
    "...oo..oo....oo..oo.....",
    "........................",
  ];

  function paintSprite(canvas, rows, palette) {
    const width = rows[0].length;
    const height = rows.length;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, width, height);
    rows.forEach((row, y) => {
      for (let x = 0; x < width; x += 1) {
        const color = palette[row[x]];
        if (!color) continue;
        ctx.fillStyle = color;
        ctx.fillRect(x, y, 1, 1);
      }
    });
  }

  /* Procedural habit sigils: a tiny mirrored rune, unique per quest name. */
  const SIGIL_PALETTES = [
    ["#ffd08a", "#ff8a3d", "#7a2e1e"],
    ["#a9fff1", "#79e6d2", "#1c4f47"],
    ["#d8b8ff", "#a07bd8", "#33204f"],
    ["#ffb3c0", "#e2506b", "#4a1424"],
    ["#ffe9ad", "#e8c173", "#4a3512"],
  ];

  function hashString(value) {
    let hash = 2166136261;
    for (let i = 0; i < value.length; i += 1) {
      hash ^= value.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function mulberry32(seed) {
    let value = seed;
    return () => {
      value |= 0;
      value = (value + 0x6d2b79f5) | 0;
      let t = Math.imul(value ^ (value >>> 15), 1 | value);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function drawSigil(canvas, name) {
    const seed = hashString(name);
    const random = mulberry32(seed);
    const palette = SIGIL_PALETTES[seed % SIGIL_PALETTES.length];
    const size = 7;
    const half = 4;
    const cells = [];
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < half; x += 1) {
        const edge = x === 0 || y === 0 || y === size - 1;
        const chance = edge ? 0.3 : 0.46;
        cells.push(random() < chance);
      }
    }
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, size, size);
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < half; x += 1) {
        if (!cells[y * half + x]) continue;
        const color = random() < 0.12 ? palette[2] : random() < 0.55 ? palette[0] : palette[1];
        ctx.fillStyle = color;
        ctx.fillRect(x, y, 1, 1);
        ctx.fillRect(size - 1 - x, y, 1, 1);
      }
    }
    // A bright core keeps every sigil feeling intentional.
    ctx.fillStyle = palette[0];
    ctx.fillRect(3, 3, 1, 1);
  }

  /* ---------------------------------------------------------------------- *
   * Atmosphere: drifting embers, dust and celebration bursts
   * ---------------------------------------------------------------------- */

  class Atmosphere {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.particles = [];
      this.bursts = [];
      this.pointer = { x: 0, y: 0, tx: 0, ty: 0 };
      this.reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      this.frame = this.frame.bind(this);
      this.resize();
      this.seed();
      this.bind();
      requestAnimationFrame(this.frame);
    }

    resize() {
      this.dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.width = window.innerWidth;
      this.height = window.innerHeight;
      this.canvas.width = Math.floor(this.width * this.dpr);
      this.canvas.height = Math.floor(this.height * this.dpr);
      this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    }

    seed() {
      const count = this.reduced ? 24 : 64;
      this.particles = Array.from({ length: count }, () => this.makeParticle(true));
    }

    makeParticle(anywhere = false) {
      const ember = Math.random() < 0.72;
      return {
        x: Math.random() * this.width,
        y: anywhere ? Math.random() * this.height : this.height + 12,
        radius: ember ? 0.7 + Math.random() * 1.7 : 0.5 + Math.random() * 1.1,
        speed: ember ? 0.18 + Math.random() * 0.4 : 0.05 + Math.random() * 0.14,
        drift: Math.random() * Math.PI * 2,
        driftSpeed: 0.2 + Math.random() * 0.5,
        alpha: ember ? 0.25 + Math.random() * 0.5 : 0.08 + Math.random() * 0.16,
        ember,
        depth: 0.3 + Math.random() * 0.7,
        phase: Math.random() * Math.PI * 2,
      };
    }

    bind() {
      window.addEventListener("resize", () => this.resize());
      if (this.reduced) return;
      window.addEventListener("pointermove", (event) => {
        this.pointer.tx = (event.clientX / this.width - 0.5) * 18;
        this.pointer.ty = (event.clientY / this.height - 0.5) * 12;
      });
    }

    burst(x, y, colors = ["#ffd08a", "#ff9a4d", "#ffe6a6"], count = 26) {
      if (this.reduced) return;
      for (let i = 0; i < count; i += 1) {
        const angle = Math.random() * Math.PI * 2;
        const speed = 1.5 + Math.random() * 5;
        this.bursts.push({
          x,
          y,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed - 1.4,
          life: 1,
          decay: 0.012 + Math.random() * 0.02,
          size: 1 + Math.random() * 2.4,
          color: colors[Math.floor(Math.random() * colors.length)],
        });
      }
      if (this.bursts.length > 500) this.bursts.splice(0, this.bursts.length - 500);
    }

    frame(now) {
      const delta = Math.min(48, now - (this.last || now));
      this.last = now;
      this.pointer.x += (this.pointer.tx - this.pointer.x) * 0.04;
      this.pointer.y += (this.pointer.ty - this.pointer.y) * 0.04;

      const ctx = this.ctx;
      ctx.clearRect(0, 0, this.width, this.height);
      ctx.save();
      ctx.translate(this.pointer.x, this.pointer.y);

      for (const particle of this.particles) {
        particle.y -= particle.speed * (delta / 16);
        particle.x += Math.sin(particle.drift + now / 2400) * 0.18 * (delta / 16);
        particle.drift += 0.002 * (delta / 16);
        if (particle.y < -14) {
          particle.y = this.height + 12;
          particle.x = Math.random() * this.width;
        }
        const flicker = 0.65 + 0.35 * Math.sin(now / 420 + particle.phase);
        ctx.globalAlpha = particle.alpha * flicker;
        ctx.fillStyle = particle.ember ? "rgba(255,154,77,1)" : "rgba(196,214,255,1)";
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
        ctx.fill();
      }

      for (let i = this.bursts.length - 1; i >= 0; i -= 1) {
        const spark = this.bursts[i];
        spark.x += spark.vx;
        spark.y += spark.vy;
        spark.vy += 0.09;
        spark.vx *= 0.985;
        spark.life -= spark.decay;
        if (spark.life <= 0) {
          this.bursts.splice(i, 1);
          continue;
        }
        ctx.globalAlpha = Math.max(0, spark.life);
        ctx.fillStyle = spark.color;
        ctx.beginPath();
        ctx.arc(spark.x, spark.y, spark.size, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
      ctx.globalAlpha = 1;
      requestAnimationFrame(this.frame);
    }
  }

  /* ---------------------------------------------------------------------- *
   * Tiny synth for feedback (no audio files)
   * ---------------------------------------------------------------------- */

  const Sound = {
    ensure() {
      if (!app.audio) {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return null;
        app.audio = new AudioContext();
      }
      if (app.audio.state === "suspended") app.audio.resume();
      return app.audio;
    },

    tone(frequency, start, duration, options = {}) {
      const audio = this.ensure();
      if (!audio) return;
      const { type = "sine", volume = 0.06, slide = 0 } = options;
      const oscillator = audio.createOscillator();
      const gain = audio.createGain();
      const t0 = audio.currentTime + start;
      oscillator.type = type;
      oscillator.frequency.setValueAtTime(frequency, t0);
      if (slide) oscillator.frequency.exponentialRampToValueAtTime(slide, t0 + duration);
      gain.gain.setValueAtTime(0.0001, t0);
      gain.gain.exponentialRampToValueAtTime(volume, t0 + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
      oscillator.connect(gain).connect(audio.destination);
      oscillator.start(t0);
      oscillator.stop(t0 + duration + 0.03);
    },

    noise(start, duration, volume = 0.05) {
      const audio = this.ensure();
      if (!audio) return;
      const samples = Math.floor(audio.sampleRate * duration);
      const buffer = audio.createBuffer(1, samples, audio.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < samples; i += 1) {
        data[i] = (Math.random() * 2 - 1) * (1 - i / samples);
      }
      const source = audio.createBufferSource();
      const gain = audio.createGain();
      const filter = audio.createBiquadFilter();
      filter.type = "highpass";
      filter.frequency.value = 900;
      gain.gain.value = volume;
      source.buffer = buffer;
      source.connect(filter).connect(gain).connect(audio.destination);
      source.start(audio.currentTime + start);
    },

    play(kind) {
      if (!app.sound) return;
      switch (kind) {
        case "claim":
          this.noise(0, 0.16, 0.05);
          this.tone(880, 0, 0.2, { type: "triangle", volume: 0.045, slide: 330 });
          this.tone(1320, 0.02, 0.12, { type: "sine", volume: 0.025 });
          break;
        case "levelup":
          [523.25, 659.25, 783.99, 1046.5].forEach((note, index) => {
            this.tone(note, index * 0.11, 0.5, { type: "triangle", volume: 0.05 });
          });
          break;
        case "relic":
          this.tone(1174.66, 0, 0.35, { type: "sine", volume: 0.05 });
          this.tone(1567.98, 0.09, 0.5, { type: "sine", volume: 0.035 });
          break;
        case "boss":
          this.noise(0, 0.5, 0.06);
          this.tone(110, 0, 0.6, { type: "sawtooth", volume: 0.04, slide: 45 });
          break;
        case "error":
          this.tone(150, 0, 0.22, { type: "square", volume: 0.03, slide: 110 });
          break;
        default:
          break;
      }
    },
  };

  /* ---------------------------------------------------------------------- *
   * Small DOM helpers
   * ---------------------------------------------------------------------- */

  function makeIcon(name, className = "icon") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", className);
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#i-${name}`);
    svg.appendChild(use);
    return svg;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  const numberFormat = new Intl.NumberFormat("en-GB");

  function formatNumber(value) {
    return numberFormat.format(value);
  }

  function formatToday(iso) {
    const date = new Date(`${iso}T12:00:00`);
    return date.toLocaleDateString("en-GB", {
      weekday: "long",
      day: "numeric",
      month: "long",
    });
  }

  function formatRelative(iso, todayIso) {
    if (!iso) return "";
    const oneDay = 86400000;
    const diff = Math.round((new Date(`${todayIso}T12:00:00`) - new Date(`${iso}T12:00:00`)) / oneDay);
    if (diff <= 0) return "Today";
    if (diff === 1) return "Yesterday";
    if (diff < 7) return `${diff} days ago`;
    return new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  }

  function isStreakAlive(lastDone, todayIso) {
    if (!lastDone) return false;
    const diff = Math.round((new Date(`${todayIso}T12:00:00`) - new Date(`${lastDone}T12:00:00`)) / 86400000);
    return diff === 0 || diff === 1;
  }

  async function api(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("The dungeon gate returned an unreadable answer.");
    }
    if (!response.ok || !data.ok) throw new Error(data.error || `Request failed (${response.status}).`);
    return data;
  }

  /* ---------------------------------------------------------------------- *
   * Rendering
   * ---------------------------------------------------------------------- */

  const RANKS = [
    { name: "Novice", level: 1 },
    { name: "Apprentice", level: 5 },
    { name: "Squire", level: 10 },
    { name: "Knight", level: 15 },
    { name: "Champion", level: 20 },
    { name: "Legend", level: 30 },
  ];

  const iconForAchievement = (id) => ({
    first_quest: "sword",
    streak_3: "flame",
    streak_7: "flame",
    streak_30: "flame",
    level_5: "shield",
    level_10: "crown",
    quests_10: "scroll",
    quests_50: "star",
    boss_slayer: "skull",
  }[id] || "star");

  function render(dashboard) {
    app.dashboard = dashboard;
    renderHero(dashboard);
    renderRankLadder(dashboard);
    renderStreaks(dashboard);
    renderMilestones(dashboard);
    renderBoss(dashboard);
    renderQuests(dashboard);
    renderRelics(dashboard);
    renderHeatmap(dashboard);
    renderLog(dashboard);
    $("#today-label").textContent = formatToday(dashboard.today);
    $("#quest-tally").textContent = `${dashboard.stats.completed_today} of ${dashboard.stats.quests} cleared today`;
    if (dashboard.state_path) $("#state-path").textContent = dashboard.state_path;
    $("#empty-state").hidden = dashboard.habits.length > 0;
    $("#quest-list").hidden = dashboard.habits.length === 0;
    const undo = $("#undo-btn");
    undo.disabled = dashboard.recent.length === 0;
  }

  function renderHero(dashboard) {
    const { hero, stats } = dashboard;
    $("#hero-name").textContent = hero.name;
    $("#hero-rank").textContent = hero.rank;
    $("#hero-level").textContent = hero.level;
    $("#hero-level-text").textContent = hero.level;
    $("#xp-current").textContent = formatNumber(hero.xp);
    $("#xp-next").textContent = formatNumber(hero.xp_next);
    $("#stat-completions").textContent = formatNumber(stats.completions);
    $("#stat-best").textContent = formatNumber(stats.best_streak);
    $("#stat-days").textContent = formatNumber(stats.active_days);
    const pct = clamp(hero.xp_pct, 0, 100);
    $("#xp-fill").style.width = `${pct}%`;
    const circumference = 2 * Math.PI * 88;
    $("#ring-progress").style.strokeDashoffset = String(circumference * (1 - pct / 100));
  }

  function renderRankLadder(dashboard) {
    const { hero } = dashboard;
    const list = $("#rank-ladder");
    list.replaceChildren();
    for (const rank of RANKS) {
      const item = el("li", "");
      if (hero.level >= rank.level) item.classList.add("is-reached");
      if (hero.rank === rank.name) item.classList.add("is-current");
      item.appendChild(el("span", "rank-node"));
      item.appendChild(el("span", "rank-name", rank.name));
      item.appendChild(el("span", "rank-level", `LV ${rank.level}`));
      list.appendChild(item);
    }
  }

  function renderStreaks(dashboard) {
    const list = $("#streak-list");
    list.replaceChildren();
    const burning = dashboard.habits
      .filter((habit) => habit.streak > 0)
      .sort((a, b) => b.streak - a.streak)
      .slice(0, 3);
    if (!burning.length) {
      list.appendChild(el("li", "streak-empty", "No embers burning yet. Claim a quest to spark one."));
      return;
    }
    for (const habit of burning) {
      const item = el("li", "");
      item.appendChild(makeIcon("flame"));
      item.appendChild(el("span", "streak-name", habit.name));
      const value = el("b", "", String(habit.streak));
      value.appendChild(el("small", "", "d"));
      item.appendChild(value);
      list.appendChild(item);
    }
  }

  function renderMilestones(dashboard) {
    const { hero, next_relic: nextRelic, heatmap, stats } = dashboard;
    const rank = hero.next_rank;
    $("#ms-rank").textContent = rank ? rank.name : "Legend";
    $("#ms-rank-sub").textContent = rank
      ? `${formatNumber(rank.xp_needed)} XP to level ${rank.level}`
      : "The highest rank is yours.";
    $("#ms-relic").textContent = nextRelic ? nextRelic.name : "All relics claimed";
    $("#ms-relic-sub").textContent = nextRelic ? nextRelic.desc : "Every ember remembers you.";
    const week = heatmap.slice(-7).reduce((total, day) => total + day.count, 0);
    $("#ms-week").textContent = formatNumber(week);
    $("#ms-week-sub").textContent = `quests cleared · ${stats.completed_today} today`;
  }

  function renderBoss(dashboard) {
    const { boss } = dashboard;
    const card = $("#boss-card");
    card.classList.toggle("is-defeated", boss.defeated);
    $("#boss-name").textContent = boss.name;
    $("#boss-hp-label").textContent = `${boss.hp} / ${boss.max}`;
    $("#hp-fill").style.width = boss.max ? `${(boss.hp / boss.max) * 100}%` : "0%";
    const pips = $("#boss-pips");
    pips.replaceChildren();
    for (let index = 0; index < boss.max; index += 1) {
      const pip = document.createElement("i");
      if (index < boss.hp) pip.classList.add("is-full");
      pips.appendChild(pip);
    }
    let hint;
    if (!boss.max) hint = "Add a quest to wake the boss.";
    else if (boss.defeated) hint = "Vanquished. Another will rise tomorrow — be ready.";
    else hint = `Clear ${boss.hp} more quest${boss.hp === 1 ? "" : "s"} to banish them before midnight.`;
    $("#boss-hint").textContent = hint;
  }

  function renderQuests(dashboard) {
    const list = $("#quest-list");
    list.replaceChildren();
    for (const habit of dashboard.habits) {
      const alive = isStreakAlive(habit.last_done, dashboard.today);
      const item = el("li", `quest${habit.done_today ? " is-cleared" : ""}`);
      item.dataset.habit = habit.name;

      const sigil = el("div", "quest-sigil");
      const canvas = document.createElement("canvas");
      drawSigil(canvas, habit.name);
      sigil.appendChild(canvas);

      const body = el("div", "quest-body");
      const title = el("div", "quest-title");
      title.appendChild(el("span", "quest-name", habit.name));
      if (habit.done_today) title.appendChild(el("span", "quest-stamp", "cleared"));
      body.appendChild(title);

      const meta = el("div", "quest-meta");
      meta.appendChild(makeIcon("flame"));
      meta.appendChild(el("span", "", alive ? `${habit.streak}-day streak` : "streak cold"));
      meta.appendChild(el("span", "dot"));
      meta.appendChild(el("span", "", `${habit.completions} cleared`));
      meta.appendChild(el("span", "dot"));
      meta.appendChild(el("span", "best", `best ${habit.best_streak}`));
      body.appendChild(meta);

      const reward = el("div", "quest-reward");
      reward.appendChild(document.createTextNode(`+${habit.xp}`));
      reward.appendChild(el("span", "", "XP"));

      let claim;
      if (habit.done_today) {
        claim = el("button", "claim is-cleared");
        claim.type = "button";
        claim.disabled = true;
        claim.appendChild(makeIcon("check"));
        claim.appendChild(document.createTextNode("Cleared"));
      } else {
        claim = el("button", "claim");
        claim.type = "button";
        claim.appendChild(makeIcon("sword"));
        claim.appendChild(document.createTextNode("Claim"));
        claim.addEventListener("click", (event) => claimQuest(habit.name, event));
      }

      const remove = el("button", "quest-remove");
      remove.type = "button";
      remove.title = `Remove ${habit.name}`;
      remove.setAttribute("aria-label", `Remove ${habit.name}`);
      remove.appendChild(makeIcon("trash"));
      remove.addEventListener("click", () => openRemove(habit.name));

      item.append(sigil, body, reward, claim, remove);
      list.appendChild(item);
    }
  }

  function renderRelics(dashboard) {
    const grid = $("#relic-grid");
    grid.replaceChildren();
    const unlocked = dashboard.achievements.filter((item) => item.unlocked).length;
    $("#relic-count").textContent = `${unlocked} / ${dashboard.achievements.length}`;
    for (const relic of dashboard.achievements) {
      const item = el("li", `relic ${relic.unlocked ? "is-unlocked" : "is-locked"}`);
      item.title = relic.unlocked ? `${relic.name} — ${relic.desc}` : `Locked — ${relic.desc}`;
      const medal = el("span", "medal");
      medal.appendChild(makeIcon(relic.unlocked ? iconForAchievement(relic.id) : "lock"));
      item.appendChild(medal);
      item.appendChild(el("span", "relic-name", relic.name));
      grid.appendChild(item);
    }
  }

  function renderHeatmap(dashboard) {
    const heatmap = $("#heatmap");
    heatmap.replaceChildren();
    let total = 0;
    for (const day of dashboard.heatmap) {
      const cell = el("i", `cell lvl-${day.level}`);
      cell.title = `${day.date} · ${day.count} quest${day.count === 1 ? "" : "s"} cleared`;
      if (day.future) cell.classList.add("is-future");
      if (day.date === dashboard.today) cell.classList.add("is-today");
      cell.setAttribute("aria-label", `${day.date}: ${day.count} quests cleared`);
      heatmap.appendChild(cell);
      total += day.count;
    }
    heatmap.setAttribute("aria-label", `Quest activity over the last twelve weeks. ${total} quests cleared.`);
  }

  function renderLog(dashboard) {
    const log = $("#battle-log");
    log.replaceChildren();
    if (!dashboard.recent.length) {
      log.appendChild(el("li", "log-empty", "No victories yet. The first cut is yours to make."));
      return;
    }
    for (const entry of dashboard.recent) {
      const item = el("li", "log-entry");
      const mark = el("span", "log-mark");
      mark.appendChild(makeIcon("sword"));
      const text = el("div", "log-text");
      text.appendChild(el("p", "log-habit", entry.habit));
      text.appendChild(el("p", "log-date", `${formatRelative(entry.date, dashboard.today)} · streak ${entry.streak}`));
      item.append(mark, text, el("span", "log-xp", `+${entry.xp}`));
      log.appendChild(item);
    }
  }

  /* ---------------------------------------------------------------------- *
   * Effects
   * ---------------------------------------------------------------------- */

  function floatXp(x, y, text, sub = "") {
    const node = el("div", "float-xp", text);
    node.style.left = `${x}px`;
    node.style.top = `${y}px`;
    if (sub) {
      const small = el("span", "float-crit", sub);
      small.style.display = "block";
      small.style.textAlign = "center";
      node.appendChild(small);
    }
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 1200);
  }

  function slashFx(rect) {
    const node = el("div", "quest-slash-fx");
    node.style.left = `${rect.left}px`;
    node.style.top = `${rect.top}px`;
    node.style.width = `${rect.width}px`;
    node.style.height = `${rect.height}px`;
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 650);
  }

  function toast(kicker, body, icon = "spark", kind = "") {
    const node = el("div", `toast${kind === "error" ? " is-error" : ""}`);
    const medal = el("span", "toast-medal");
    medal.appendChild(makeIcon(kind === "error" ? "shield" : icon));
    const content = el("div", "toast-content");
    content.appendChild(el("p", "toast-title", kicker));
    content.appendChild(el("p", "toast-body", body));
    node.append(medal, content);
    $("#toasts").appendChild(node);
    setTimeout(() => {
      node.classList.add("is-out");
      setTimeout(() => node.remove(), 380);
    }, 4200);
  }

  function levelUpOverlay(level, rank) {
    const overlay = $("#levelup");
    $("#levelup-level").textContent = level;
    $("#levelup-rank").textContent = rank;
    overlay.hidden = false;
    setTimeout(() => {
      overlay.hidden = true;
    }, 2400);
  }

  function shakeScreen() {
    document.body.classList.remove("shake");
    void document.body.offsetWidth;
    document.body.classList.add("shake");
    setTimeout(() => document.body.classList.remove("shake"), 460);
  }

  async function claimQuest(name, event) {
    if (app.busy) return;
    app.busy = true;
    const item = event.currentTarget.closest(".quest");
    item.classList.add("is-pending");
    const rect = event.currentTarget.getBoundingClientRect();
    try {
      const data = await api("/api/complete", { habit: name });
      const result = data.result;
      slashFx(item.getBoundingClientRect());
      atmosphere.burst(rect.left + rect.width / 2, rect.top + rect.height / 2);
      floatXp(rect.left + rect.width / 2, rect.top - 6, `+${result.xp_awarded}`, result.streak_bonus ? `STREAK BONUS +${result.streak_bonus}` : "");
      Sound.play("claim");
      if (result.leveled_up) {
        setTimeout(() => Sound.play("levelup"), 240);
        setTimeout(() => levelUpOverlay(result.level, data.result.dashboard.hero.rank), 220);
        shakeScreen();
      }
      for (const relic of result.new_achievements) {
        toast("Relic unlocked", `${relic.name} — ${relic.desc}`, iconForAchievement(relic.id), "relic");
        setTimeout(() => Sound.play("relic"), 520);
      }
      const wasDefeated = Boolean(app.dashboard && app.dashboard.boss && app.dashboard.boss.defeated);
      render(data.result.dashboard);
      if (!wasDefeated && data.result.dashboard.boss.defeated) {
        const sprite = $("#boss-sprite").getBoundingClientRect();
        atmosphere.burst(sprite.left + sprite.width / 2, sprite.top + sprite.height / 2, ["#e2506b", "#ff9a4d", "#ffe6a6"], 46);
        setTimeout(() => Sound.play("boss"), 380);
        toast("Dungeon cleared", `${data.result.dashboard.boss.name} has been banished.`, "skull", "relic");
      }
    } catch (error) {
      toast("The quest resisted", error.message, "shield", "error");
      Sound.play("error");
    } finally {
      app.busy = false;
      item.classList.remove("is-pending");
    }
  }

  async function refresh() {
    const response = await fetch("/api/state", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("The ledger could not be read.");
    render(await response.json());
  }

  /* ---------------------------------------------------------------------- *
   * Modals
   * ---------------------------------------------------------------------- */

  function openModal(modal) {
    app.previousFocus = document.activeElement;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeModal(modal) {
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    if ($$(".modal:not([hidden])").length === 0) {
      document.body.style.overflow = "";
    }
    if (app.previousFocus && typeof app.previousFocus.focus === "function") {
      app.previousFocus.focus({ preventScroll: true });
    }
    app.previousFocus = null;
  }

  function closeAllModals() {
    $$(".modal").forEach((modal) => {
      if (!modal.hidden) closeModal(modal);
    });
  }

  function openAdd() {
    $("#add-error").hidden = true;
    $("#add-name").value = "";
    $("#add-xp").value = "20";
    $("#add-xp-value").textContent = "20 XP";
    openModal($("#modal-add"));
    setTimeout(() => $("#add-name").focus(), 60);
  }

  function openRename() {
    if (!app.dashboard) return;
    $("#rename-error").hidden = true;
    $("#rename-name").value = app.dashboard.hero.name;
    openModal($("#modal-rename"));
    setTimeout(() => {
      $("#rename-name").focus();
      $("#rename-name").select();
    }, 60);
  }

  function openRemove(name) {
    app.removeTarget = name;
    $("#remove-name").textContent = name;
    $("#remove-error").hidden = true;
    openModal($("#modal-remove"));
  }

  function showFormError(target, message) {
    target.textContent = message;
    target.hidden = false;
  }

  /* ---------------------------------------------------------------------- *
   * Actions
   * ---------------------------------------------------------------------- */

  async function submitAdd(event) {
    event.preventDefault();
    const name = $("#add-name").value.trim();
    const xp = Number($("#add-xp").value);
    if (!name) {
      showFormError($("#add-error"), "Give your quest a name first.");
      return;
    }
    const button = event.submitter || $("#add-form button[type=submit]");
    button.disabled = true;
    try {
      const data = await api("/api/add", { name, xp });
      render(data.dashboard);
      closeModal($("#modal-add"));
      toast("Quest forged", `“${name}” is now part of your ledger.`, "scroll");
      const addRect = $("#add-open").getBoundingClientRect();
      atmosphere.burst(addRect.left + addRect.width / 2, addRect.top + addRect.height / 2, ["#ffd08a", "#79e6d2"], 18);
    } catch (error) {
      showFormError($("#add-error"), error.message);
      Sound.play("error");
    } finally {
      button.disabled = false;
    }
  }

  async function submitRename(event) {
    event.preventDefault();
    const name = $("#rename-name").value.trim();
    if (!name) {
      showFormError($("#rename-error"), "A hero needs a name.");
      return;
    }
    const button = event.submitter || $("#rename-form button[type=submit]");
    button.disabled = true;
    try {
      const data = await api("/api/rename", { name });
      render(data.dashboard);
      closeModal($("#modal-rename"));
      toast("Name spoken", `The dungeon will remember ${name}.`, "crown");
    } catch (error) {
      showFormError($("#rename-error"), error.message);
      Sound.play("error");
    } finally {
      button.disabled = false;
    }
  }

  async function confirmRemove() {
    if (!app.removeTarget || app.busy) return;
    app.busy = true;
    const button = $("#remove-confirm");
    button.disabled = true;
    const name = app.removeTarget;
    try {
      const data = await api("/api/remove", { habit: name });
      render(data.dashboard);
      closeModal($("#modal-remove"));
      app.removeTarget = null;
      toast("Quest banished", `“${name}” fades from the ledger.`, "trash");
    } catch (error) {
      showFormError($("#remove-error"), error.message);
      Sound.play("error");
    } finally {
      button.disabled = false;
      app.busy = false;
    }
  }

  async function undoLast() {
    if (app.busy) return;
    app.busy = true;
    const button = $("#undo-btn");
    button.disabled = true;
    try {
      const data = await api("/api/undo", {});
      render(data.dashboard);
      toast("Victory rewound", "The last quest has been returned to the gauntlet.", "undo");
    } catch (error) {
      toast("Nothing to rewind", error.message, "shield", "error");
      Sound.play("error");
    } finally {
      app.busy = false;
      if (app.dashboard) button.disabled = app.dashboard.recent.length === 0;
    }
  }

  async function summonDemo() {
    if (app.busy) return;
    app.busy = true;
    const button = $("#empty-demo");
    button.disabled = true;
    try {
      const data = await api("/api/demo", {});
      render(data.dashboard);
      toast("The dungeon stirs", "A demo adventure has been summoned.", "spark");
    } catch (error) {
      toast("The ritual failed", error.message, "shield", "error");
    } finally {
      app.busy = false;
      button.disabled = false;
    }
  }

  function toggleSound() {
    app.sound = !app.sound;
    writePreference("hq-sound", app.sound ? "on" : "off");
    updateSoundButton();
    if (app.sound) {
      Sound.ensure();
      Sound.play("relic");
    }
  }

  function updateSoundButton() {
    const button = $("#sound-toggle");
    button.classList.toggle("is-on", app.sound);
    button.setAttribute("aria-pressed", String(app.sound));
    button.title = app.sound ? "Sound on" : "Sound off";
    button.querySelector("use").setAttribute("href", app.sound ? "#i-sound" : "#i-mute");
  }

  /* Taunts ----------------------------------------------------------------- */

  const TAUNTS = [
    "You call that a streak? I have slept for a thousand years.",
    "Tomorrow is a perfectly good day to start. And the day after that.",
    "I feed on open tabs and “later”.",
    "One more episode. One more scroll. One more excuse.",
    "Your hero looks tired. Perhaps a nap?",
    "The dungeon is dark. Nobody would notice if you skipped today.",
    "I have already won. You just haven't noticed yet.",
  ];

  function tauntBoss() {
    const bubble = $("#boss-bubble");
    bubble.textContent = TAUNTS[Math.floor(Math.random() * TAUNTS.length)];
    bubble.hidden = false;
    clearTimeout(app.tauntTimer);
    app.tauntTimer = setTimeout(() => {
      bubble.hidden = true;
    }, 4200);
  }

  /* ---------------------------------------------------------------------- *
   * Boot
   * ---------------------------------------------------------------------- */

  let atmosphere;

  async function boot() {
    paintSprite($("#hero-sprite"), HERO_SPRITE, HERO_PALETTE);
    paintSprite($("#boss-sprite"), BOSS_SPRITE, BOSS_PALETTE);
    drawSigil($("#brand-sigil"), "Emberdeep Ledger");
    drawSigil($("#boot-sigil"), "Habit Quest");
    atmosphere = new Atmosphere($("#atmosphere"));

    try {
      await Promise.race([
        document.fonts ? document.fonts.ready : Promise.resolve(),
        sleep(1400),
      ]);
      await refresh();
      updateSoundButton();
      setTimeout(() => {
        $("#boot").classList.add("is-gone");
        app.booted = true;
      }, 320);
    } catch (error) {
      const boot = $("#boot");
      $(".boot-text", boot).textContent = "The gate is stuck";
      $(".boot-sub", boot).textContent = "click to try again";
      boot.style.cursor = "pointer";
      boot.addEventListener("click", () => window.location.reload(), { once: true });
      console.error(error);
    }
  }

  function bind() {
    $("#add-open").addEventListener("click", openAdd);
    $("#empty-add").addEventListener("click", openAdd);
    $("#empty-demo").addEventListener("click", summonDemo);
    $("#hero-name-btn").addEventListener("click", openRename);
    $("#add-form").addEventListener("submit", submitAdd);
    $("#rename-form").addEventListener("submit", submitRename);
    $("#remove-confirm").addEventListener("click", confirmRemove);
    $("#undo-btn").addEventListener("click", undoLast);
    $("#sound-toggle").addEventListener("click", toggleSound);
    $("#boss-taunt").addEventListener("click", tauntBoss);
    $("#add-xp").addEventListener("input", (event) => {
      $("#add-xp-value").textContent = `${event.target.value} XP`;
    });

    $$("[data-close]").forEach((node) => {
      node.addEventListener("click", () => closeModal(node.closest(".modal")));
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeAllModals();
        return;
      }
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
      const modalOpen = $$(".modal:not([hidden])").length > 0;
      if (!typing && !modalOpen && (event.key === "n" || event.key === "N")) {
        event.preventDefault();
        openAdd();
      }
    });
  }

  bind();
  boot();
})();
