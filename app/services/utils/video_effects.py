from moviepy import Clip, vfx


# FadeIn
def fadein_transition(clip: Clip, t: float) -> Clip:
    return clip.with_effects([vfx.FadeIn(t)])


# FadeOut
def fadeout_transition(clip: Clip, t: float) -> Clip:
    return clip.with_effects([vfx.FadeOut(t)])


# SlideIn
def slidein_transition(clip: Clip, t: float, side: str) -> Clip:
    return clip.with_effects([vfx.SlideIn(t, side)])


# SlideOut
def slideout_transition(clip: Clip, t: float, side: str) -> Clip:
    return clip.with_effects([vfx.SlideOut(t, side)])


# CrossFadeIn
def crossfadein_transition(clip: Clip, t: float) -> Clip:
    return clip.with_effects([vfx.CrossFadeIn(t)])


# CrossFadeOut
def crossfadeout_transition(clip: Clip, t: float) -> Clip:
    return clip.with_effects([vfx.CrossFadeOut(t)])


# Rotate
def rotate_transition(clip: Clip, t: float) -> Clip:
    # 创建一个旋转效果，旋转90度
    # t参数在这里不使用，但保留以保持接口一致
    return clip.with_effects([vfx.Rotate(90, unit='deg')])


# Blink
def blink_transition(clip: Clip, t: float) -> Clip:
    return clip.with_effects([vfx.Blink(t, t)])


# MirrorX (水平翻转)
def mirrorx_transition(clip: Clip, t: float) -> Clip:
    # t参数在这里不使用，但保留以保持接口一致
    return clip.with_effects([vfx.MirrorX()])


# MirrorY (垂直翻转)
def mirrory_transition(clip: Clip, t: float) -> Clip:
    # t参数在这里不使用，但保留以保持接口一致
    return clip.with_effects([vfx.MirrorY()])


# ZoomIn
def zoomin_transition(clip: Clip, t: float) -> Clip:
    # t参数在这里不直接使用，但保留以保持接口一致
    # 创建一个简单的缩放效果，从0.7倍大小缩放到1.0倍大小
    return clip.with_effects([vfx.Resize(0.7)])


# ZoomOut
def zoomout_transition(clip: Clip, t: float) -> Clip:
    # t参数在这里不直接使用，但保留以保持接口一致
    # 创建一个简单的缩放效果，从1.3倍大小缩放到1.0倍大小
    return clip.with_effects([vfx.Resize(1.3)])
