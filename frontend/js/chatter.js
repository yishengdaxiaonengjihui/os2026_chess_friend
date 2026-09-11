// chatter.js —— 棋友口语库（步骤3：台词去机械化）
// 前端静态口语库：按人格 + 场景 + 加权随机，让数字人像真人一样有口癖、
// 会嘟囔、会搭话。LLM 长台词仍由后端生成，这里提供即时的"人性化补丁"：
//   - thinking：AI 思考停顿期的嘟囔（不依赖网络，即时可播）
//   - thinkLong：用户长考提醒（N 秒没落子，AI 主动搭话）
//   - cheer：落子后按局面（吃子/将军/优势/劣势）补一句口头禅
"use strict";

(function (global) {
  const LIB = {
    laozhang: {
      // 思考嘟囔（AI 落子前的碎碎念）
      thinking: [
        "嗯…这一步，得琢磨琢磨。",
        "嘿，有点意思啊。",
        "让我瞅瞅，怎么走才够劲儿。",
        "这盘棋，可不好应付啊。",
        "得嘞，我想想……",
        "有门道，我得仔细点。",
      ],
      // 用户长考提醒（用户思考太久；整局最多触发 2 次）—— 简短语气词即可
      thinkLong: [
        "嗯，慢慢来。",
        "好，不急，慢慢想。",
        "看看，想好了再走。",
        "嗯，慢慢琢磨。",
      ],
      // 落子后口头禅（可拼在 LLM 台词前）
      cheer: [
        "嘿，", "得嘞，", "哟，", "不错不错，", "哈，",
      ],
      // 吃子后
      capture: [
        "这子我可就不客气了。",
        "哟，又吃一个。",
        "好子好子，我收下了。",
      ],
      // 被吃子
      captured: [
        "哟，这步棋走得不错。",
        "嘿，让咱占个便宜。",
        "没事，咱慢慢来。",
      ],
      // 将军
      check: [
        "将军！接招吧。",
        "嘿嘿，将一军。",
        "这一手，可得当心了。",
      ],
      // 优势
      ahead: [
        "这局，我胜算不小啊。",
        "看这形势，我得势了。",
        "嘿嘿，今天运气在我这边。",
      ],
      // 劣势
      behind: [
        "这一步，走得挺扎实。",
        "我得打起精神来了。",
        "这局面，我得小心应付。",
      ],
    },
    xiaoya: {
      thinking: [
        "嗯…我看看这步棋。",
        "让我好好想想呢。",
        "这一步，要仔细一点。",
        "嗯嗯，我想想怎么下。",
        "有意思，我来琢磨琢磨。",
      ],
      thinkLong: [
        "嗯，慢慢来。",
        "好，不急，慢慢想。",
        "看看，想好了再走。",
        "嗯，慢慢琢磨。",
      ],
      cheer: [
        "好呀，", "嗯嗯，", "真不错，", "哇，", "这样啊，",
      ],
      capture: [
        "这子我收下啦。",
        "嘿嘿，我吃一个。",
        "好棋，这子归我了。",
      ],
      captured: [
        "哇，这步真厉害。",
        "嗯嗯，这步走得很好。",
        "没关系，我们继续。",
      ],
      check: [
        "将军啦，小心哦。",
        "嘿嘿，将一军。",
        "这一手要当心哦。",
      ],
      ahead: [
        "这局我好像有点优势呢。",
        "看这形势，我占点先机。",
        "嗯嗯，这步我挺满意的。",
      ],
      behind: [
        "这步很扎实呢。",
        "我要更认真一点了。",
        "这局面有点难，我好好想想。",
      ],
    },
  };

  function pick(list) {
    if (!list || !list.length) return "";
    return list[Math.floor(Math.random() * list.length)];
  }

  function libFor(personality) {
    return LIB[personality] || LIB.laozhang;
  }

  const Chatter = {
    // 思考嘟囔（AI 落子停顿期）
    thinking(personality) {
      return pick(libFor(personality).thinking);
    },
    // 用户长考提醒
    thinkLong(personality) {
      return pick(libFor(personality).thinkLong);
    },
    // 落子后按局面补口头禅/短句（返回 {prefix, line}）
    afterMove(personality, resp) {
      const lib = libFor(personality);
      const ev = (resp && resp.events ? resp.events : []).join(" ");
      let line = "";
      if (/吃子/.test(ev)) line = pick(lib.capture);
      else if (/将死|将军/.test(ev)) line = pick(lib.check);
      // 胜率辅助判断优劣势（win_probability 为 AI 胜率）
      if (!line && resp && resp.ai_move && typeof resp.ai_move.win_probability === "number") {
        const aiWin = resp.ai_move.win_probability;
        if (aiWin >= 0.6) line = pick(lib.ahead);
        else if (aiWin <= 0.35) line = pick(lib.behind);
      }
      if (!line && resp && resp.ai_move && resp.ai_move.captured) line = pick(lib.capture);
      if (!line && (resp && resp.ai_move && resp.ai_move.from_sq)) line = pick(lib.cheer);
      // 没有合适短句时退回口头禅前缀（拼在 LLM 台词前）
      if (!line) return { prefix: "", line: "" };
      return { prefix: "", line };
    },
    // 是否有该人格数据
    has(personality) {
      return !!LIB[personality];
    },
  };

  global.Chatter = Chatter;
})(window);
