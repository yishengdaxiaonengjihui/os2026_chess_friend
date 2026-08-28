/* 数字人适配层（第三阶段，自研）：
 * 优先：魔珐星云 XmovAvatar Web SDK（3D 渲染 + TTS + 口型同步 + 客户端打断）
 * 降级：浏览器 Web Speech API 中文朗读（适老化友好）→ 仅文字提示
 *
 * 用法：
 *   var ad = new AvatarAdapter({ appId, appSecret, gateway });
 *   ad.init().then(function(){ if (ad.mode === 'xmov') ... });
 *   ad.speak({ speech_text, ssml, emotion_sdk });
 *   ad.stop();          // 用户操作打断（barge-in）
 *   ad.onState = fn;    // 回调 "speaking"/"idle"
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

  function AvatarAdapter(opts) {
    this.opts = opts || {};
    this.avatar = null;
    this.mode = "none"; // "xmov" | "speech" | "none"
    this.onState = null;
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

  AvatarAdapter.prototype.speak = function (cmd) {
    var self = this;
    if (!cmd || !cmd.speech_text) { return; }
    this.setState("speaking");

    if (this.mode === "xmov" && this.avatar) {
      try {
        this.avatar.speak(cmd.ssml || ("<speak>" + cmd.speech_text + "</speak>"), true, true,
          { emotion: cmd.emotion_sdk || "neutral" });
        return;
      } catch (e) {
        console.warn("[avatar] speak 失败，降级朗读", e);
        this.mode = "speech";
      }
    }

    if (this.mode === "speech" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(cmd.speech_text);
      var v = pickZhVoice();
      if (v) { u.voice = v; }
      u.lang = "zh-CN";
      u.rate = 0.95;
      u.pitch = 1.0;
      u.onend = function () { self.setState("idle"); };
      window.speechSynthesis.speak(u);
      return;
    }

    // 无语音能力：按估算时长复位（与后端时序一致）
    setTimeout(function () { self.setState("idle"); },
      Math.max(1000, cmd.speech_text.length * 120));
  };

  AvatarAdapter.prototype.stop = function () {
    if (this.mode === "xmov" && this.avatar) {
      try { this.avatar.interrupt("user"); } catch (e) { /* 忽略 */ }
    }
    if (window.speechSynthesis) { window.speechSynthesis.cancel(); }
    this.setState("idle");
  };

  AvatarAdapter.prototype.setState = function (s) {
    if (this.onState) { try { this.onState(s); } catch (e) { /* 忽略 */ } }
  };

  window.AvatarAdapter = AvatarAdapter;
  window.__avatarAdapter = null;
})();
