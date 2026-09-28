---
version: alpha
name: "AudioEnhancer"
description: "Windows 音效预设面板，以暗色控制台承载霓虹音柱和可暂停的音符动画。"
colors:
  background: "#14181f"
  panel: "#1b2029"
  card: "#20262f"
  border: "#2e3642"
  text: "#e8eaed"
  secondary-text: "#9aa3ad"
  primary: "#f0c060"
  visual-background: "#10141c"
  visual-magenta: "#ff3f88"
  visual-lavender: "#a6aaff"
  visual-cyan: "#3cdec8"
  visual-blue: "#3e66fa"
typography:
  sans:
    fontFamily: "system-ui, sans-serif"
rounded:
  card: "12px"
  visualizer: "15px"
  power-button: "19px"
spacing:
  content-inset: "24px"
  content-gap: "12px"
  card-gap: "14px"
components:
  power-button: {}
  effect-card: {}
  music-visualizer: {}
---

# AudioEnhancer 设计规范

## Overview

面向 Windows 桌面用户，主要任务是选择一个固定音效预设并确认它是否已生效。界面沿用现有暗色面板和金色操作按钮。参考图中的霓虹音柱是唯一鲜艳的视觉焦点；它用于表现活跃状态，不代表实时音频分析。布局与操作文案以清楚、稳定为先。

运行时色值以 `main.py` 中的 `C_*` 常量和 `music_visualizer.py` 中的绘制色值为准；本文记录用途和对应值。改动共享色值时同步更新本文与代码。

## Colors

背景、面板、卡片和边框分别对应 `main.py` 的 `C_BG`、`C_PANEL`、`C_CARD` 和 `C_CARD_BORDER`。金色 `primary` 用于主操作和选中态。霓虹色只用于动画，左侧由粉色向紫色过渡，中央为淡紫色，右侧由青色向蓝色过渡。音效关闭时降低动画亮度；状态信息仍以文字和符号表达，不能只靠颜色。

## Typography

界面使用 Qt 的系统字体和支持中文的系统回退字体。标题、预设名、说明文字在 `main.py` 中按 19、15 和 11–12 像素区分层级。按钮始终保留文字，图标和动画不承担必要操作说明。

## Layout

八个预设按两列四行等宽排列，卡片高 84 像素、间距 14 像素。内容左右内边距为 24 像素，纵向间距为 12 像素。动画位于标题与 APO 状态之间，高 96 像素。窗口较矮时由主滚动区承载内容；音效操作不被动画遮挡。

## Elevation & Depth

基础层级依靠深浅面色和细边框，不在卡片上叠加大阴影。动画音柱使用几层低透明度描边形成柔和光晕，避免闪烁和高亮覆盖控件。

## Shapes

卡片圆角 12 像素；动画面板 15 像素；电源按钮为胶囊形。音柱使用圆头线条，与音符曲线形成统一的柔和轮廓。

## Components

### Foundational visual states

音效预设选中时以金色边框和文字突出；失败与警告显示文本。电源按钮表现开启与关闭状态。动画播放、暂停均有文字按钮，可用键盘操作。

### Buttons and actions

金色实心按钮仅用于缺失 APO 时的安装和修复。正常状态下“设备设置”和“刷新设备”是次要按钮。动画暂停按钮位于动画右上角，保留可见边框、悬停及焦点状态。

### Navigation and data display

应用只有一个主窗口。动画与设备配置、预设网格按使用顺序排列，滚动区在低高度窗口中保留全部内容。

### Forms and overlays

只有一个 APO 主配置文件，不显示无实际选择作用的下拉框。系统托盘和状态反馈沿用现有行为。

### Iconography

预设卡片使用现有表情图标；动画音符由 Qt 矢量路径绘制，不依赖字体字形或外部素材。

### Motion

音效成功开启后，音柱按 120 BPM 的四拍视觉节奏跳动，音符轻微浮动；关闭音效后静止并降低亮度。默认约 25 帧每秒；窗口隐藏或用户暂停时停止计时器。动画不采集音频，不应宣传为频谱或与播放内容同步。

### Content and data visualization

界面文案使用简体中文。操作和状态必须直说其含义；音柱只是装饰性反馈，真正的音效状态由按钮和状态文本提供。

## Do's and Don'ts

- 保持控制区和预设卡片可读，动画始终位于独立面板内。
- 新增动态效果时提供暂停方式，并在窗口隐藏时停止更新。
- 不把装饰动画描述为实时音频可视化。
- 不为常规按钮和状态文字添加霓虹光晕。
