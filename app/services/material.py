import os
import random
import time
from typing import List
from urllib.parse import urlencode

import requests
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

from app.config import config
from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode
from app.utils import utils

requested_count = 0


def get_api_key(cfg_key: str):
    api_keys = config.app.get(cfg_key)
    if not api_keys:
        raise ValueError(
            f"\n\n##### {cfg_key} is not set #####\n\nPlease set it in the config.toml file: {config.config_file}\n\n"
            f"{utils.to_json(config.app)}"
        )

    # if only one key is provided, return it
    if isinstance(api_keys, str):
        return api_keys

    global requested_count
    requested_count += 1
    return api_keys[requested_count % len(api_keys)]


def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
    max_retries: int = 3,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_orientation = aspect.name
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    }
    # Build URL
    params = {"query": search_term, "per_page": 20, "orientation": video_orientation}
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    # 添加重试机制
    for retry in range(max_retries):
        try:
            r = requests.get(
                query_url,
                headers=headers,
                proxies=config.proxy,
                verify=False,
                timeout=(30, 60),
            )
            response = r.json()
            video_items = []
            if "videos" not in response:
                logger.error(f"search videos failed: {response}")
                if retry < max_retries - 1:
                    logger.info(f"Retrying search ({retry+1}/{max_retries})...")
                    time.sleep(2)  # 等待2秒后重试
                    continue
                return video_items

            videos = response["videos"]
            # 如果没有找到视频，尝试使用更通用的搜索词
            if not videos and retry < max_retries - 1:
                logger.warning(f"No videos found for '{search_term}', trying more generic terms...")
                # 使用更通用的搜索词
                generic_terms = ["nature", "people", "city", "abstract", "business"]
                params["query"] = random.choice(generic_terms)
                query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
                logger.info(f"Retrying with generic term: {query_url}")
                continue

            # loop through each video in the result
            for v in videos:
                duration = v["duration"]
                # check if video has desired minimum duration
                if duration < minimum_duration:
                    continue
                video_files = v["video_files"]
                # loop through each url to determine the best quality
                for video in video_files:
                    w = int(video["width"])
                    h = int(video["height"])
                    if w == video_width and h == video_height:
                        item = MaterialInfo()
                        item.provider = "pexels"
                        item.url = video["link"]
                        item.duration = duration
                        video_items.append(item)
                        break

            # 如果找到了视频，返回结果
            if video_items:
                return video_items

            # 如果没有找到合适的视频，但还有重试机会，尝试使用不同的分辨率
            if retry < max_retries - 1:
                logger.warning(f"No suitable videos found for '{search_term}', trying different resolution...")
                continue

            return video_items

        except Exception as e:
            logger.error(f"search videos failed (attempt {retry+1}/{max_retries}): {str(e)}")
            if retry < max_retries - 1:
                logger.info(f"Retrying in 2 seconds...")
                time.sleep(2)  # 等待2秒后重试
            else:
                logger.error(f"All retries failed for '{search_term}'")

    # 如果所有重试都失败，返回空列表
    return []


def search_videos_pixabay(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
    max_retries: int = 3,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    # 添加重试机制
    for retry in range(max_retries):
        try:
            api_key = get_api_key("pixabay_api_keys")
            # Build URL
            params = {
                "q": search_term,
                "video_type": "all",  # Accepted values: "all", "film", "animation"
                "per_page": 50,
                "key": api_key,
            }
            query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
            logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

            r = requests.get(
                query_url, proxies=config.proxy, verify=False, timeout=(30, 60)
            )
            response = r.json()
            video_items = []
            if "hits" not in response:
                logger.error(f"search videos failed: {response}")
                if retry < max_retries - 1:
                    logger.info(f"Retrying search ({retry+1}/{max_retries})...")
                    time.sleep(2)  # 等待2秒后重试
                    continue
                return video_items

            videos = response["hits"]

            # 如果没有找到视频，尝试使用更通用的搜索词
            if not videos and retry < max_retries - 1:
                logger.warning(f"No videos found for '{search_term}', trying more generic terms...")
                # 使用更通用的搜索词
                generic_terms = ["nature", "people", "city", "abstract", "business"]
                params["q"] = random.choice(generic_terms)
                query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
                logger.info(f"Retrying with generic term: {query_url}")
                continue

            # loop through each video in the result
            for v in videos:
                duration = v["duration"]
                # check if video has desired minimum duration
                if duration < minimum_duration:
                    continue
                video_files = v["videos"]
                # loop through each url to determine the best quality
                for video_type in video_files:
                    video = video_files[video_type]
                    w = int(video["width"])
                    # h = int(video["height"])
                    if w >= video_width:
                        item = MaterialInfo()
                        item.provider = "pixabay"
                        item.url = video["url"]
                        item.duration = duration
                        video_items.append(item)
                        break

            # 如果找到了视频，返回结果
            if video_items:
                return video_items

            # 如果没有找到合适的视频，但还有重试机会，尝试使用不同的分辨率
            if retry < max_retries - 1:
                logger.warning(f"No suitable videos found for '{search_term}', trying different resolution...")
                continue

            return video_items

        except Exception as e:
            logger.error(f"search videos failed (attempt {retry+1}/{max_retries}): {str(e)}")
            if retry < max_retries - 1:
                logger.info(f"Retrying in 2 seconds...")
                time.sleep(2)  # 等待2秒后重试
            else:
                logger.error(f"All retries failed for '{search_term}'")

    # 如果所有重试都失败，返回空列表
    return []


def save_video(video_url: str, save_dir: str = "", max_retries: int = 3) -> str:
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = video_url.split("?")[0]
    url_hash = utils.md5(url_without_query)
    video_id = f"vid-{url_hash}"
    video_path = f"{save_dir}/{video_id}.mp4"

    # if video already exists, return the path
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"video already exists: {video_path}")
        try:
            # 验证视频文件是否有效
            clip = VideoFileClip(video_path)
            duration = clip.duration
            fps = clip.fps
            clip.close()
            if duration > 0 and fps > 0:
                return video_path
            else:
                logger.warning(f"Invalid video file (duration or fps is 0): {video_path}")
                # 删除无效文件
                try:
                    os.remove(video_path)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Invalid video file: {video_path} => {str(e)}")
            # 删除无效文件
            try:
                os.remove(video_path)
            except Exception:
                pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    # 添加重试机制
    for retry in range(max_retries):
        try:
            # if video does not exist, download it
            with open(video_path, "wb") as f:
                response = requests.get(
                    video_url,
                    headers=headers,
                    proxies=config.proxy,
                    verify=False,
                    timeout=(60, 240),
                )
                if response.status_code != 200:
                    logger.error(f"Failed to download video: {video_url}, status code: {response.status_code}")
                    if retry < max_retries - 1:
                        logger.info(f"Retrying download ({retry+1}/{max_retries})...")
                        time.sleep(2)  # 等待2秒后重试
                        continue
                    return ""

                f.write(response.content)

            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                try:
                    clip = VideoFileClip(video_path)
                    duration = clip.duration
                    fps = clip.fps
                    clip.close()
                    if duration > 0 and fps > 0:
                        return video_path
                    else:
                        logger.warning(f"Invalid video file (duration or fps is 0): {video_path}")
                        # 删除无效文件
                        try:
                            os.remove(video_path)
                        except Exception:
                            pass
                        if retry < max_retries - 1:
                            logger.info(f"Retrying download ({retry+1}/{max_retries})...")
                            time.sleep(2)  # 等待2秒后重试
                            continue
                except Exception as e:
                    try:
                        os.remove(video_path)
                    except Exception:
                        pass
                    logger.warning(f"Invalid video file: {video_path} => {str(e)}")
                    if retry < max_retries - 1:
                        logger.info(f"Retrying download ({retry+1}/{max_retries})...")
                        time.sleep(2)  # 等待2秒后重试
                        continue
            else:
                logger.warning(f"Downloaded file is empty or does not exist: {video_path}")
                if retry < max_retries - 1:
                    logger.info(f"Retrying download ({retry+1}/{max_retries})...")
                    time.sleep(2)  # 等待2秒后重试
                    continue

            # 如果到达这里，说明下载失败或视频无效，但已经尝试了所有重试
            break

        except Exception as e:
            logger.error(f"Failed to download video (attempt {retry+1}/{max_retries}): {video_url} => {str(e)}")
            if retry < max_retries - 1:
                logger.info(f"Retrying in 2 seconds...")
                time.sleep(2)  # 等待2秒后重试
            else:
                logger.error(f"All retries failed for video download: {video_url}")

    # 如果所有重试都失败，返回空字符串
    return ""


def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
    max_retries: int = 3,
) -> List[str]:
    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0
    search_videos = search_videos_pexels
    if source == "pixabay":
        search_videos = search_videos_pixabay

    # 如果搜索词为空，使用默认搜索词
    if not search_terms:
        search_terms = ["nature", "people", "city", "abstract", "business"]
        logger.warning(f"No search terms provided, using default terms: {search_terms}")

    # 为每个搜索词搜索视频
    for search_term in search_terms:
        video_items = search_videos(
            search_term=search_term,
            minimum_duration=max_clip_duration,
            video_aspect=video_aspect,
            max_retries=max_retries,
        )
        logger.info(f"found {len(video_items)} videos for '{search_term}'")

        for item in video_items:
            if item.url not in valid_video_urls:
                valid_video_items.append(item)
                valid_video_urls.append(item.url)
                found_duration += item.duration

    # 如果没有找到足够的视频，尝试使用更通用的搜索词
    if found_duration < audio_duration and len(valid_video_items) < 5:
        generic_terms = ["nature", "people", "city", "abstract", "business"]
        logger.warning(f"Not enough videos found, trying generic terms: {generic_terms}")

        for search_term in generic_terms:
            if search_term in search_terms:
                continue  # 跳过已经搜索过的词

            video_items = search_videos(
                search_term=search_term,
                minimum_duration=max_clip_duration,
                video_aspect=video_aspect,
                max_retries=max_retries,
            )
            logger.info(f"found {len(video_items)} videos for generic term '{search_term}'")

            for item in video_items:
                if item.url not in valid_video_urls:
                    valid_video_items.append(item)
                    valid_video_urls.append(item.url)
                    found_duration += item.duration

            # 如果已经找到足够的视频，停止搜索
            if found_duration >= audio_duration and len(valid_video_items) >= 5:
                break

    logger.info(
        f"found total videos: {len(valid_video_items)}, required duration: {audio_duration} seconds, found duration: {found_duration} seconds"
    )

    # 如果仍然没有找到视频，返回空列表
    if not valid_video_items:
        logger.error("No videos found after all attempts")
        return []

    video_paths = []

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    if video_contact_mode.value == VideoConcatMode.random.value:
        random.shuffle(valid_video_items)

    total_duration = 0.0
    download_failures = 0
    max_failures = 10  # 最大允许的下载失败次数

    for item in valid_video_items:
        try:
            logger.info(f"downloading video: {item.url}")
            saved_video_path = save_video(
                video_url=item.url,
                save_dir=material_directory,
                max_retries=max_retries
            )
            if saved_video_path:
                logger.info(f"video saved: {saved_video_path}")
                video_paths.append(saved_video_path)
                seconds = min(max_clip_duration, item.duration)
                total_duration += seconds
                if total_duration > audio_duration:
                    logger.info(
                        f"total duration of downloaded videos: {total_duration} seconds, skip downloading more"
                    )
                    break
            else:
                download_failures += 1
                logger.warning(f"Failed to download video: {item.url}, failures: {download_failures}/{max_failures}")
                if download_failures >= max_failures:
                    logger.error(f"Too many download failures ({download_failures}), stopping download")
                    break
        except Exception as e:
            download_failures += 1
            logger.error(f"failed to download video: {utils.to_json(item)} => {str(e)}")
            if download_failures >= max_failures:
                logger.error(f"Too many download failures ({download_failures}), stopping download")
                break

    # 如果没有下载到任何视频，记录错误
    if not video_paths:
        logger.error("No videos were successfully downloaded")
    else:
        logger.success(f"downloaded {len(video_paths)} videos with total duration of {total_duration} seconds")

    return video_paths


if __name__ == "__main__":
    download_videos(
        "test123", ["Money Exchange Medium"], audio_duration=100, source="pixabay"
    )
