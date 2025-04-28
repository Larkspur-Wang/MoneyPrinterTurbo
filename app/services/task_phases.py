"""
任务阶段处理模块，将任务拆分为多个阶段，便于资源管理和并行处理
"""
import math
import os
import os.path
import time
from os import path

from loguru import logger

from app.config import config
from app.controllers.manager.advanced_manager import TaskPhase
from app.models import const
from app.models.schema import VideoConcatMode, VideoParams
from app.services import llm, material, subtitle, video, voice
from app.services import state as sm
from app.utils import utils

# 不直接导入moviepy，而是在需要时动态导入
# 这样可以避免IDE报错，同时保持功能正常
VideoFileClip = None  # 全局变量，用于标记是否可用

def get_video_file_clip():
    """动态导入VideoFileClip"""
    global VideoFileClip
    if VideoFileClip is None:
        try:
            from moviepy.editor import VideoFileClip as VFC
            VideoFileClip = VFC
        except ImportError:
            logger.warning("MoviePy not available, video validation will be limited")
            VideoFileClip = False
    return VideoFileClip


def phase_script(task_id, params):
    """生成脚本阶段"""
    logger.info("\n\n## generating video script")
    video_script = params.video_script.strip()
    if not video_script:
        video_script = llm.generate_script(
            video_subject=params.video_subject,
            language=params.video_language,
            paragraph_number=params.paragraph_number,
        )
    else:
        logger.debug(f"video script: \n{video_script}")

    if not video_script:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error("failed to generate video script.")
        return None

    return video_script


def phase_terms(task_id, params, video_script):
    """生成关键词阶段"""
    logger.info("\n\n## generating video terms")
    video_terms = params.video_terms
    if not video_terms:
        video_terms = llm.generate_terms(
            video_subject=params.video_subject, video_script=video_script, amount=5
        )
    else:
        import re
        if isinstance(video_terms, str):
            video_terms = [term.strip() for term in re.split(r"[,，]", video_terms)]
        elif isinstance(video_terms, list):
            video_terms = [term.strip() for term in video_terms]
        else:
            raise ValueError("video_terms must be a string or a list of strings.")

        logger.debug(f"video terms: {utils.to_json(video_terms)}")

    if not video_terms:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error("failed to generate video terms.")
        return None

    return video_terms


def phase_save_script(task_id, video_script, video_terms, params):
    """保存脚本数据阶段"""
    script_file = path.join(utils.task_dir(task_id), "script.json")
    script_data = {
        "script": video_script,
        "search_terms": video_terms,
        "params": params,
    }

    with open(script_file, "w", encoding="utf-8") as f:
        f.write(utils.to_json(script_data))


def phase_audio(task_id, params, video_script):
    """生成音频阶段"""
    logger.info("\n\n## generating audio")
    audio_file = path.join(utils.task_dir(task_id), "audio.mp3")
    sub_maker = voice.tts(
        text=video_script,
        voice_name=voice.parse_voice_name(params.voice_name),
        voice_rate=params.voice_rate,
        voice_file=audio_file,
    )
    if sub_maker is None:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error(
            """failed to generate audio:
1. check if the language of the voice matches the language of the video script.
2. check if the network is available. If you are in China, it is recommended to use a VPN and enable the global traffic mode.
        """.strip()
        )
        return None, None, None

    audio_duration = math.ceil(voice.get_audio_duration(sub_maker))
    return audio_file, audio_duration, sub_maker


def phase_subtitle(task_id, params, video_script, sub_maker, audio_file):
    """生成字幕阶段"""
    if not params.subtitle_enabled:
        return ""

    subtitle_path = path.join(utils.task_dir(task_id), "subtitle.srt")
    subtitle_provider = config.app.get("subtitle_provider", "").strip().lower()
    logger.info(f"\n\n## generating subtitle, provider: {subtitle_provider}")

    subtitle_fallback = False
    if subtitle_provider == "edge":
        voice.create_subtitle(
            text=video_script, sub_maker=sub_maker, subtitle_file=subtitle_path
        )
        if not os.path.exists(subtitle_path):
            subtitle_fallback = True
            logger.warning("subtitle file not found, fallback to whisper")

    if subtitle_provider == "whisper" or subtitle_fallback:
        subtitle.create(audio_file=audio_file, subtitle_file=subtitle_path)
        logger.info("\n\n## correcting subtitle")
        subtitle.correct(subtitle_file=subtitle_path, video_script=video_script)

    subtitle_lines = subtitle.file_to_subtitles(subtitle_path)
    if not subtitle_lines:
        logger.warning(f"subtitle file is invalid: {subtitle_path}")
        return ""

    return subtitle_path


def phase_download(task_id, params, video_terms, audio_duration):
    """下载视频阶段"""
    try:
        if params.video_source == "local":
            logger.info("\n\n## preprocess local materials")
            materials = video.preprocess_video(
                materials=params.video_materials, clip_duration=params.video_clip_duration
            )
            if not materials:
                sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
                logger.error(
                    "no valid materials found, please check the materials and try again."
                )
                return None
            return [material_info.url for material_info in materials]
        else:
            logger.info(f"\n\n## downloading videos from {params.video_source}")

            # 设置下载重试次数
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    downloaded_videos = material.download_videos(
                        task_id=task_id,
                        search_terms=video_terms,
                        source=params.video_source,
                        video_aspect=params.video_aspect,
                        video_contact_mode=params.video_concat_mode,
                        audio_duration=audio_duration * params.video_count,
                        max_clip_duration=params.video_clip_duration,
                    )

                    if not downloaded_videos:
                        retry_count += 1
                        logger.warning(f"Download attempt {retry_count} failed, retrying...")
                        # 短暂休眠后重试
                        import time
                        time.sleep(2)
                        continue

                    # 验证下载的视频文件
                    valid_videos = []
                    for video_path in downloaded_videos:
                        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                            valid_videos.append(video_path)
                        else:
                            logger.warning(f"Invalid video file: {video_path}")

                    if not valid_videos:
                        retry_count += 1
                        logger.warning(f"No valid videos found in attempt {retry_count}, retrying...")
                        continue

                    return valid_videos

                except Exception as e:
                    retry_count += 1
                    logger.error(f"Download error in attempt {retry_count}: {str(e)}")
                    if retry_count >= max_retries:
                        break
                    # 短暂休眠后重试
                    import time
                    time.sleep(2)

            # 如果所有重试都失败
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error(
                "failed to download videos after multiple attempts, maybe the network is not available. if you are in China, please use a VPN."
            )
            return None
    except Exception as e:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error(f"Error in download phase: {str(e)}")
        return None


def phase_render(task_id, params, downloaded_videos, audio_file, subtitle_path):
    """渲染视频阶段"""
    try:
        # 强制进行垃圾回收
        import gc
        gc.collect()

        final_video_paths = []
        combined_video_paths = []
        video_concat_mode = (
            params.video_concat_mode if params.video_count == 1 else VideoConcatMode.random
        )
        video_transition_mode = params.video_transition_mode

        # 减少视频数量，如果内存不足
        video_count = min(params.video_count, 2)  # 最多生成2个视频，减少内存压力

        _progress = 50
        for i in range(video_count):
            # 每次循环前进行垃圾回收
            gc.collect()

            index = i + 1
            combined_video_path = path.join(
                utils.task_dir(task_id), f"combined-{index}.mp4"
            )
            logger.info(f"\n\n## combining video: {index} => {combined_video_path}")

            # 设置重试机制
            max_retries = 2
            for retry in range(max_retries):
                try:
                    # 验证视频文件
                    valid_videos = []
                    for video_path in downloaded_videos:
                        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                            try:
                                # 尝试验证视频文件完整性
                                video_clip = get_video_file_clip()
                                if video_clip and video_clip is not False:
                                    try:
                                        clip = video_clip(video_path)
                                        clip.close()
                                    except Exception as clip_error:
                                        logger.warning(f"Error validating video: {str(clip_error)}")
                                valid_videos.append(video_path)
                            except Exception as e:
                                logger.warning(f"Invalid video file {video_path}: {str(e)}")

                    if not valid_videos:
                        raise ValueError("No valid video files found")

                    # 使用验证过的视频文件
                    video.combine_videos(
                        combined_video_path=combined_video_path,
                        video_paths=valid_videos,
                        audio_file=audio_file,
                        video_aspect=params.video_aspect,
                        video_concat_mode=video_concat_mode,
                        video_transition_mode=video_transition_mode,
                        max_clip_duration=params.video_clip_duration,
                        threads=params.n_threads,
                    )
                    break  # 成功则跳出重试循环
                except Exception as e:
                    logger.error(f"Error combining videos (attempt {retry+1}): {str(e)}")
                    if retry == max_retries - 1:  # 最后一次重试失败
                        raise  # 重新抛出异常
                    # 短暂休眠后重试
                    import time
                    time.sleep(2)
                    # 强制垃圾回收
                    gc.collect()

            _progress += 50 / video_count / 2
            sm.state.update_task(task_id, progress=_progress)

            final_video_path = path.join(utils.task_dir(task_id), f"final-{index}.mp4")

            logger.info(f"\n\n## generating video: {index} => {final_video_path}")

            # 设置重试机制
            for retry in range(max_retries):
                try:
                    video.generate_video(
                        video_path=combined_video_path,
                        audio_path=audio_file,
                        subtitle_path=subtitle_path,
                        output_file=final_video_path,
                        params=params,
                    )
                    break  # 成功则跳出重试循环
                except Exception as e:
                    logger.error(f"Error generating video (attempt {retry+1}): {str(e)}")
                    if retry == max_retries - 1:  # 最后一次重试失败
                        raise  # 重新抛出异常
                    # 短暂休眠后重试
                    import time
                    time.sleep(2)
                    # 强制垃圾回收
                    gc.collect()

            _progress += 50 / video_count / 2
            sm.state.update_task(task_id, progress=_progress)

            final_video_paths.append(final_video_path)
            combined_video_paths.append(combined_video_path)

            # 每个视频完成后进行垃圾回收
            gc.collect()

        return final_video_paths, combined_video_paths
    except Exception as e:
        logger.error(f"Error in render phase: {str(e)}")
        # 强制垃圾回收
        import gc
        gc.collect()
        return None, None


def start_phased(task_id, params: VideoParams, task_manager=None, stop_at: str = "video"):
    """分阶段启动任务"""
    # 强制进行垃圾回收
    import gc
    gc.collect()

    logger.info(f"start phased task: {task_id}, stop_at: {stop_at}")
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=5)

    if type(params.video_concat_mode) is str:
        params.video_concat_mode = VideoConcatMode(params.video_concat_mode)

    # 限制视频数量，防止内存溢出
    if params.video_count > 2:
        logger.warning(f"Limiting video count from {params.video_count} to 2 to prevent memory issues")
        params.video_count = 2

    # 更新任务阶段
    if task_manager:
        task_manager.update_task_phase(task_id, TaskPhase.SCRIPT)

    # 1. 生成脚本
    video_script = phase_script(task_id, params)
    if not video_script or "Error: " in video_script:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        if task_manager:
            task_manager.update_task_phase(task_id, TaskPhase.FAILED)
        return

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=10)

    if stop_at == "script":
        sm.state.update_task(
            task_id, state=const.TASK_STATE_COMPLETE, progress=100, script=video_script
        )
        if task_manager:
            task_manager.update_task_phase(task_id, TaskPhase.COMPLETE)
        return {"script": video_script}

    # 更新任务阶段
    if task_manager:
        task_manager.update_task_phase(task_id, TaskPhase.TERMS)

    # 2. 生成关键词
    video_terms = ""
    if params.video_source != "local":
        video_terms = phase_terms(task_id, params, video_script)
        if not video_terms:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            if task_manager:
                task_manager.update_task_phase(task_id, TaskPhase.FAILED)
            return

    # 保存脚本数据
    phase_save_script(task_id, video_script, video_terms, params)

    if stop_at == "terms":
        sm.state.update_task(
            task_id, state=const.TASK_STATE_COMPLETE, progress=100, terms=video_terms
        )
        if task_manager:
            task_manager.update_task_phase(task_id, TaskPhase.COMPLETE)
        return {"script": video_script, "terms": video_terms}

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=20)

    # 更新任务阶段
    if task_manager:
        task_manager.update_task_phase(task_id, TaskPhase.AUDIO)

    # 3. 生成音频
    audio_file, audio_duration, sub_maker = phase_audio(task_id, params, video_script)
    if not audio_file:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        if task_manager:
            task_manager.update_task_phase(task_id, TaskPhase.FAILED)
        return

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=30)

    if stop_at == "audio":
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            audio_file=audio_file,
        )
        if task_manager:
            task_manager.update_task_phase(task_id, TaskPhase.COMPLETE)
        return {"audio_file": audio_file, "audio_duration": audio_duration}

    # 更新任务阶段
    if task_manager:
        task_manager.update_task_phase(task_id, TaskPhase.SUBTITLE)

    # 4. 生成字幕
    subtitle_path = phase_subtitle(task_id, params, video_script, sub_maker, audio_file)

    if stop_at == "subtitle":
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            subtitle_path=subtitle_path,
        )
        if task_manager:
            task_manager.update_task_phase(task_id, TaskPhase.COMPLETE)
        return {"subtitle_path": subtitle_path}

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=40)

    # 更新任务阶段
    if task_manager:
        task_manager.update_task_phase(task_id, TaskPhase.DOWNLOAD)

    # 5. 获取视频素材
    downloaded_videos = phase_download(task_id, params, video_terms, audio_duration)
    if not downloaded_videos:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        if task_manager:
            task_manager.update_task_phase(task_id, TaskPhase.FAILED)
        return

    if stop_at == "materials":
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            materials=downloaded_videos,
        )
        if task_manager:
            task_manager.update_task_phase(task_id, TaskPhase.COMPLETE)
        return {"materials": downloaded_videos}

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=50)

    # 更新任务阶段
    if task_manager:
        task_manager.update_task_phase(task_id, TaskPhase.RENDER)

    # 6. 生成最终视频
    final_video_paths, combined_video_paths = phase_render(
        task_id, params, downloaded_videos, audio_file, subtitle_path
    )

    if not final_video_paths:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        if task_manager:
            task_manager.update_task_phase(task_id, TaskPhase.FAILED)
        return

    logger.success(f"task {task_id} finished, generated {len(final_video_paths)} videos.")

    kwargs = {
        "videos": final_video_paths,
        "combined_videos": combined_video_paths,
        "script": video_script,
        "terms": video_terms,
        "audio_file": audio_file,
        "audio_duration": audio_duration,
        "subtitle_path": subtitle_path,
        "materials": downloaded_videos,
    }
    sm.state.update_task(task_id, state=const.TASK_STATE_COMPLETE, progress=100, **kwargs)

    # 更新任务阶段
    if task_manager:
        task_manager.update_task_phase(task_id, TaskPhase.COMPLETE)

    return kwargs
