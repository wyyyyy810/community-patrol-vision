# B → A 模型与参数交付表

**文档状态：正式冻结 v1.0 — 待 A 复现并签核**

**交付方**：B（机器人模型、传感器定义、图像识别）
**接收方**：A（导航、桥接、最终速度仲裁）
**模型来源**：rbot（ROS 2 Jazzy + Gazebo Harmonic），`rlai_description` 包
**基线版本**：git `47af3fc3780bd582837f48ce3785d3d68834a1b7`（2026-05-20）／包版本 `0.1.0`
**本次交付版本**：git **ed50809**（基线 `47af3fc` 之上追加 1 个"命名落地"commit）
**交付日期**：2026-10-03（v1.0）
**实测日期**：2026-09-28（主数据）／2026-10-03（改名后复测）
**实测工况**：RTF ≈ 0.197；`headless:=true`、`camera_processing_enabled:=false`

> **v1.0 相对 v0.9 的变化**：frame 名与相机话题名**已按冻结契约全部落地并实测验证**（见第 2、3 节）。
> 除"待 A 复现签核"外，v0.9 列出的全部遗留事项均已关闭。

> **关于"无 TBD"的准确表述**：契约列出的**必填数值**（几何、footprint、驱动几何、传感器位姿、话题名/类型、里程计来源）**均已实测或从模型文件读取，无空缺**。
> 非契约必填项（`/camera/camera_info`、`/camera/depth` 的单独频率）未测，已明确标注。

> 本表为契约《A/B/C 最小接口契约 v0.1》中「B Robot Model → A 必交参数」的交付。
> 契约要求"交付表必须与模型一致，不允许 A/B 各维护不同数值"，请 A 的配置与本表保持同一套值。

---

## 0. 交付范围与前提

| 项 | 说明 |
|---|---|
| 仿真环境 | Gazebo Harmonic；ROS 2 Jazzy；`use_sim_time=true` |
| 机器人 | 单机器人，差速底盘，机器人名 `rlai_bot` |
| 默认启用传感器 | **2D 雷达、RGB-D 相机、IMU**（3D 雷达 / 双目 / GPS 默认关闭） |
| 实测环境 | VMware 虚拟机 + 软件渲染（`LIBGL_ALWAYS_SOFTWARE=1`）；`headless:=true`、`camera_processing_enabled:=false` |
| 实测工况 | 小车静止（`small_warehouse` 世界，出生点 x=1.0, y=1.0） |
| 文件位置 | **Ubuntu 虚拟机 `~/rbot`**（`/home/aic-w/rbot`）。Windows 侧另有一份未改名的只读副本，勿用 |

**实测启动命令**（A 复现时请保持一致，否则频率不可比）：

```bash
source /opt/ros/jazzy/setup.bash && source ~/rbot/install/setup.bash
ros2 launch rlai_bringup simulation.launch.py headless:=true camera_processing_enabled:=false
```

**A 需要在本表基础上做的事**（不在 B 职责内）：
- 桥接发布 `/scan`、相机话题（B 提供 Gazebo 传感器源，A 负责桥接，**不能双方各发布一份**）
- 配置 Nav2 footprint / inflation（本表 footprint **不含**安全余量）
- `/odom` 话题重映射（见第 4 节）

---

## 1. 整车几何（robot_width / robot_length / footprint）

| 参数 | **实值** | 说明 |
|---|---|---|
| robot_width | **0.40 m** | 碰撞外轮廓最大横向宽度。底盘碰撞盒宽 ±0.20；驱动轮外缘仅 ±0.195、万向轮 ±0.15，均更窄，故由底盘宽度决定 |
| robot_length | **0.502 m** | 碰撞外轮廓最大纵向长度。底盘**网格**实测 x∈[−0.2500, **+0.2520**]；相机最前 0.2495、前万向轮 0.225 均不占优 |
| robot_height（附带，契约未强制） | **≈0.30 m** | 载荷板顶 z≈0.24 + base_link 抬高 0.0625 |
| wheel_radius | **0.0625 m** | 驱动轮有效滚动半径（左右同径） |
| wheel_separation | **0.35 m** | 左右驱动轮滚动平面间距（轮心 y=±0.175） |
| base_footprint → base_link | **xyz = (0, 0, 0.0625)**，rpy = (0,0,0) | 抬高一个轮半径，使轮子落于 z=0 |

### 1.1 物理参数（质量 / 惯量 / 质心）

**当前启用配置**：2D 雷达 + RGB-D 相机 + IMU 开；3D 雷达 / 双目 / GPS 关。

| 部件 | link（**改名后**） | 质量 (kg) | 位置（base_link 系） |
|---|---|---|---|
| 底盘 | `base_link` | **15.0** | (0, 0, 0) |
| 载物台 | `payload_platform_link` | 2.5 | (0, 0, 0.230) |
| 左驱动轮 | `left_wheel_link` | 1.5 | (0, +0.175, 0) |
| 右驱动轮 | `right_wheel_link` | 1.5 | (0, −0.175, 0) |
| 万向轮转向座 ×4 | `*_caster_swivel_link` | 0.05 ×4 = 0.20 | (±0.20, ±0.14, 0) |
| 万向轮轮体 ×4 | `*_caster_wheel_link` | 0.15 ×4 = 0.60 | (±0.20, ±0.14, −0.036) |
| 2D 雷达 | `laser_link` | 0.17 | (0.20, 0, 0.18) |
| RGB-D 相机 | `camera_link` | 0.072 | (0.237, 0, 0.125) |
| IMU | `imu_link` | 0.05 | (0, 0, 0.08) |
| **总质量** | | **21.592 kg** | |

| 派生量 | 值 |
|---|---|
| 合成质心（base_link 系） | **(0.0024, 0.000, 0.0277) m** |
| 质心距地高度 | **0.0902 m**（0.0625 + 0.0277） |
| `base_link` 惯量 | ixx **0.2281** / iyy **0.3406** / izz **0.5125**（ixy=ixz=iyz=0） |

> `base_link` 惯量按 15 kg、0.50×0.40×0.15 实心长方体解析式计算，URDF 注释中已写明公式，可复核。

**碰撞体清单**：

| 部件 | 类型 | 尺寸 |
|---|---|---|
| 底盘 | box | 0.50 × 0.40 × 0.15 m |
| 驱动轮 ×2 | cylinder | r = 0.0625 m，l = 0.040 m |
| 万向轮轮体 ×4 | cylinder | r = 0.025 m，l = 0.020 m |
| 载物台顶板 | box | 0.440 × 0.320 × 0.020 m |
| 万向轮转向座、各传感器 | **无碰撞体** | （仅有 visual） |

### footprint（base_footprint 下二维顶点）

```
[[0.252, -0.20], [0.252, 0.20], [-0.25, 0.20], [-0.25, -0.20]]
```

- **4 点、逆时针、不自交、不重复首点**，覆盖整车水平投影
- 前缘 **+0.252** 与 `robot_length = 0.502` 一致；后缘 −0.25；横向 ±0.20
- **不含导航安全余量** —— 请 A 单独配置 inflation
- Nav2 配置片段示例（多边形 footprint）：

```yaml
footprint: "[[0.252, -0.20], [0.252, 0.20], [-0.25, 0.20], [-0.25, -0.20]]"
```

**数值一致性提醒**：`wheel_radius=0.0625`、`wheel_separation=0.35` 在模型文件与驱动配置中各写了一份：
- `rlai_description/urdf/robot.urdf.xacro`

```xml
<xacro:rlai_wheels wheel_separation="0.35" wheel_radius="0.0625"/>
```

- `rlai_control/config/controllers.yaml`（第 25–26 行）

```yaml
wheel_separation: 0.35    # meters (between wheel centrelines)
wheel_radius:     0.0625  # meters
```

**当前两处一致 ✅**，改动任一必须同步另一处。

---

## 2. 传感器安装位姿（TF 固定边）— **命名已落地**

四元数无特殊说明时，rpy 均为 (0, 0, 0)。

| 父 → 子（**已落地为契约冻结名**） | **xyz (m)** | **rpy (rad)** | 说明 |
|---|---|---|---|
| `base_footprint` → `base_link` | (0, 0, **0.0625**) | (0, 0, 0) | 车体原点相对平面底盘投影的高度 |
| `base_link` → `laser_link` | (**0.20, 0, 0.18**) | (0, 0, 0) | 2D 雷达安装位姿 |
| `base_link` → `camera_link` | (**0.237, 0, 0.125**) | (0, 0, 0) | 相机机械位姿 |
| `camera_link` → `camera_optical_frame` | (0, 0, 0) | (**−π/2, 0, −π/2**) | 光学坐标：z 向前、x 向右、y 向下 |

**另附（契约未列入主链，供 A 知悉）**：

| 边 | xyz | 说明 |
|---|---|---|
| `base_link` → `imu_link` | (0, 0, 0.08) | IMU 安装位姿 |
| `camera_link` → `camera_depth_optical_frame` | (0, 0, 0) | 深度流光学帧（与 RGB 光学帧同姿态） |

### ✅ 改名已完成（2026-10-03）

| 契约冻结名 | rbot 原模型名 | 状态 |
|---|---|---|
| `laser_link` | `lidar_2d_link` | ✅ **已改** |
| `camera_link` | `depth_camera_link` | ✅ **已改** |
| `camera_optical_frame` | `depth_camera_rgb_optical_frame` | ✅ **已改** |
| `camera_depth_optical_frame` | `depth_camera_depth_optical_frame` | ✅ **已改** |

**改动文件（9 个，已 commit）**：

```
src/localization/rlai_localization/config/amcl.yaml
src/mapping/rlai_mapping/rviz/mapping.rviz
src/navigation/rlai_navigation/rviz/navigation.rviz
src/perception/rlai_camera_processing/launch/camera_processing.launch.py
src/robot/rlai_description/urdf/gazebo/gazebo_materials.urdf.xacro
src/robot/rlai_description/urdf/gazebo/gazebo_sensors.urdf.xacro
src/robot/rlai_description/urdf/sensors/depth_camera.urdf.xacro
src/robot/rlai_description/urdf/sensors/lidar_2d.urdf.xacro
src/simulation/rlai_gazebo/config/ros_gz_bridge.yaml
```

### 改名后实测验证（2026-10-03）

| 校验项 | 命令 | 实测结果 |
|---|---|---|
| `base_link→laser_link` | `tf2_echo base_link laser_link` | `[0.200, 0.000, 0.180]`，四元数单位 ✅ |
| `base_link→camera_link` | `tf2_echo base_link camera_link` | `[0.237, 0.000, 0.125]`，四元数单位 ✅ |
| `camera_link→camera_optical_frame` | `tf2_echo camera_link camera_optical_frame` | 平移 0，RPY `[−1.571, 0, −1.571]` ✅ |
| `/scan` 消息 frame_id | `ros2 topic echo --once /scan --field header.frame_id` | **`laser_link`** ✅ |
| `/camera/image_raw` 消息 frame_id | `ros2 topic echo --once /camera/image_raw --field header.frame_id` | **`camera_optical_frame`** ✅ |

> **关键提示（供 A 排错）**：TF 树与消息 `header.frame_id` 是**两个独立来源** —— TF 来自 `robot_state_publisher` 解析 URDF，frame_id 来自 Gazebo 传感器插件的 `<gz_frame_id>`。
> 改名后必须**两边都验**：只验 TF 会出现"TF 是新名、消息是旧名"，表现为 Rviz 报 `Message Filter dropping message: frame xxx does not exist`，数据在发但图上看不见。
> 若 A 遇到此现象，先 `pkill -9 -f "gz sim"; pkill -9 -f "ros2 launch"; pkill -9 -f "robot_state_publisher"; pkill -9 -f "ros_gz_bridge"; pkill -9 -f "component_container"`，再**新开终端**重启。

---

## 3. 话题清单

### 3.1 Gazebo 源 → ROS 2 目标（桥接对照）

B 提供的是 **Gazebo Transport 侧**的传感器话题；A 负责用 `ros_gz_bridge` 把它们转成 **ROS 2 侧**话题。**两侧消息体系不同，不可混写。**

| Gazebo 源话题 | Gazebo 类型 | ROS 2 目标话题 | ROS 2 类型 | 方向 |
|---|---|---|---|---|
| `/scan` | `gz.msgs.LaserScan` | `/scan` | `sensor_msgs/msg/LaserScan` | GZ→ROS |
| `/imu/data_raw` | `gz.msgs.IMU` | `/imu/data_raw` | `sensor_msgs/msg/Imu` | GZ→ROS |
| `/depth_camera/image_raw` | `gz.msgs.Image` | **`/camera/image_raw`** | `sensor_msgs/msg/Image` | GZ→ROS |
| `/depth_camera/camera_info` | `gz.msgs.CameraInfo` | **`/camera/camera_info`** | `sensor_msgs/msg/CameraInfo` | GZ→ROS |
| `/depth_camera/depth` | `gz.msgs.Image` | **`/camera/depth`** | `sensor_msgs/msg/Image` | GZ→ROS |
| `/clock` | `gz.msgs.Clock` | `/clock` | `rosgraph_msgs/msg/Clock` | GZ→ROS |
| `/gazebo/ground_truth/odom` | `gz.msgs.Odometry` | `/gazebo/ground_truth/odom` | `nav_msgs/msg/Odometry` | GZ→ROS |

链路示意：

```
Gazebo Sensor → Gazebo topic (gz.msgs.*) → ros_gz_bridge → ROS 2 topic (sensor_msgs/*) → Nav2 / perception
```

> **改名策略说明（A 可复用）**：`ros_gz_bridge.yaml` 中 `gz_topic_name` 与 `ros_topic_name` **允许不同**。
> 本次只改了 ROS 侧目标名，Gazebo 侧 `<topic>` 未动 —— 改动面最小、回滚最容易。**不要**为了统一命名去改 Gazebo 传感器配置。

### 3.2 ROS 2 侧话题属性（实测）

| ROS 2 话题（**改名后**） | 类型 | 配置频率（仿真） | 实测频率（墙钟） | 备注 |
|---|---|---|---|---|
| `/scan` | LaserScan | 15 Hz | **2.53 Hz**（改名后复测 2.13 Hz） | 720 采样、FOV ±π、量程 0.30–25 m、噪声 σ=0.01 m |
| `/camera/image_raw` | Image | 30 Hz | **1.80 Hz**（改名后复测 ≈1.2 Hz） | 640×480、HFoV 1.5184 rad、**encoding = `rgb8`** |
| `/camera/camera_info` | CameraInfo | 30 Hz | 随图像流（未单独测） | 标定随分辨率自动生成 |
| `/camera/depth` | Image | 30 Hz | 随图像流（未单独测） | **encoding = `32FC1`**、near 0.1 / far 10 m |
| `/imu/data_raw` | Imu | 200 Hz | 未在本工况单独测 | gyro σ=0.0003394 rad/s/√Hz；accel σ=0.004 m/s²/√Hz |
| `/imu/data` | Imu | 200 Hz（转发） | **31.7 Hz** | `imu_filter_madgwick` 输出，**EKF 的 `imu0` 输入** |
| `/joint_states` | JointState | 100 Hz | **15.0 Hz** | 由 `joint_state_broadcaster` 发布，**不经过 bridge** |
| `/odometry/filtered` | Odometry | 30 Hz | **5.08 Hz** | EKF 输出，建议作为 `/odom` 来源 |

**A 桥接后的目标话题名（契约冻结名）**：`/scan`、`/camera/image_raw`、`/camera/camera_info` —— **已全部落地**。

**已实测确认的属性**：

| 项 | 结果 |
|---|---|
| `/scan` 消息类型 | `sensor_msgs/msg/LaserScan` ✅ 正确 |
| `/scan` 发布者数量 | **1 个**（`ros_gz_bridge`）✅ 无重复发布 |
| `/scan` QoS | **RELIABLE**, durability VOLATILE |
| `/scan` 抖动 | std dev **0.017 s**（min 0.360 / max 0.449 s）✅ 全场最稳 |
| RGB 图 encoding | **`rgb8`** ✅（按 RGB 顺序解码，红绿通道不互换） |
| 深度图 encoding | **`32FC1`** ✅（ROS 端实测值，非 Gazebo 的 `R_FLOAT32` pixel format） |
| `/imu/data` 发布者 | `imu_filter_madgwick` ✅ 已确认存在且连续 |
| `/scan` frame_id | **`laser_link`** ✅（2026-10-03 复测） |
| `/camera/image_raw` frame_id | **`camera_optical_frame`** ✅（2026-10-03 复测） |

**关于 QoS（重要，请勿误判）**：`/scan` 实测为 **RELIABLE** 发布；订阅端无论用 RELIABLE 还是 BEST_EFFORT **均可收到**（向下兼容）。**只有"发布 BEST_EFFORT + 订阅 RELIABLE"才会收不到**，当前不是该情况，**不会通信失败**。契约基线写的是 BE depth 5，方向安全，无需改桥接。

**关于 encoding 口径**：`R_FLOAT32` 是 **Gazebo 的 pixel format**，属于 Gazebo 消息体系；ROS 端 `sensor_msgs/Image.encoding` 的实测值是 **`32FC1`**。A 解码深度图请用 `32FC1`。

---

## 4. 里程计与时钟（B 交付来源说明，供 A 配置）

### 里程计链路（契约第 3 节红线：禁止用场景真值代替估计）

rbot 中存在**三条**与里程计相关的话题，**性质不同，A 必须区分**：

| 话题 | 性质 | 是否可用 |
|---|---|---|
| `/gazebo/ground_truth/odom` | **仿真真值** | ❌ **契约明确禁止**用于定位/里程计 |
| `/diff_drive_controller/odom`（50 Hz） | **轮速推算** | ✅ 作为 EKF 输入（`odom0`） |
| `/odometry/filtered`（30 Hz 配置 / **5.08 Hz 实测**） | **EKF 融合输出** | ✅ **建议作为 `/odom` 来源** |

```
/gazebo/ground_truth/odom   ❌ 不参与控制（真值）
/diff_drive_controller/odom ─┐
                             ├→ EKF (ekf_node) → /odometry/filtered → 推荐给导航
/imu/data (madgwick) ────────┘
```

**链路**：`/diff_drive_controller/odom` + `/imu/data`（`imu_filter_madgwick` 滤波后）→ **EKF**（`ekf_node`）→ 发布 `/odometry/filtered` + `odom→base_footprint` TF

**已验证**：
- `/imu/data` 实测 **31.7 Hz**，发布者 `imu_filter_madgwick` ✅ —— 证明 `imu_filter_madgwick` 在跑，`/imu/data_raw → /imu/data` 转换正常；
- `/odometry/filtered` 实测 **5.08 Hz** ✅ —— EKF 输出正常；
- **结论：EKF 双输入（轮速 + IMU）链路已验证完整，未退化成单输入。**

> ⚠️ 注意：仅凭 `/odometry/filtered` 有数据**不足以**证明双输入正常（EKF 单输入也会有输出）。本表是在**实测 `/imu/data` 存在且连续**之后才下的结论。

**`/odom` 的落地方式（已冻结为一种，请 A 按此执行）**：

> **统一在 launch 中将 `/odometry/filtered` remap 为契约话题 `/odom`，不额外启动 republisher 节点。**

理由：republisher 会多出一个节点和一个话题，带来额外延迟与**重复发布风险**；本项目强调"唯一发布者"，remap 更干净。
`/odom` 的 `header.frame_id = odom`、`child_frame_id = base_footprint`。

**驱动配置实值**（`rlai_control/config/controllers.yaml`）：

| 参数 | 值 |
|---|---|
| `update_rate` | 100 Hz（**也是 `/joint_states` 的发布基准**） |
| `odom_publish_rate` | 50 Hz（仅作用于 `/diff_drive_controller/odom`） |
| `odom_frame_id` / `base_frame_id` | `odom` / `base_footprint` |
| `enable_odom_tf` | **false**（由 EKF 唯一发布 `odom→base_footprint`，避免重复） |

### 轮关节来源（契约要求注明）

`/joint_states`（sensor_msgs/msg/JointState，**实测 15.0 Hz**，配置基准 100 Hz）由 **ros2_control 的 `joint_state_broadcaster` 唯一发布**。
rbot 的 `ros_gz_bridge.yaml` **故意不桥接** `/joint_states`（该文件第 2 行注释注明"ros2_control is the sole publisher"）。**A 请勿再桥接一份。**

> **更正说明**：`/joint_states` 的配置基准是 `controller_manager` 的 `update_rate: 100`，**不是** `odom_publish_rate: 50`（后者只管 `/diff_drive_controller/odom`）。

### TF 发布责任（契约 TF TABLE）

| 边 | 责任 |
|---|---|
| `base_footprint→base_link`、`base_link→laser_link`、`base_link→camera_link`、`camera_link→camera_optical_frame` | **B 定义固定关节**；由唯一 `robot_state_publisher`（C 启动）发布 |
| `odom→base_footprint` | **A**（EKF 或 A 指定唯一来源） |
| `map→odom` | **A**（SLAM 或 AMCL，互斥） |

---

## 5. 仿真性能与频率（概念必须分清）

### 5.1 三个不同的"频率"

| 概念 | 含义 | 怎么得到 |
|---|---|---|
| **Configured simulation-time rate**（配置仿真频率） | URDF / config 里写的 `<update_rate>`，**按仿真时间计** | 读模型文件 |
| **Observed wall-clock rate**（现实墙钟接收频率） | 现实中每秒收到几条消息 | `ros2 topic hz` 实测 |
| **Effective simulation-time rate**（折算仿真频率） | 折算回仿真时间后的真实频率 = 墙钟 ÷ RTF | 计算得出 |

**Gazebo 的 `<update_rate>` 是仿真时间频率。** 当 RTF < 1（仿真跑得比现实慢）时：

```
墙钟频率 ≈ 配置频率 × RTF
```

**这是正常的等比下降，不是掉频。** 机器人自己在仿真时间里也只走了那么久，所以 SLAM / Nav2 看到的数据密度在仿真时间里是完整的。

### 5.2 仿真实时率 RTF（独立实测）

RTF **必须独立测量**，不能由话题频率反推（那是循环论证）。本表用 `/clock` 直接测：

```bash
S0=$(ros2 topic echo --once /clock | tr -d ' ' | grep -m1 '^sec:' | cut -d: -f2); T0=$(date +%s%N); sleep 10; S1=$(ros2 topic echo --once /clock | tr -d ' ' | grep -m1 '^sec:' | cut -d: -f2); T1=$(date +%s%N); echo "sim=$(($S1-$S0))s real=$(echo "scale=2;($T1-$T0)/1000000000"|bc)s RTF=$(echo "scale=3;($S1-$S0)*1000000000/($T1-$T0)"|bc)"
```

| 工况 | RTF |
|---|---|
| headless + `camera_processing_enabled:=true`（默认） | **0.129** |
| headless + `camera_processing_enabled:=false` | **0.197** |

> 关掉 `depth_image_proc::PointCloudXyzNode`（640×480 → 点云，约 30.7 万点/帧）让 RTF 提升 **53%**，证明点云转换是主要 CPU 消耗之一。

**本表 5.3 节的频率实测于 RTF ≈ 0.197 的工况。** 测量工具本身占用 CPU，实际 RTF 可能略高于该值。
RTF 在不同 session 间波动明显（已观测 0.129 / 0.197 / 0.37），**因此每个频率都必须同时标注"墙钟实测值 + 当时 RTF"，单给一个数字不可信。**

### 5.3 实测结果

| 话题 | 配置（仿真 Hz） | 实测（墙钟 Hz） | 折算（仿真 Hz） | 达成率 | 抖动 std dev |
|---|---|---|---|---|---|
| `/scan` | 15 | **2.53** | 12.8 | **85%** ✅ | 0.017 s |
| `/odometry/filtered` | 30 | **5.08** | 25.8 | **86%** ✅ | 0.017 s |
| `/imu/data` | 200 | **31.7** | 161 | **80%** ✅ | 0.027 s |
| `/joint_states` | 100 | **15.0** | 76 | **76%** ⚠️ | 0.026 s |
| `/camera/image_raw`（原 `/depth_camera/image_raw`） | 30 | **1.80** | 9.1 | **30%** ❌ | 0.19–2.85 s |

### 5.4 结论

> **掉频的只有相机一个。**

- **数值型链路**（雷达、EKF、IMU、轮关节）达成率 **76%–86%**，属于"整体仿真跑慢导致的等比下降"，**没有单独掉队**。
- **图像型链路**（相机）只有 **30%**，是在 RTF 之外的**额外损失**，瓶颈是 `LIBGL_ALWAYS_SOFTWARE=1` 下逐帧软件渲染 RGB + 深度。
- 已排除桥接传输：640×480 RGB8 每帧 921 KB，按 1.8 Hz 计实际仅约 1.7 MB/s，远未到传输上限。

**对 A 的影响（重要更正）**：
- `/scan` 达成 85%、**抖动 std dev 仅 0.017 s**，是全场最稳的话题。**雷达数据在仿真时间里接近配置值且均匀，SLAM 建图与 Nav2 避障不受影响。**
- `/odometry/filtered` 达成 86%、抖动 0.017 s，定位平滑度不受影响。
- **此前"激光稀疏导致 SLAM 精度下降"的判断已作废**，请勿沿用。

**对 B 的影响**：红绿灯识别必须按 **约 9 Hz 仿真帧率**、且**帧间隔不均匀**（最长 0.56 仿真秒，0.5 m/s 时车已移动 28 cm）来设计，不能假设 30 Hz 或均匀间隔。

**关于契约**：契约第 7 节将「配置频率」列为"**可后续细化**"项（**非冻结项**）；第 8 节验收只要求"**实测频率有记录**"。本表已满足验收。**是否下调基线或加强环境，建议 A/B/C 共同决策。**

**已验证的缓解措施**：
- ✅ `headless:=true`（去掉 GUI 渲染）
- ✅ `camera_processing_enabled:=false`（RTF +53%）

**待评估的缓解方向**：
- 相机降分辨率（640×480 → 320×240）
- 相机 `update_rate` 30 → 10 Hz（使其稳定在可达成区间，减少抖动）
- 关闭深度流，仅保留 RGB
- 精简世界模型（减少物件/多边形）
- 改用裸机或更强算力环境

---

## 6. 核对方式（A 可独立复现验证）

```bash
# 展开模型，核对全部几何/位姿
cd ~/rbot
xacro install/rlai_description/share/rlai_description/urdf/robot.urdf.xacro sim_mode:=gazebo > /tmp/rlai.urdf
grep -nE "wheel_separation|wheel_radius|box size=|origin xyz=|<mass|<inertia" /tmp/rlai.urdf | head -40

# 运行时读 TF（最权威）— 用改名后的冻结名
ros2 run tf2_ros tf2_echo base_footprint base_link          # 应打印 0 0 0.0625
ros2 run tf2_ros tf2_echo base_link laser_link              # 应打印 0.20 0.00 0.18
ros2 run tf2_ros tf2_echo base_link camera_link             # 应打印 0.237 0.00 0.125
ros2 run tf2_ros tf2_echo camera_link camera_optical_frame  # 应打印 RPY -1.571 0 -1.571

# 消息 frame_id（改名后必须与 TF 同名）
ros2 topic echo --once /scan --field header.frame_id               # 应为 laser_link
ros2 topic echo --once /camera/image_raw --field header.frame_id   # 应为 camera_optical_frame

# 话题类型 / QoS / 发布者
ros2 topic info -v /scan
ros2 topic info -v /imu/data

# encoding（ROS 端真实值）
ros2 topic echo --once /camera/image_raw --field encoding   # 应为 rgb8
ros2 topic echo --once /camera/depth --field encoding       # 应为 32FC1

# 频率（注意：ros2 CLI 启动有 3~5 秒静默期，请等 average rate 出现后再 Ctrl+C）
ros2 topic hz /scan
ros2 topic hz /odometry/filtered

# RTF 独立实测（见 5.2 节命令）
```

> 建议加 `timeout --signal=INT 秒数` 前缀让命令自动退出，例如
> `timeout --signal=INT 12 ros2 run tf2_ros tf2_echo base_link laser_link`。

**验证结论**：
- 几何与位姿经「URDF 声明 + STL 网格包围盒」双向交叉核对，误差 ≤2 mm；
- 质量/惯量/质心由 URDF 逐 link 提取后求和，惯量公式已在 URDF 注释中给出；
- TF 位姿经 `tf2_echo` 运行时实测，与 URDF 声明一致；
- **消息 `header.frame_id` 与 TF 树同名，已双向验证**；
- **仿真实时率（RTF）由 Gazebo `/clock` 独立实测**；
- **ROS 话题墙钟接收频率由 `ros2 topic hz` 实测**；
- 两者概念不同，不可互相替代。

---

## 7. 交付清单与状态

| 交付项 | 状态 |
|---|---|
| 整车几何（width / length / footprint） | ✅ 已交付（实值） |
| **物理参数（质量 / 惯量 / 质心）** | ✅ 已交付（实值，见 1.1） |
| 驱动几何（wheel_radius / wheel_separation） | ✅ 已交付（实值） |
| 传感器安装位姿（laser / camera / optical） | ✅ 已交付（实值 + `tf2_echo` 实测） |
| 话题、类型、**Gazebo↔ROS 桥接对照** | ✅ 已交付 |
| **frame 名** | ✅ **已按冻结契约改名并实测验证** |
| **相机话题名** | ✅ **已改名为 `/camera/*` 并实测有发布** |
| 配置频率 + 实测频率 + **RTF** | ✅ 已交付（5 项实测 + RTF 独立实测） |
| 消息类型 / QoS / **encoding（rgb8 / 32FC1）** | ✅ 已实测确认 |
| EKF 双输入链路 | ✅ **已实测验证**（`/imu/data` 存在且连续） |
| 模型文件与版本 | ✅ 已交付（基线 `47af3fc` + 改名 commit ed50809） |
| 驱动/传感器配置 | ✅ 已交付（`controllers.yaml` 关键值） |
| base_footprint→base_link 高度 | ✅ 0.0625 m |
| joint_states 来源说明 | ✅ 已交付（ros2_control 唯一发布） |

### 遗留事项

| 项 | 状态 |
|---|---|
| 4 条 TF frame 改名 | ✅ **已完成并验证** |
| 相机话题改名 | ✅ **已完成并验证** |
| `/camera/camera_info`、`/camera/depth` 单独频率 | ⚪ 未测（**契约未要求**，不影响联调） |

### 🔑 关于模型版本哈希（A 请以此为准）

- **基线**：git `47af3fc3780bd582837f48ce3785d3d68834a1b7`
- **本次交付**：git **ed50809**（在基线之上 1 个 commit，仅含命名落地改动，共 9 个文件）

**A 请务必以本文档文首记录的 hash 检出模型**，不要用旧的 `47af3fc`——旧版本里是 `lidar_2d_link` / `/depth_camera/*`，与本文档及契约不符。

流程已按规范执行：

```
B 完成改名 → 完整测试（TF + frame_id + 话题发布）→ git commit → hash 填入本表 → 交给 A → A 复现 → A 签核
```

### 待 A 确认事项（3 项，签核前请回复）

1. `robot_length = 0.502` / footprint 前缘 `+0.252` 是否与 A 的 Nav2 配置一致
2. `/odom` 是否按第 4 节所述，采用 **launch remap** 方式取 `/odometry/filtered`（而非 republisher）
3. 频率基线是否需共同调整（当前建议：数值型维持配置值；相机按约 9 Hz 仿真帧率设计 B 的视觉算法）

### 文档状态流转

- **当前：正式冻结 v1.0（待 A 复现并签核）**
- v0.9 遗留项已全部关闭：
  - ✅ frame 名完成改名 + 实测验证
  - ✅ camera topic 名完成改名 + 实测验证
  - ✅ 质量/惯量补齐
  - ✅ Gazebo/ROS topic 表拆开
  - ✅ RTF/频率重新解释
  - ✅ EKF 双输入实测确认
  - ✅ 重新 commit 并更新 hash
- **剩余**：A 复现并签核上述 3 项确认事项
