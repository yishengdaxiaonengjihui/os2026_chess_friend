/* 数字人适配层（第三阶段，自研）：
 * 优先：魔珐星云 XmovAvatar Web SDK（3D 渲染 + TTS + 口型同步 + 客户端打断）
 * 降级：浏览器 Web Speech API 中文朗读（适老化友好）→ 仅文字提示
 *
 * 问题2：内置「有限任务队列 + 状态机」调度器。
 *   - 落子评论 = 低优先级游戏操作：不粗暴打断正在播放的语音，新评论入队排队，
 *     队列最大 2 条，超出丢弃最旧（过时棋局评论）。
 *   - 用户主动说话 = 高优先级社交行为：bargeIn() 强制终止当前语音、清空队列、优先回复。
 *   - 保证棋盘丝滑、每句 AI 发言完整说完。
 *
 * 问题11：情绪超时自动重置——非平静情绪持续 N 秒无新事件自动恢复 neutral。
 *
 * 用法：
 *   var ad = new AvatarAdapter({ appId, appSecret, gateway });
 *   ad.init().then(function(){ if (ad.mode === 'xmov') ... });
 *   ad.speak({ speech_text, ssml, emotion_sdk });   // 低优先级，入队
 *   ad.bargeIn({ ... });                            // 高优先级，强停+清队+立即播
 *   ad.stop();                                      // 全部停止（退出对局等）
 *   ad.onState = fn;    // "speaking"/"idle"/"thinking"
 */
(function () {
  "use strict";

  var SDK_URL = "https://media.xingyun3d.com/xingyun3d/general/litesdk/xmovAvatar@latest.js";
  var sdkLoading = false;

  function loadSdk(timeoutMs) {
    return new Promise(function (resolve, reject) {
      if (window.XmovAvatar) { resolve(); return; }
      if (sdkLoading) { return; }
      sdkLoading = true;
      var s = document.createElement("script");
      s.src = SDK_URL;
      s.async = true;
      s.onload = function () { resolve(); };
      s.onerror = function () { reject(new Error("SDK 加载失败")); };
      document.head.appendChild(s);
      setTimeout(function () {
        if (!window.XmovAvatar) { reject(new Error("SDK 加载超时")); }
      }, timeoutMs || 8000);
    });
  }

  function pickZhVoice() {
    if (!window.speechSynthesis) { return null; }
    var voices = window.speechSynthesis.getVoices();
    if (!voices || !voices.length) { return null; }
    return voices.find(function (v) { return /^zh|cmn/i.test(v.lang); }) || null;
  }

  function estimateMs(text) {
    var n = (text || "").length;
    // 保守估算：字数*130ms + 800ms 安全余量，确保"播完"回调晚于实际发声结束，
    // 这样恢复麦克风时 TTS 已彻底播完，尾音不会被收进去
    return Math.max(1500, n * 130 + 800);
  }

  function AvatarAdapter(opts) {
    this.opts = opts || {};
    this.avatar = null;
    this.mode = "none"; // "xmov" | "speech" | "none"
    this.onState = null;
    // 回声防护：数字人发声开始/结束回调（前端用于暂停/恢复麦克风识别）
    this.onSpeechStart = null;
    this.onSpeechEnd = null;
    // 回声防护：每句台词播放完成回调（前端按播放结束时刻记入字幕历史，
    // 供"相邻行相似度+时间窗"回声检测比对——回声发生在播放结束后的余音期）
    this.onSpeechDone = null;
    // 最近一句 AI 台词（供回声文本过滤兜底）
    this.lastSpeechText = "";
    // 问题2：调度器状态
    this._queue = [];          // 待播语音任务（低优先级，max 2）
    this._playing = false;
    this._maxQueue = 2;
    this._timer = null;
    // 问题11：情绪 TTL
    this._emotionTimer = null;
    this._lastEmotion = "平静";
    var self = this;
    if (window.speechSynthesis) {
      window.speechSynthesis.onvoiceschanged = function () { pickZhVoice(); };
    }
  }

  AvatarAdapter.prototype.init = function () {
    var self = this;
    if (this._initPromise) { return this._initPromise; }
    this._initPromise = loadSdk(8000).then(function () {
      try {
        self.avatar = new window.XmovAvatar({
          containerId: "#avatar-container",
          appId: self.opts.appId,
          appSecret: self.opts.appSecret,
          gatewayServer: self.opts.gateway,
          enableClientInterrupt: true,
          onMessage: function (err) {
            console.error("[xmov]", err && (err.code + " " + err.message));
          },
        });
        self.avatar.init({
          onDownloadProgress: function (p) {
            if (p === 100 && self.onReady) { self.onReady(); }
          },
        });
        self.mode = "xmov";
      } catch (e) {
        console.warn("[avatar] XmovAvatar 初始化失败，降级朗读", e);
        self.mode = window.speechSynthesis ? "speech" : "none";
      }
    }).catch(function (err) {
      console.warn("[avatar] 星云 SDK 不可用，降级：", err && err.message);
      self.mode = window.speechSynthesis ? "speech" : "none";
    });
    return this._initPromise;
  };

  // ---- 问题2：队列调度 ----

  /* 低优先级：落子评论。正在播则排队；队列满(2)丢弃最旧（过时评论）。 */
  AvatarAdapter.prototype.speak = function (cmd) {
    if (!cmd || !cmd.speech_text) { return; }
    if (this._queue.length >= this._maxQueue) { this._queue.shift(); } // 丢最旧
    this._queue.push(cmd);
    this.setState("thinking"); // 排队/思索
    this._playNext();
  };

  /* 高优先级：用户主动说话。强停当前 + 清空队列 + 立即回复。 */
  AvatarAdapter.prototype.bargeIn = function (cmd) {
    this._stopCurrent();
    this._queue = [];
    this._playing = false;
    if (cmd && cmd.speech_text) {
      this._queue.push(cmd);
      this._playNext();
    } else {
      this.setState("idle");
    }
  };

  /* 全部停止（离开对局 / 新开对局等）。 */
  AvatarAdapter.prototype.stop = function () {
    this._stopCurrent();
    this._queue = [];
    this._playing = false;
    this.setState("idle");
    this._notifySpeechEnd();
  };

  AvatarAdapter.prototype._playNext = function () {
    var self = this;
    if (this._playing) { return; }
    var cmd = this._queue.shift();
    if (!cmd) { this.setState("idle"); this._notifySpeechEnd(); return; }
    this._playing = true;
    this.lastSpeechText = cmd.speech_text || "";
    this.setState("speaking");
    this._notifySpeechStart();
    this._touchEmotion(cmd.emotion_tag || cmd.emotion_sdk || "平静");
    this._doSpeak(cmd, function () {
      self._notifySpeechDone(cmd.speech_text || ""); // 本句播完（时间戳=结束时刻）
      self._playing = false;
      self._playNext();
    });
  };

  /* 回声防护：播放开始/结束通知（供前端暂停/恢复麦克风识别） */
  AvatarAdapter.prototype._notifySpeechStart = function () {
    if (this.onSpeechStart) { try { this.onSpeechStart(); } catch (e) { /* 忽略 */ } }
  };
  AvatarAdapter.prototype._notifySpeechEnd = function () {
    if (this.onSpeechEnd) { try { this.onSpeechEnd(); } catch (e) { /* 忽略 */ } }
  };
  /* 回声防护：单句播完通知（供前端把 AI 台词记入字幕历史，时间贴近回声时刻） */
  AvatarAdapter.prototype._notifySpeechDone = function (text) {
    if (this.onSpeechDone) { try { this.onSpeechDone(text); } catch (e) { /* 忽略 */ } }
  };

  /* 实际播放（按模式），播完调用 done() 继续队列。 */
  AvatarAdapter.prototype._doSpeak = function (cmd, done) {
    var self = this;
    if (!cmd || !cmd.speech_text) { done(); return; }
    if (this.mode === "xmov" && this.avatar) {
      try {
        this.avatar.speak(cmd.ssml || ("<speak>" + cmd.speech_text + "</speak>"), true, true,
          { emotion: cmd.emotion_sdk || "neutral" });
        this._timer = setTimeout(done, estimateMs(cmd.speech_text)); // 按时长估算排队
        return;
      } catch (e) {
        console.warn("[avatar] speak 失败，降级朗读", e);
        this.mode = "speech";
      }
    }
    if (this.mode === "speech" && window.speechSynthesis) {
      var u = new SpeechSynthesisUtterance(cmd.speech_text);
      var v = pickZhVoice();
      if (v) { u.voice = v; }
      u.lang = "zh-CN";
      u.rate = 0.95;
      u.pitch = 1.0;
      u.onend = done;
      u.onerror = done;
      window.speechSynthesis.speak(u);
      return;
    }
    this._timer = setTimeout(done, estimateMs(cmd.speech_text)); // 无语音：按估算
  };

  AvatarAdapter.prototype._stopCurrent = function () {
    if (this._timer) { clearTimeout(this._timer); this._timer = null; }
    if (this.mode === "xmov" && this.avatar) {
      try { this.avatar.interrupt("user"); } catch (e) { /* 忽略 */ }
    }
    if (window.speechSynthesis) { window.speechSynthesis.cancel(); }
  };

  AvatarAdapter.prototype.setState = function (s) {
    if (this.onState) { try { this.onState(s); } catch (e) { /* 忽略 */ } }
  };

  // ---- 问题11：情绪超时自动重置 ----
  AvatarAdapter.prototype._touchEmotion = function (tag) {
    var self = this;
    var neutral = /neutral|平静|沉思|认真/.test(tag);
    if (neutral) { return; } // 平静类无需重置
    this._lastEmotion = tag;
    if (this._emotionTimer) { clearTimeout(this._emotionTimer); }
    this._emotionTimer = setTimeout(function () {
      self._lastEmotion = "平静";
      if (self.onEmotionReset) { try { self.onEmotionReset(); } catch (e) { /* 忽略 */ } }
    }, 6000); // 6 秒无新情绪事件 -> 恢复平静
  };

  AvatarAdapter.prototype.dispose = function () {
    this.stop();
    if (this._emotionTimer) { clearTimeout(this._emotionTimer); this._emotionTimer = null; }
  };

  window.AvatarAdapter = AvatarAdapter;
  window.__avatarAdapter = null;
})();
