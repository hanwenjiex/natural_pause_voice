# 网络波动模拟器

一个轻量的桌面小工具，运行后显示悬浮窗，一键模拟视频会议中的网络波动效果——麦克风声音断断续续、摄像头画面卡顿冻结。

## 功能

- **桌面悬浮窗** — 280×120px，置顶显示，可拖动，不遮挡会议画面
- **一键开关** — 点击「开始卡顿」立即生效，关闭后立刻恢复
- **麦克风效果** — 随机静音、音量忽大忽小、声音断续，通过 Windows 音频 API 直接控制麦克风，对 Zoom / Teams / 腾讯会议等全部生效
- **摄像头效果** — 画面随机冻结、掉帧，需配合 OBS 虚拟摄像头使用
- **三档强度** — 弱（偶尔卡）/ 中（正常爆炸）/ 强（几乎听不清）

## 快速开始

### 方式一：直接运行 exe

从 Releases 下载 `网络波动模拟器.exe`，双击运行。

### 方式二：从源码运行

```bash
pip install -r requirements.txt
python main.py
```

### 打包 exe

```bash
build.bat
```

或手动执行：

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name "网络波动模拟器" main.py
```

输出在 `dist/网络波动模拟器.exe`。

## 使用说明

1. 启动后桌面显示一个深色悬浮窗
2. 点击 **🚀 开始卡顿** 启动效果
3. 拖动强度滑块调节卡顿频率（左弱右强）
4. 点击 **🛑 停止卡顿** 立即恢复正常
5. 点击 **✕** 关闭程序

### 摄像头效果设置

摄像头效果需要额外安装 [OBS Studio](https://obsproject.com/)（提供虚拟摄像头驱动）：

1. 安装 OBS Studio
2. 打开 OBS → 工具 → 虚拟摄像头 → 启动
3. 在会议软件中将摄像头切换为「OBS Virtual Camera」
4. 在工具中点击「开始卡顿」后画面即出现卡顿效果

## 文件结构

```
├── main.py              # 主程序（单文件）
├── requirements.txt     # Python 依赖
├── build.bat            # 打包脚本
└── dist/
    └── 网络波动模拟器.exe  # 编译后的可执行文件
```

## 工作原理

- **音频**：通过 Windows Core Audio API（`pycaw`）直接控制麦克风端点的静音状态和音量，不涉及虚拟音频驱动
- **视频**：通过 OpenCV 捕获摄像头画面，添加随机帧冻结效果后通过 `pyvirtualcam` 输出到 OBS 虚拟摄像头
- 全部在用户态操作，不修改系统组件，关闭后完全恢复原始状态

## 依赖

- pycaw — Windows 音频端点控制
- comtypes — COM 接口调用
- opencv-python-headless — 摄像头画面捕获
- pyvirtualcam — 虚拟摄像头输出
- numpy — 图像数据处理

## 系统要求

- Windows 10 / Windows 11
- Python 3.8+（源码运行）
- 麦克风（音频效果）
- 摄像头 + OBS Studio（摄像头效果，可选）
