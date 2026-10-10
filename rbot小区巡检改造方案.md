# 基于 rbot 的小区巡检仿真改造方案

> 目标：让 rbot 仿真小车在 Gazebo 小区场景中巡逻，能识别红绿灯、识别行人立牌，并根据视觉辅助规划路线。
> 基线仓库：https://github.com/rlxai/rbot（ROS 2 Jazzy + Gazebo Harmonic，Apache 2.0）

---

## 一、源码分析结论（现有能力盘点）

### 1.1 可以直接复用的部分

| 能力 | 位置 | 说明 |
|---|---|---|
| 差速小车底盘 | `src/robot/rlai_description/urdf/` | URDF/Xacro + 网格，`ros2_control` 差速控制 |
| RGB-D 相机 | `gazebo_sensors.urdf.xacro` | **RGB 640×480 @30Hz，话题 `/depth_camera/image_raw`**；深度图 `/depth_camera/depth`；HFoV 87°，已桥接到 ROS |
| 2D 激光 / IMU / GPS | 同上 | 建图定位现成可用 |
| 建图定位 | `src/mapping`、`src/localization` | SLAM Toolbox + EKF + AMCL |
| 导航 | `src/navigation` | Nav2，MPPI 控制器 + SMAC Hybrid-A* |
| 巡逻模式 | `nav_client.py` | `mode:=patrol` 已实现 FollowWaypoints 多航点巡逻，**只需改航点坐标** |
| 仿真启动 | `src/bringup/.../simulation.launch.py` | 支持 `world:=` 参数一键切换场景 |

### 1.2 必须自己开发的部分

| 缺口 | 现状 | 需要做的事 |
|---|---|---|
| 小区 world | 只有仓库/庭院场景（`outdoor_courtyard.sdf` 最接近） | 新建 `community.sdf`：道路、楼栋、路口红绿灯、行人立牌 |
| 红绿灯识别 | perception 包只有激光/深度处理，无图像识别 | 新增视觉识别节点 + 路口停车逻辑 |
| 行人立牌识别 | 同上 | 新增检测节点 |
| 视觉辅助路线 | Nav2 纯地图规划 | 视觉作为路标/红绿灯触发条件，接入巡逻流程 |

---

## 二、总体架构

```
                    ┌─────────────────────────────────────┐
                    │  Gazebo Harmonic — community.sdf    │
                    │  (道路/楼栋/红绿灯/行人立牌模型)      │
                    └──────────────┬──────────────────────┘
                                   │ ros_gz_bridge（沿用现有 yaml）
   /scan /imu /odom ───────────────┤
   /depth_camera/image_raw (RGB) ──┤
   /depth_camera/depth ────────────┤
                                   ▼
   ┌──────────────┐   ┌────────────────────┐   ┌─────────────────┐
   │ SLAM/AMCL    │   │ 视觉感知层（新增）   │   │ Nav2 导航        │
   │ EKF 建图定位  │   │ traffic_light_      │   │ MPPI + Hybrid-A*│
   └──────┬───────┘   │ detector_node       │   └────────┬────────┘
          │           │ pedestrian_sign_    │            │
          │           │ detector_node       │            │
          │           └─────────┬──────────┘            │
          │                     │ /traffic_light_state   │
          │                     │ /pedestrian_detected   │
          ▼                     ▼                        ▼
   ┌────────────────────────────────────────────────────────────┐
   │ patrol_manager（新增）：巡逻状态机                            │
   │   巡航 → 接近路口 → 读红绿灯 → 红:停车等待 / 绿:通过 → 下一航点 │
   └────────────────────────────────────────────────────────────┘
```

---

## 三、实施步骤

### 第 1 步：搭建小区 world（`community.sdf`）

- 以 `outdoor_courtyard.sdf`（356 行，纯几何搭建）为模板，新建 `src/simulation/rlai_gazebo/worlds/community.sdf`
- 内容：
  - **道路**：灰色长方体地面贴图 + 白色车道线（SDF 几何体即可，无需外部素材）
  - **楼栋**：用现有 `warehouse_shelf` 改造或自建 box 楼栋模型（4–6 栋围合）
  - **红绿灯**：新建模型 `traffic_light/model.sdf` —— 立杆 + 三灯圆盘，红/黄/绿灯用三个独立 link，**每个灯单独发 UV 光照材质**，便于视觉识别（纯色、高对比）
  - **行人立牌**：新建 `pedestrian_sign/model.sdf` —— 黄底黑图行人图案，用 Gazebo 内置 material 或程序生成的贴图
- 在 `rlai_gazebo/CMakeLists.txt` 注册新 world 和新模型

### 第 2 步：新增红绿灯识别节点

新包 `src/perception/rlai_vision/`（ament_python）：

```
rlai_vision/
├── rlai_vision/
│   ├── traffic_light_detector.py   # 红绿灯识别
│   ├── pedestrian_sign_detector.py # 行人立牌识别
│   └── patrol_manager.py           # 巡逻状态机
└── launch/vision.launch.py
```

**识别方案（分级，从简到难）：**

- **Level 1（推荐起步）— OpenCV 颜色分割**：
  - 订阅 `/depth_camera/image_raw`（RGB 640×480）
  - HSV 阈值分割红/绿圆斑（`cv2.inRange` + 圆形轮廓检测 + 面积过滤）
  - 发布 `/traffic_light_state`（`std_msgs/String`：RED / GREEN / UNKNOWN）
  - 优点：无需训练数据，仿真里纯色高对比，准确率极高；一天可完成
- **Level 2 — YOLOv8/11**：如后续要区分箭头灯、行人图案，换 `ultralytics` + 自标数据集（仿真内自动截图标注，成本也不高）

### 第 3 步：行人立牌识别节点

- Level 1：同样 OpenCV——黄底色块检测 + 黑色行人图案模板匹配
- Level 2：YOLO 类别 `pedestrian_sign`
- 发布 `/pedestrian_detected`（`std_msgs/Bool`），并附方位角（用检测框中心 x 像素 + 相机内参换算）

### 第 4 步：巡逻状态机（视觉 → 行为联动）

改造 `patrol_manager.py`（参考 `nav_client.py` 的 FollowWaypoints 写法）：

1. 航点列表改为小区路线（在小区地图上标注：出发充电桩 → 路口1 → ... → 路口N）
2. 每个路口航点前设「预停点」（距路口 2m）
3. 到达预停点 → 订阅 `/traffic_light_state`：
   - **RED** → 停车（发零速 TwistStamped 到 `/cmd_vel`，或调 velocity_smoother 抑制），每秒重查，GREEN 后继续
   - **GREEN** → 直接通过
4. 巡逻中收到 `/pedestrian_detected=true` → 减速绕行（Nav2 costmap 2D 激光已能避障，视觉信息主要用于提前降速和日志记录）

### 第 5 步：视觉辅助路线规划

- **导航主体仍走 Nav2**（激光建图 + SMAC Hybrid-A*，在小区静态地图上规划最稳）
- 视觉的三种辅助方式（按优先级）：
  1. **路口管控**（第 4 步，必做）
  2. **视觉路标校正**：识别到立牌/红绿灯时结合 TF 记录实际位置，与 AMCL 位姿比对做偏差告警
  3. **进阶（可选）**：把视觉检测框投影进 Nav2 costmap 作为临时障碍层

### 第 6 步：集成启动

在 `simulation.launch.py` 增加 Launch 参数：`vision_enabled:=true`、`patrol_enabled:=true`，一键启动：

```bash
ros2 launch rlai_bringup simulation.launch.py \
  world:=community vision_enabled:=true patrol_enabled:=true \
  use_amcl:=true map_yaml_file:=/ros2_ws/maps/community_map.yaml
```

---

## 四、里程碑

| 阶段 | 交付物 | 验收标准 |
|---|---|---|
| M1 环境搭建 | Docker 起 rbot 基线，小车在仓库 world 巡逻成功 | `run_sim.sh --rviz-nav` + patrol 跑通 |
| M2 小区场景 | community.sdf + 建好的小区地图 | 能建图保存为 `community_map.yaml` |
| M3 红绿灯识别 | traffic_light_detector + 预停点停车逻辑 | 红灯停、绿灯走，≥95% 准确率 |
| M4 行人立牌识别 | pedestrian_sign_detector + 减速绕行 | 检测到立牌即降速 |
| M5 集成联调 | 一键启动 + 完整巡逻闭环 | 巡逻全流程无人工干预跑完 3 圈 |

## 五、风险与注意点

1. **Windows 运行环境**：需 Docker Desktop（WSL2 后端）或 Ubuntu 24.04 虚拟机；Gazebo Harmonic 无原生 Windows 支持
2. **TF 冲突**：勿同时开 `mapping_enabled` 和 `use_amcl`（都发 `map→odom`，README 明确警告）
3. **光照一致性**：仿真内 OpenCV 颜色阈值要对 world 光照标定一次；如果以后迁移真机，直接换 YOLO
4. **相机话题**：RGB 是 `/depth_camera/image_raw`（不是 RealSense 风格的 `.../color/image_raw`），桥接已配好，不用改 bridge yaml
