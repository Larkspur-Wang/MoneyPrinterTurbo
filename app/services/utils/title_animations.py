import random
import numpy as np
from moviepy import ImageClip, CompositeVideoClip, ColorClip, VideoClip
from loguru import logger


def apply_animation(
    clip: ImageClip,
    animation_type: str,
    duration: float,
    speed: float = 1.0
) -> ImageClip:
    """
    为标题贴纸应用动画效果

    :param clip: 原始图像剪辑
    :param animation_type: 动画类型
    :param duration: 视频持续时间
    :param speed: 动画速度
    :return: 应用了动画效果的剪辑
    """
    # 调整速度因子
    speed_factor = speed

    # 如果是随机动画，随机选择一种动画效果
    if animation_type == "random":
        animation_types = ["bounce", "pulse", "whole_bounce", "light_sweep", "fade", "blink", "wave"]
        animation_type = random.choice(animation_types)
        logger.info(f"Randomly selected animation: {animation_type}")

    # 根据动画类型应用不同的效果
    if animation_type == "bounce":
        return bounce_animation(clip, speed_factor)
    elif animation_type == "pulse":
        return pulse_animation(clip, speed_factor)
    elif animation_type == "whole_bounce":
        return whole_bounce_animation(clip, speed_factor)
    elif animation_type == "light_sweep":
        return light_sweep_animation(clip, duration, speed_factor)
    elif animation_type == "fade":
        return fade_animation(clip, speed_factor)
    elif animation_type == "blink":
        return blink_animation(clip, duration, speed_factor)
    elif animation_type == "wave":
        return wave_animation(clip, speed_factor)
    elif animation_type == "rotate":
        return pulse_animation(clip, speed_factor)  # 用pulse代替rotate
    else:
        # 如果没有指定动画或不支持的动画类型，返回原始剪辑
        return clip


def pulse_animation(clip: ImageClip, speed: float = 1.0) -> ImageClip:
    """
    整体放大缩小的动画效果

    :param clip: 原始图像剪辑
    :param speed: 动画速度
    :return: 应用了动画效果的剪辑
    """
    # 确保剪辑有持续时间
    if not hasattr(clip, 'duration') or clip.duration is None:
        logger.warning("Clip has no duration, using default duration of 5 seconds")
        clip = clip.with_duration(5)

    # 应用整体缩放效果
    return clip.resized(lambda t: 1 + 0.1 * np.sin(speed * 2 * np.pi * t))


def whole_bounce_animation(clip: ImageClip, speed: float = 1.0) -> ImageClip:
    """
    整体上下跳动的动画效果

    :param clip: 原始图像剪辑
    :param speed: 动画速度
    :return: 应用了动画效果的剪辑
    """
    # 确保剪辑有持续时间
    if not hasattr(clip, 'duration') or clip.duration is None:
        logger.warning("Clip has no duration, using default duration of 5 seconds")
        clip = clip.with_duration(5)

    # 获取原始位置
    original_position = clip.pos

    # 定义新的位置函数
    def get_position(t):
        # 获取原始位置
        orig_pos = original_position(t)

        # 如果原始位置的y坐标是字符串（如"center"）
        if isinstance(orig_pos[1], str):
            # 保持原始位置不变
            return orig_pos
        else:
            # 如果是数值，则添加上下移动效果
            return (orig_pos[0], orig_pos[1] + 10 * np.sin(speed * 2 * np.pi * t))

    # 应用上下移动效果
    return clip.with_position(get_position)


def light_sweep_animation(clip: ImageClip, duration: float, speed: float = 1.0) -> ImageClip:
    """
    光照扫过效果

    :param clip: 原始图像剪辑
    :param duration: 视频持续时间
    :param speed: 动画速度
    :return: 应用了动画效果的剪辑
    """
    # 获取剪辑的原始尺寸
    w, h = clip.size

    # 创建一个光照效果剪辑
    def make_light_mask(t):
        # 计算光照位置
        pos = (w + 100) * ((t * speed) % 1) - 50

        # 创建一个渐变遮罩
        mask = np.zeros((h, w, 4), dtype=np.uint8)

        # 光照宽度
        light_width = 100

        # 创建光照效果
        for x in range(max(0, int(pos - light_width)), min(w, int(pos + light_width))):
            if 0 <= x < w:
                # 计算光照强度
                intensity = 1 - abs(x - pos) / light_width
                # 设置遮罩透明度
                mask[:, x, 3] = np.uint8(255 * intensity)

        return mask

    # 创建光照遮罩剪辑
    light_mask = VideoClip(make_light_mask, duration=duration)

    # 创建一个白色光照剪辑
    light_clip = ColorClip(size=clip.size, color=(255, 255, 255))
    light_clip = light_clip.with_mask(light_mask)
    light_clip = light_clip.with_duration(duration)

    # 合成原始剪辑和光照剪辑
    # 由于 ColorClip 没有 with_blend 方法，我们直接使用 CompositeVideoClip
    composite_clip = CompositeVideoClip([clip, light_clip])
    composite_clip = composite_clip.with_duration(duration)
    return composite_clip


def fade_animation(clip: ImageClip, speed: float = 1.0) -> ImageClip:
    """
    淡入淡出效果（自定义实现）

    :param clip: 原始图像剪辑
    :param speed: 动画速度
    :return: 应用了动画效果的剪辑
    """
    # 确保剪辑有持续时间
    if not hasattr(clip, 'duration') or clip.duration is None:
        logger.warning("Clip has no duration, using default duration of 5 seconds")
        clip = clip.with_duration(5)

    # 创建一个函数，根据时间返回不透明度
    def make_frame_opacity(t):
        # 计算总时长
        total_duration = clip.duration
        # 计算淡入淡出时间
        fade_time = min(0.5, total_duration / 4)

        # 淡入阶段
        if t < fade_time:
            return t / fade_time
        # 淡出阶段
        elif t > total_duration - fade_time:
            return (total_duration - t) / fade_time
        # 中间阶段
        else:
            return 1.0

    # 创建一个函数，根据时间和不透明度修改帧
    def make_frame(t):
        frame = clip.get_frame(t)
        opacity = make_frame_opacity(t)

        # 修改alpha通道（如果有的话）
        if frame.shape[2] == 4:  # RGBA
            frame[:, :, 3] = frame[:, :, 3] * opacity
        else:  # RGB
            # 如果没有alpha通道，则调整整体亮度
            frame = frame * opacity

        return frame

    # 创建新的剪辑
    new_clip = VideoClip(make_frame, duration=clip.duration)

    # 保持原始位置
    new_clip = new_clip.with_position(clip.pos)

    return new_clip


def wave_animation(clip: ImageClip, speed: float = 1.0) -> ImageClip:
    """
    波浪效果

    :param clip: 原始图像剪辑
    :param speed: 动画速度
    :return: 应用了动画效果的剪辑
    """
    # 确保剪辑有持续时间
    if not hasattr(clip, 'duration') or clip.duration is None:
        logger.warning("Clip has no duration, using default duration of 5 seconds")
        clip = clip.with_duration(5)

    # 获取原始位置
    original_position = clip.pos

    # 定义新的位置函数
    def get_position(t):
        # 获取原始位置
        orig_pos = original_position(t)

        # 如果原始位置的y坐标是字符串（如"center"）
        if isinstance(orig_pos[1], str):
            # 保持原始位置不变
            return orig_pos
        else:
            # 如果是数值，则添加上下移动效果
            # 使用更平缓的波浪效果
            return (orig_pos[0], orig_pos[1] + 8 * np.sin(speed * 1.5 * np.pi * t))

    # 应用上下移动效果
    return clip.with_position(get_position)


def bounce_animation(clip: ImageClip, speed: float = 1.0) -> ImageClip:
    """
    每个字符单独跳动的动画效果，实现逐一跳动并循环的效果

    :param clip: 原始图像剪辑
    :param speed: 动画速度
    :return: 应用了动画效果的剪辑
    """
    # 确保剪辑有持续时间
    if not hasattr(clip, 'duration') or clip.duration is None:
        logger.warning("Clip has no duration, using default duration of 5 seconds")
        clip = clip.with_duration(5)

    # 获取原始位置
    original_position = clip.pos

    # 获取剪辑的原始尺寸
    w, h = clip.size

    # 估计字符数量（根据图像宽度和平均字符宽度）
    # 假设每个字符平均宽度约为图像高度的0.8倍（对于中文字符）
    avg_char_width = int(h * 0.8)
    estimated_chars = max(3, w // avg_char_width)  # 至少3个字符，避免估计不足

    # 创建一个函数，根据时间返回位置
    def get_position(t):
        # 获取原始位置
        orig_pos = original_position(t) if callable(original_position) else original_position

        # 如果原始位置不是元组或者y坐标是字符串（如"center"）
        if not isinstance(orig_pos, tuple) or isinstance(orig_pos[1], str):
            # 保持原始位置不变
            return orig_pos

        # 解包原始位置
        x, y = orig_pos

        # 计算当前活跃的字符索引（0到estimated_chars-1）
        active_char_index = int((t * speed * 2) % estimated_chars)

        # 计算跳动阶段（0到1）
        bounce_phase = (t * speed * 2) % 1.0

        # 计算跳动高度
        bounce_height = 0

        # 使用正弦函数创建更自然的跳动效果
        if bounce_phase < 0.5:
            bounce_height = -15 * np.sin(bounce_phase * 2 * np.pi)  # 负值表示向上移动

        # 返回修改后的位置
        return (x, y + bounce_height)

    # 应用位置函数
    bouncing_clip = clip.with_position(get_position)

    # 返回修改后的剪辑
    return bouncing_clip


def blink_animation(clip: ImageClip, duration: float, speed: float = 1.0) -> ImageClip:
    """
    闪烁效果（使用自定义实现）

    :param clip: 原始图像剪辑
    :param duration: 视频持续时间
    :param speed: 动画速度
    :return: 应用了动画效果的剪辑
    """
    # 创建一个函数，根据时间返回透明度
    def make_frame_opacity(t):
        # 使用正弦函数创建闪烁效果
        opacity = (np.sin(speed * 2 * np.pi * t) + 1) / 2  # 范围从0到1
        return opacity

    # 创建一个函数，根据时间和透明度修改帧
    def make_frame(t):
        frame = clip.get_frame(t)
        opacity = make_frame_opacity(t)
        # 修改alpha通道（如果有的话）
        if frame.shape[2] == 4:  # RGBA
            frame[:, :, 3] = frame[:, :, 3] * opacity
        return frame

    # 创建新的剪辑
    new_clip = VideoClip(make_frame, duration=duration)
    new_clip = new_clip.with_duration(clip.duration)

    # 保持原始位置
    new_clip = new_clip.with_position(clip.pos)

    return new_clip
