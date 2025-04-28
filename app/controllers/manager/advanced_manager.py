import threading
import time
from enum import Enum
from queue import PriorityQueue
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

from app.controllers.manager.base_manager import TaskManager


class TaskPhase(Enum):
    """任务阶段枚举，用于标识任务当前处于哪个阶段"""
    INIT = 0
    SCRIPT = 1  # 生成脚本阶段
    TERMS = 2   # 生成关键词阶段
    AUDIO = 3   # 生成音频阶段
    SUBTITLE = 4  # 生成字幕阶段
    DOWNLOAD = 5  # 下载视频阶段
    RENDER = 6   # 渲染视频阶段
    COMPLETE = 7  # 完成阶段
    FAILED = 8   # 失败阶段


class TaskInfo:
    """任务信息类，包含任务的详细信息"""
    def __init__(self, task_id: str, func: Callable, args: Tuple, kwargs: Dict, priority: int = 0):
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.priority = priority
        self.phase = TaskPhase.INIT
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.progress = 0
        self.is_running = False
        self.is_complete = False
        self.is_failed = False
        self.result = None
        self.error = None

    def __lt__(self, other):
        # 优先级队列比较方法，优先级高的先执行
        if not isinstance(other, TaskInfo):
            return NotImplemented
        return self.priority < other.priority


class AdvancedTaskManager(TaskManager):
    """高级任务管理器，支持更智能的资源分配"""
    def __init__(self, max_concurrent_tasks: int, max_download_tasks: int = 2, max_render_tasks: int = 2):
        super().__init__(max_concurrent_tasks)
        self.max_download_tasks = max_download_tasks  # 最大下载任务数
        self.max_render_tasks = max_render_tasks  # 最大渲染任务数
        self.current_download_tasks = 0  # 当前下载任务数
        self.current_render_tasks = 0  # 当前渲染任务数
        self.task_info_map = {}  # 任务ID到任务信息的映射
        self.phase_hooks = {}  # 阶段钩子，用于在任务进入某个阶段时执行特定操作
        self.task_phase_lock = threading.Lock()  # 任务阶段锁

    def create_queue(self):
        return PriorityQueue()

    def add_task(self, func: Callable, *args: Any, **kwargs: Any):
        task_id = kwargs.get("task_id", "")
        priority = kwargs.get("priority", 0)

        # 创建任务信息
        task_info = TaskInfo(task_id, func, args, kwargs, priority)

        with self.lock:
            # 保存任务信息
            self.task_info_map[task_id] = task_info

            # 检查是否可以立即执行任务
            if self.current_tasks < self.max_concurrent_tasks:
                logger.info(f"Adding task: {func.__name__}, task_id: {task_id}, current_tasks: {self.current_tasks}")
                self.current_tasks += 1  # 立即增加计数，防止竞态条件
                self.execute_task(func, *args, **kwargs)
                task_info.is_running = True
            else:
                logger.info(f"Enqueueing task: {func.__name__}, task_id: {task_id}, current_tasks: {self.current_tasks}")
                self.enqueue(task_info)

    def execute_task(self, func: Callable, *args: Any, **kwargs: Any):
        thread = threading.Thread(
            target=self.run_task, args=(func, *args), kwargs=kwargs
        )
        thread.daemon = True  # 设置为守护线程，这样主程序退出时，线程也会退出
        thread.start()

    def run_task(self, func: Callable, *args: Any, **kwargs: Any):
        task_id = kwargs.get("task_id", "")
        try:
            # 在执行任务前进行垃圾回收
            import gc
            gc.collect()

            # 执行任务
            result = func(*args, **kwargs)

            # 更新任务信息
            with self.task_phase_lock:
                if task_id in self.task_info_map:
                    task_info = self.task_info_map[task_id]
                    task_info.is_complete = True
                    task_info.is_running = False
                    task_info.result = result
                    task_info.phase = TaskPhase.COMPLETE
        except MemoryError as me:
            # 内存错误特殊处理
            logger.error(f"Task {task_id} failed due to memory error: {str(me)}")
            # 强制进行垃圾回收
            import gc
            gc.collect()

            # 更新任务信息
            with self.task_phase_lock:
                if task_id in self.task_info_map:
                    task_info = self.task_info_map[task_id]
                    task_info.is_failed = True
                    task_info.is_running = False
                    task_info.error = f"Memory error: {str(me)}"
                    task_info.phase = TaskPhase.FAILED
        except Exception as e:
            logger.error(f"Task {task_id} failed: {str(e)}")
            # 更新任务信息
            with self.task_phase_lock:
                if task_id in self.task_info_map:
                    task_info = self.task_info_map[task_id]
                    task_info.is_failed = True
                    task_info.is_running = False
                    task_info.error = str(e)
                    task_info.phase = TaskPhase.FAILED
        finally:
            # 再次进行垃圾回收
            import gc
            gc.collect()

            # 完成任务
            self.task_done(task_id)

    def task_done(self, task_id: str = ""):
        with self.lock:
            self.current_tasks -= 1

            # 更新资源计数
            if task_id in self.task_info_map:
                task_info = self.task_info_map[task_id]
                if task_info.phase == TaskPhase.DOWNLOAD:
                    self.current_download_tasks -= 1
                elif task_info.phase == TaskPhase.RENDER:
                    self.current_render_tasks -= 1

        # 检查队列中的下一个任务
        self.check_queue()

    def check_queue(self):
        with self.lock:
            # 检查是否有可用资源
            if self.current_tasks < self.max_concurrent_tasks and not self.is_queue_empty():
                # 获取下一个任务
                task_info = self.dequeue()

                # 检查任务类型和资源限制
                can_execute = True
                if task_info.phase == TaskPhase.DOWNLOAD and self.current_download_tasks >= self.max_download_tasks:
                    can_execute = False
                elif task_info.phase == TaskPhase.RENDER and self.current_render_tasks >= self.max_render_tasks:
                    can_execute = False

                if can_execute:
                    # 更新资源计数
                    self.current_tasks += 1
                    if task_info.phase == TaskPhase.DOWNLOAD:
                        self.current_download_tasks += 1
                    elif task_info.phase == TaskPhase.RENDER:
                        self.current_render_tasks += 1

                    # 执行任务
                    task_info.is_running = True
                    self.execute_task(task_info.func, *task_info.args, **task_info.kwargs)
                else:
                    # 如果资源不足，将任务重新放回队列
                    self.enqueue(task_info)

    def enqueue(self, task_info: TaskInfo):
        self.queue.put(task_info)

    def dequeue(self):
        return self.queue.get()

    def is_queue_empty(self):
        return self.queue.empty()

    def update_task_phase(self, task_id: str, phase: TaskPhase, progress: int = 0):
        """更新任务阶段"""
        with self.task_phase_lock:
            if task_id in self.task_info_map:
                task_info = self.task_info_map[task_id]
                old_phase = task_info.phase
                task_info.phase = phase
                task_info.progress = progress
                task_info.last_update_time = time.time()

                # 执行阶段钩子
                if phase in self.phase_hooks:
                    for hook in self.phase_hooks[phase]:
                        hook(task_id, old_phase, phase)

                logger.debug(f"Task {task_id} phase updated: {old_phase} -> {phase}, progress: {progress}%")

    def register_phase_hook(self, phase: TaskPhase, hook: Callable[[str, TaskPhase, TaskPhase], None]):
        """注册阶段钩子"""
        if phase not in self.phase_hooks:
            self.phase_hooks[phase] = []
        self.phase_hooks[phase].append(hook)

    def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        return self.task_info_map.get(task_id)

    def get_all_task_info(self) -> List[TaskInfo]:
        """获取所有任务信息"""
        return list(self.task_info_map.values())

    def get_active_tasks(self) -> List[TaskInfo]:
        """获取所有活动任务"""
        return [task for task in self.task_info_map.values() if task.is_running]

    def get_queued_tasks(self) -> List[TaskInfo]:
        """获取所有排队任务"""
        return [task for task in self.task_info_map.values() if not task.is_running and not task.is_complete and not task.is_failed]

    def get_completed_tasks(self) -> List[TaskInfo]:
        """获取所有完成任务"""
        return [task for task in self.task_info_map.values() if task.is_complete]

    def get_failed_tasks(self) -> List[TaskInfo]:
        """获取所有失败任务"""
        return [task for task in self.task_info_map.values() if task.is_failed]

    def clear_completed_tasks(self):
        """清除所有完成任务"""
        with self.task_phase_lock:
            for task_id in list(self.task_info_map.keys()):
                if self.task_info_map[task_id].is_complete or self.task_info_map[task_id].is_failed:
                    del self.task_info_map[task_id]
