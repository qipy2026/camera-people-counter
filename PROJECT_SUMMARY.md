# 摄像头定时快照 + 人数监测系统 — 总结

## 需求

- 摄像头定时快照（工作日 上午2张 + 下午2张，可人工设置时间）
- YOLO 人数检测
- Web 仪表盘（散点图 + 快照预览）
- CSV 数据导出（周报用）
- 人数波动可视化

## 最终技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 采集 | OpenCV VideoCapture | RTSP/HTTP/USB/视频文件全支持 |
| 检测 | YOLOv11-nano (Ultralytics) | CPU 推理 ~0.5s/帧，5分钟间隔绰绰有余 |
| 调度 | APScheduler + CronTrigger | 按时间点触发，支持工作日过滤 |
| 数据库 | SQLite (WAL模式) | 单摄每天288行，SQLite够用十年，零运维 |
| 后端 | Flask + Blueprint | 轻量，分析API独立模块 |
| 前端 | Chart.js 4.4 + 散点图 | 时间轴 + 点击弹窗 |
| 部署 | Docker Compose | 单容器，一键启动 |

## 架构

```
摄像头(RTSP) → APScheduler CronTrigger → OpenCV 采集帧
    → YOLO 推理 → SQLite 写入 → Flask API
        ├── GET /api/counts/latest     (当前人数)
        ├── GET /api/counts/timeseries (时序数据)
        ├── GET /api/export/csv        (CSV导出 UTF-8 BOM)
        ├── GET /api/health            (健康检查)
        ├── GET /api/schedule          (时间点管理 CRUD)
        └── GET /snapshots/<filename>  (快照图片)
            ↓
    Chart.js 散点图 → 点击弹窗 Modal (大图+时间+人数)
```

## 关键文件

```
search/
├── app.py                    # Flask入口 + APScheduler + 图片serve
├── db.py                     # SQLite CRUD + 时序聚合 + 调度表
├── config.py                 # 环境变量配置管理
├── startup_check.py          # 启动前4项校验 (配置/DB/模型/目录)
├── analytics.py              # API Blueprint (5端点 + 调度管理)
├── health.py                 # Health Blueprint
├── snapshot_counter.py       # 独立CLI脚本
├── templates/dashboard.html  # Chart.js 散点图 + Modal + 设置页
├── Dockerfile + docker-compose.yml
└── tests/
    ├── test_db.py            # 9项单元测试
    └── test_integration.py   # 端到端集成测试
```

## 设计决策演变

最初的方案经过了 `/office-hours` → `/plan-eng-review` 两轮审查，做了三次重大简化：

| 决策 | 原始方案 | 最终方案 | 为什么改 |
|------|---------|---------|----------|
| 数据库 | TimescaleDB | SQLite | 单摄288行/天，SQLite够用十年；外部审查指出TimescaleDB解决不存在的规模问题 |
| 检测引擎 | Fork dvr-yolov8-detection | 自建 snapshot_counter.py | Fork 绑定101KB单体 Flask；自建更轻量 |
| 异常检测 | Z-score + MAD降级 + 冷启动 + 两级告警 | 不做自动告警，图表肉眼判断 | 用户只说了"波动不能太大"，没说要自动化告警 |
| 调度方式 | IntervalTrigger (每N分钟) | CronTrigger (按时间点) | 用户明确要求上午2次+下午2次 |
| 导出格式 | CSV + Excel + PNG | 仅CSV (UTF-8 BOM) | Excel可直接打开CSV，PNG导出复杂度不值得 |
| 部署 | GitHub Actions CI/CD | 手动 docker compose build | 内部单机工具不需要CI |

## 遇到的坑

### 1. Chart.js 4.x 时间轴静默失败 ⚠️ 最坑
**现象:** 散点图什么都不显示，控制台无报错。
**原因:** Chart.js 4.x 使用 `type:'time'` 坐标轴必须单独加载日期适配器库 `chartjs-adapter-date-fns`。缺少这个库时，图表静默失败——不渲染、不报错。
**修复:** 在 Chart.js CDN 后加一行：
```html
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
```
**教训:** Chart.js 4.x 拆分了日期适配器。凡是时间轴图表，检查是否加载了适配器。

### 2. numpy/opencv 版本冲突
**现象:** `cv2.rectangle()` / `cv2.copyMakeBorder()` 报 `img is not a numpy array`
**原因:** ultralytics 依赖 `numpy<2`，但新版 opencv-python 需要 `numpy>=2`。pip 安装时 numpy 被降级到 1.x，opencv 无法识别 numpy 数组。
**修复:** `pip install "numpy>=2"` 覆盖旧版。
**教训:** Python 生态中 opencv + torch + ultralytics 三者的 numpy 版本约束互相矛盾。先装 torch/ultralytics，再强制升级 numpy。

### 3. Flask 模板缓存
**现象:** 修改 `templates/dashboard.html` 后刷新浏览器不生效。
**原因:** Flask 非 debug 模式会缓存模板。`app.run(debug=False)` 时 Jinja2 使用内存缓存，不会检测文件变更。
**修复:** 杀掉 Python 进程重新启动，或用 `debug=True`（但会启用重载器，可能和 APScheduler 冲突）。
**教训:** 开发阶段设置 `debug=True`；生产部署前切回 `False`。修改模板后必须重启。

### 4. APScheduler CronTrigger 工作日过滤
**现象:** 需要只在工作日触发快照。
**原因:** CronTrigger 的 `day_of_week` 参数支持 cron 表达式，但文档不直观。
**修复:** 
```python
CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri")
```
`day_of_week` 支持: `mon-fri` (工作日), `0-4` (数字), `1,2,3,4,5` (逗号分隔)。
**教训:** APScheduler CronTrigger 的 `day_of_week` 使用 cron 约定（0=Sunday），不是 Python 的 weekday()（0=Monday）。

### 5. Windows 路径分隔符
**现象:** `snapshot_path` 在数据库中是 `snapshot_data\snap_xxx.jpg`（反斜杠），JS 端 `split('/').pop()` 拿不到文件名。
**原因:** Windows `Path` 对象转字符串默认使用 `\`。
**修复:** JS 端先 `replace(/\\/g, '/')` 再 `split('/').pop()`。
**教训:** 跨平台路径处理，统一在写入 DB 前转为 POSIX 风格（`/`），或者在读取端兼容两种分隔符。

### 6. GitHub HTTPS 端口被封 (443)
**现象:** `git push` 超时，`Failed to connect to github.com port 443`。
**原因:** 网络环境封了 443 端口。
**修复:** 
```bash
gh auth setup-git     # 让 git 使用 gh 的认证代理
git push origin master
```
`gh auth setup-git` 配置 git credential helper，走 gh CLI 的 HTTP 通道（可能用不同端口或代理）。
**教训:** 在受限网络环境，优先用 `gh` CLI 而非直接 `git`。

### 7. Playwright Chromium 下载
**现象:** `npx playwright install chromium` 超时/失败。
**原因:** 默认从 GitHub/Google 下载 ~300MB 的 Chromium 二进制，直连被墙。
**修复:**
```bash
# 国内镜像加速
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright npx playwright install chromium

# 如果下载了zip但没解压（常见于镜像源）
cd %USERPROFILE%\AppData\Local\ms-playwright
unzip -o chrome-headless-shell-1208.zip -d chromium_headless_shell-1208
```
**教训:** 镜像源下载的 zip 有时不会自动解压，需手动检查目录是否存在。

### 8. yt-dlp 下载抖音视频需要 cookies
**现象:** `yt-dlp` 报 `Fresh cookies are needed`
**原因:** 抖音视频页面需要登录态或浏览器 cookies。
**修复:** 未解决——headless 浏览器无法获取已登录浏览器的 cookies。替代方案是用合成数据测试。
**教训:** 中国视频平台（抖音/B站）的反爬机制较严，测试阶段用合成/公开数据集更高效。

### 9. 数据点全部为0导致图表"没数据"的错觉
**现象:** 用户反馈"网页上没有数据"。
**原因:** 测试视频只有50秒，播完后每帧都返回 None，快照全部失败。数据库里 person_count 全是0或null，散点图虽然有54个点但全部压在 y=0 线上，视觉上像没数据。加上缺少 Chart.js 日期适配器（见坑#1），两个问题叠加。
**修复:** 
1. 加 Chart.js 日期适配器
2. 灌入模拟数据（不同时间段、不同人数）
3. 过滤掉没有快照图片的数据点
**教训:** "没有数据"的根因可能有多个（JS错误 + 数据质量问题 + 视觉问题），逐一排查不要假设是单一原因。

### 10. 散点图只显示有快照的数据点
**现象:** 用户点击数据点提示"此数据点没有关联快照图片"。
**原因:** 模拟数据灌入时 `snapshot_path` 为空字符串。
**修复:** 图表数据过滤 `p.snapshot_path` 非空；同时为存量数据拍真实快照关联。
**教训:** 模拟数据和真实数据的完整性要一致，尤其涉及文件引用的字段。

## 经验总结

1. **前端 JS 库的隐式依赖是最隐蔽的 bug。** Chart.js 静默失败浪费了大量排查时间。凡是涉及 CDN 引入的库，先确认是否所有 peer dependency 都已加载。

2. **Python 依赖版本冲突是常态。** opencv + torch + ultralytics + numpy 的组合几乎必定有版本问题。锁定版本号的 `requirements.txt` 比 `pip install` 靠谱。

3. **外部审查（Outside Voice）救了方案。** TimescaleDB、异常检测引擎、Fork 策略这三个过度设计都是在外部审查中指出并砍掉的，最终工时从 3-4 周降到 2.5 天。

4. **先跑通管道再优化 UI。** API + 数据层先验证（curl 测试所有端点），确认数据流正确后再调前端。前端不出数据时，先检查 API 返回是否正确。

5. **测试数据要有人为多样性。** 全0或全1的测试数据看不出图表问题，也发现了不了人数波动分析的 bug。刻意制造 1-8 人的不均匀分布。

6. **Windows 开发环境的路径/端口/编码问题要提前处理。** 反斜杠路径、GBK编码、443端口被封——每个都是踩过才知道的坑。
