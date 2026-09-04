"""问题3：输入过滤 —— 噪音判定 + 连续消息只响应最新。"""
from backend.app.core.input_filter import InputFilter, is_noise
from backend.app.core.memory_manager import ShortTermMemory


def test_is_noise_basic():
    assert is_noise("")
    assert is_noise("   ")
    assert is_noise("。")
    assert is_noise("。。。")
    assert is_noise("!!!")
    assert is_noise("🤣🤣🤣")
    assert is_noise("嗯")
    assert is_noise("哦哦")
    assert is_noise("哈哈哈")
    assert is_noise("啊啊啊啊")
    assert not is_noise("走一步棋")
    assert not is_noise("你好，最近怎么样")
    assert not is_noise("你下棋好厉害呀")


def test_input_filter_noise_ignored():
    f = InputFilter()
    assert f.check("。。。") == "noise"
    assert f.check("嗯") == "noise"
    # 噪音不推进状态：正常输入不受影响
    assert f.check("我们聊聊") == "ok"


def test_input_filter_dedup_consecutive():
    """连续消息只响应最新：去抖窗口内新输入覆盖旧输入（dedup）。"""
    f = InputFilter()
    assert f.check("这一步走错了吧", now=1000.0) == "ok"
    # 0.5s 后又发一条 -> 连续消息
    assert f.check("不对，应该是走那边", now=1000.5) == "dedup"
    # 同一条重复 -> 视为连续（内容不同才 dedup；相同则仍 ok 由上游去重）
    assert f.check("这一步走错了吧", now=1001.0) == "dedup"
    # 超出窗口 -> 正常
    assert f.check("我们再聊点别的", now=1010.0) == "ok"


def test_replace_last_user_coalesce():
    """连续消息只响应最新：ShortTermMemory.replace_last_user 覆盖上一条用户输入。"""
    m = ShortTermMemory()
    m.add("user", "（用户打断）第一步")
    m.add("assistant", "好的")
    m.add("user", "（用户打断）第二步")
    # 最新一条应覆盖第二步前的旧内容？——这里验证覆盖逻辑：替换最后一条 user
    m.replace_last_user("（用户打断）第三步（最新）")
    contents = [t.content for t in m.turns]
    assert "（用户打断）第三步（最新）" in contents
    assert contents.count("（用户打断）第二步") == 0
    # 无 user 记录时退化为新增
    m2 = ShortTermMemory()
    m2.replace_last_user("你好")
    assert m2.turns[-1].content == "你好"
