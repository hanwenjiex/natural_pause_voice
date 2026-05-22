# -*- coding: utf-8 -*-
"""
网络波动模拟器 v1.0
会议专用小工具

原理：
  通过 Windows Core Audio API 控制麦克风静音/音量（音视频会议里直接生效）
  通过 OpenCV + 虚拟摄像头 模拟画面卡顿（需在会议里选择虚拟摄像头）
  全部在用户层操作，不破坏任何系统组件

用法：
  pip install -r requirements.txt
  python main.py

打包：
  pyinstaller --onefile --noconsole --name "网络波动模拟器" main.py
"""

import tkinter as tk
from tkinter import ttk
import threading
import time
import random
import sys
from enum import Enum

# ─── 依赖检查 ───────────────────────────────────────────────────────────

try:
    from comtypes import CLSCTX_ALL, CoInitializeEx, CoUninitialize, COINIT_APARTMENTTHREADED
    HAS_COMTYPES = True
except ImportError:
    HAS_COMTYPES = False

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    import pyvirtualcam
    HAS_VIRTUALCAM = True
except ImportError:
    HAS_VIRTUALCAM = False


class Intensity(Enum):
    WEAK = "弱"
    MEDIUM = "中"
    STRONG = "强"


# ─── 音频控制器 ─────────────────────────────────────────────────────────
# 通过 Windows Core Audio API 直接操作麦克风，Zoom/Teams/腾讯会议 全都生效

class AudioController:
    def __init__(self):
        self.running = False
        self.intensity = Intensity.MEDIUM
        self._thread = None
        self._stop = threading.Event()
        self._vol = None          # IAudioEndpointVolume (在工线程创建)
        self._orig_vol = 1.0

    def _init_vol(self):
        """初始化麦克风端点音量接口（必须在 COM 已初始化的线程调用）"""
        if not HAS_PYCAW:
            return False
        try:
            # 优先获取麦克风（捕获设备）
            try:
                device = AudioUtilities.GetMicrophone()
            except AttributeError:
                # 旧版 pycaw 回退：直接用 COM 枚举捕获设备
                from pycaw.api.mmdevice import IMMDeviceEnumerator
                from pycaw.constants import CLSID_MMDeviceEnumerator
                enum = IMMDeviceEnumerator()
                device = enum.GetDefaultAudioEndpoint(1, 0)  # eCapture=1
            if device is None:
                return False
            self._vol = device.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None
            ).QueryInterface(IAudioEndpointVolume)
            return True
        except Exception as e:
            print(f"[音频] 初始化失败: {e}")
            return False

    def _params(self):
        return {
            Intensity.WEAK: {
                'chance': 0.12,                         # 触发概率
                'interval': (2.5, 4.5),                 # 检测间隔(秒)
                'mute_dur': (0.2, 0.6),                 # 静音持续
                'vol_range': (0.3, 0.8),                # 音量波动范围
                'stutter_cnt': (2, 3),                  # 断断续续次数
            },
            Intensity.MEDIUM: {
                'chance': 0.30,
                'interval': (1.0, 2.5),
                'mute_dur': (0.3, 1.0),
                'vol_range': (0.1, 0.85),
                'stutter_cnt': (2, 4),
            },
            Intensity.STRONG: {
                'chance': 0.60,
                'interval': (0.3, 1.2),
                'mute_dur': (0.5, 1.5),
                'vol_range': (0.0, 1.0),
                'stutter_cnt': (3, 5),
            },
        }[self.intensity]

    def start(self):
        if self.running or not HAS_PYCAW:
            return
        self.running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        # 如果工线程没来得及恢复，兜底尝试
        if self._vol is not None:
            try:
                self._vol.SetMute(False, None)
            except Exception:
                pass
            self._vol = None

    def _loop(self):
        CoInitializeEx(COINIT_APARTMENTTHREADED)
        try:
            if not self._init_vol() or self._vol is None:
                self.running = False
                return

            # 保存原始状态并初始化
            self._orig_vol = self._vol.GetMasterVolumeLevelScalar()
            self._vol.SetMute(False, None)
            self._vol.SetMasterVolumeLevelScalar(1.0, None)

            while not self._stop.is_set():
                p = self._params()
                wait = random.uniform(*p['interval'])

                if self._stop.wait(wait):
                    break

                if random.random() >= p['chance']:
                    continue

                # 随机选一种效果
                effect = random.choices(
                    ['mute', 'volume', 'stutter', 'pause'],
                    weights=[35, 25, 25, 15],
                )[0]

                try:
                    if effect == 'mute':
                        """随机静音一段时间"""
                        d = random.uniform(*p['mute_dur'])
                        self._vol.SetMute(True, None)
                        self._stop.wait(d)
                        self._vol.SetMute(False, None)

                    elif effect == 'volume':
                        """音量忽大忽小"""
                        target = random.uniform(*p['vol_range'])
                        self._vol.SetMasterVolumeLevelScalar(target, None)
                        self._stop.wait(random.uniform(0.3, 1.0))
                        self._vol.SetMasterVolumeLevelScalar(1.0, None)

                    elif effect == 'stutter':
                        """快速交替静音/不静音 = 断断续续"""
                        n = random.randint(*p['stutter_cnt'])
                        for _ in range(n):
                            if self._stop.is_set():
                                break
                            self._vol.SetMute(True, None)
                            self._stop.wait(random.uniform(0.05, 0.15))
                            self._vol.SetMute(False, None)
                            self._stop.wait(random.uniform(0.05, 0.15))

                    elif effect == 'pause':
                        """静音 + 音量归零（模拟完全断连）"""
                        d = random.uniform(*p['mute_dur'])
                        self._vol.SetMute(True, None)
                        self._vol.SetMasterVolumeLevelScalar(0.0, None)
                        self._stop.wait(d)
                        self._vol.SetMute(False, None)
                        self._vol.SetMasterVolumeLevelScalar(1.0, None)

                except Exception as e:
                    print(f"[音频] 效果执行异常: {e}")

            # — 退出循环，恢复原始状态 —
            try:
                self._vol.SetMute(False, None)
                self._vol.SetMasterVolumeLevelScalar(self._orig_vol, None)
            except Exception:
                pass

        except Exception as e:
            print(f"[音频] 循环异常: {e}")
        finally:
            self._vol = None
            CoUninitialize()
            self.running = False


# ─── 摄像头控制器 ──────────────────────────────────────────────────────
# 捕获真实摄像头 → 添加冻结/卡顿 → 输出到虚拟摄像头
# 需要在会议软件里手动选择虚拟摄像头作为设备

class CameraController:
    def __init__(self):
        self.running = False
        self.intensity = Intensity.MEDIUM
        self._thread = None
        self._stop = threading.Event()
        self.available = HAS_OPENCV and HAS_VIRTUALCAM

    def _params(self):
        return {
            Intensity.WEAK: {
                'chance': 0.08,
                'freeze_min': 0.1,
                'freeze_max': 0.3,
            },
            Intensity.MEDIUM: {
                'chance': 0.18,
                'freeze_min': 0.2,
                'freeze_max': 0.5,
            },
            Intensity.STRONG: {
                'chance': 0.35,
                'freeze_min': 0.3,
                'freeze_max': 1.0,
            },
        }[self.intensity]

    def start(self):
        if not self.available or self.running:
            return
        self.running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self):
        cap = None
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                print("[摄像头] 无法打开摄像头 (索引 0)")
                self.running = False
                return

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)

            ret, frame = cap.read()
            if not ret:
                print("[摄像头] 无法读取画面")
                cap.release()
                self.running = False
                return

            frozen = frame.copy()
            frozen_until = 0.0

            with pyvirtualcam.Camera(
                width=640, height=480, fps=30,
                backend='obs', print_fps=False,
            ) as cam:
                print(f"[摄像头] 虚拟摄像头已就绪: {cam.device}")

                while not self._stop.is_set():
                    now = time.time()
                    p = self._params()

                    if now < frozen_until:
                        # 画面冻结 → 发送缓存帧
                        cam.send(frozen)
                    else:
                        # 正常读取
                        ret, frame = cap.read()
                        if not ret:
                            break

                        # 随机触发卡顿
                        if self.running and random.random() < p['chance']:
                            frozen = frame.copy()
                            frozen_until = now + random.uniform(
                                p['freeze_min'], p['freeze_max']
                            )

                        cam.send(frame)

                    cam.sleep_until_next_frame()

        except pyvirtualcam.backends.obs.FoundNoCameraError:
            print("[摄像头] 未检测到 OBS 虚拟摄像头驱动")
            print("[摄像头] 请先安装 OBS Studio 或在会议里选择真实摄像头")
        except Exception as e:
            print(f"[摄像头] 异常: {e}")
        finally:
            if cap:
                cap.release()
            self.running = False


# ─── 桌面悬浮窗 ────────────────────────────────────────────────────────

COLORS = {
    'bg': '#2d2d2d',
    'title_bg': '#3a3a3a',
    'border': '#555555',
    'status_ok': '#66cc66',
    'status_bad': '#ff6644',
    'btn_normal': '#4a4a4a',
    'btn_active': '#cc4444',
    'accent': '#ffaa33',
    'text': '#aaaaaa',
    'close': '#777777',
    'close_hover': '#ff4444',
}


class FloatingWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("网络波动模拟器")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.95)

        self.W, self.H = 280, 120
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - self.W) // 2
        y = sh - self.H - 80
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self._active = False
        self._audio = AudioController()
        self._camera = CameraController()
        self._drag = {'x': 0, 'y': 0}
        self._tick_id = None

        self._build_ui()
        self._tick()          # 定时更新状态指示

    # ── UI 构建 ────────────────────────────────────────────────────────

    def _build_ui(self):
        # 主框架
        main = tk.Frame(
            self.root, bg=COLORS['bg'],
            highlightbackground=COLORS['border'], highlightthickness=1,
        )
        main.pack(fill=tk.BOTH, expand=True)

        # ── 标题栏（拖动区域） ──
        title_bar = tk.Frame(main, bg=COLORS['title_bg'], height=22)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        tk.Label(
            title_bar, text=" 网络波动模拟器",
            bg=COLORS['title_bg'], fg='#cccccc',
            font=('Microsoft YaHei', 9),
        ).pack(side=tk.LEFT, padx=6)

        close_btn = tk.Label(
            title_bar, text="✕",
            bg=COLORS['title_bg'], fg=COLORS['close'],
            font=('Arial', 11), cursor='hand2',
        )
        close_btn.pack(side=tk.RIGHT, padx=6)
        close_btn.bind('<Enter>', lambda e: close_btn.configure(fg=COLORS['close_hover']))
        close_btn.bind('<Leave>', lambda e: close_btn.configure(fg=COLORS['close']))
        close_btn.bind('<Button-1>', lambda e: self._quit())

        # 拖动绑定
        for w in (title_bar, title_bar.winfo_children()[0]):
            w.bind('<Button-1>', self._drag_start)
            w.bind('<B1-Motion>', self._drag_move)

        # ── 主体 ──
        body = tk.Frame(main, bg=COLORS['bg'])
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(3, 5))

        # 状态行
        row1 = tk.Frame(body, bg=COLORS['bg'])
        row1.pack(fill=tk.X)
        self._lbl_status = tk.Label(
            row1, text="● 正常",
            bg=COLORS['bg'], fg=COLORS['status_ok'],
            font=('Microsoft YaHei', 8, 'bold'), anchor='w',
        )
        self._lbl_status.pack(side=tk.LEFT)

        if self._camera.available:
            self._lbl_cam = tk.Label(
                row1, text="📷",
                bg=COLORS['bg'], fg='#666666',
                font=('Microsoft YaHei', 8),
            )
            self._lbl_cam.pack(side=tk.RIGHT)

        # 开关按钮
        self._btn = tk.Button(
            body, text="🚀 开始卡顿",
            bg=COLORS['btn_normal'], fg='#ffffff',
            font=('Microsoft YaHei', 10, 'bold'),
            bd=0, padx=12, pady=3, cursor='hand2',
            activebackground='#555555', activeforeground='#ffffff',
            command=self._toggle,
        )
        self._btn.pack(fill=tk.X, pady=(4, 3))

        # 强度滑块行
        row2 = tk.Frame(body, bg=COLORS['bg'])
        row2.pack(fill=tk.X)
        tk.Label(
            row2, text="强度:",
            bg=COLORS['bg'], fg=COLORS['text'],
            font=('Microsoft YaHei', 8),
        ).pack(side=tk.LEFT)

        self._int_var = tk.IntVar(value=1)
        ttk.Scale(
            row2, from_=0, to=2, orient=tk.HORIZONTAL,
            variable=self._int_var, command=self._on_intensity,
            length=160,
        ).pack(side=tk.LEFT, padx=(4, 2))

        self._lbl_int = tk.Label(
            row2, text="中",
            bg=COLORS['bg'], fg=COLORS['accent'],
            font=('Microsoft YaHei', 8, 'bold'), width=3,
        )
        self._lbl_int.pack(side=tk.LEFT)

    # ── 事件处理 ───────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._drag['x'] = e.x
        self._drag['y'] = e.y

    def _drag_move(self, e):
        dx = e.x - self._drag['x']
        dy = e.y - self._drag['y']
        self.root.geometry(f"+{self.root.winfo_x()+dx}+{self.root.winfo_y()+dy}")

    def _on_intensity(self, val):
        v = round(float(val))
        self._int_var.set(v)
        labels = {0: "弱", 1: "中", 2: "强"}
        self._lbl_int.configure(text=labels[v])
        intensities = [Intensity.WEAK, Intensity.MEDIUM, Intensity.STRONG]
        ii = intensities[v]
        if self._active:
            self._audio.intensity = ii
            self._camera.intensity = ii

    def _toggle(self):
        if self._active:
            self._stop()
        else:
            self._start()

    def _start(self):
        self._active = True
        v = self._int_var.get()
        ii = [Intensity.WEAK, Intensity.MEDIUM, Intensity.STRONG][v]
        self._audio.intensity = ii
        self._camera.intensity = ii

        self._audio.start()
        self._camera.start()

        self._btn.configure(text="🛑 停止卡顿", bg=COLORS['btn_active'])
        self._lbl_status.configure(text="● 波动中", fg=COLORS['status_bad'])

    def _stop(self):
        self._active = False
        self._audio.stop()
        self._camera.stop()

        self._btn.configure(text="🚀 开始卡顿", bg=COLORS['btn_normal'])
        self._lbl_status.configure(text="● 正常", fg=COLORS['status_ok'])

    def _tick(self):
        """每秒刷新状态指示"""
        if hasattr(self, '_lbl_cam'):
            if self._camera.running:
                self._lbl_cam.configure(fg='#66cc66')
            else:
                self._lbl_cam.configure(fg='#666666')
        self._tick_id = self.root.after(2000, self._tick)

    def _quit(self):
        if self._tick_id:
            try:
                self.root.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None
        self._stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ─── 入口 ──────────────────────────────────────────────────────────────

def main():
    print("╔═══════════════════════════════════════╗")
    print("║        网络波动模拟器 v1.0            ║")
    print("║        会议专用小工具                  ║")
    print("╚═══════════════════════════════════════╝")

    missing = []
    if not HAS_COMTYPES:
        missing.append("comtypes")
    if not HAS_PYCAW:
        missing.append("pycaw")
    if not HAS_OPENCV:
        missing.append("opencv-python-headless")
    if not HAS_VIRTUALCAM:
        missing.append("pyvirtualcam")

    if missing:
        print(f"\n! 缺少依赖: {', '.join(missing)}")
        print("  请运行: pip install -r requirements.txt\n")
        print("  （缺少以上库时对应功能不可用，工具仍会启动）")

    print("\n  提示: 摄像头效果需要 OBS 虚拟摄像头驱动")
    print("        (https://obsproject.com/)\n")

    app = FloatingWindow()
    app.run()


if __name__ == '__main__':
    main()
