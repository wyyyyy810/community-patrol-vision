# B 任务清单与接口对照（依据《A/B/C 最小接口契约 v0.1》）

> 依据文件：
> - `INTERFACES.md` —— **冻结版 v0.1**（冻结日期 2026-09-22），**以这份为准**
> - `冻结接口.docx` —— 同一份契约的草案版本，内容更宽松，缺状态精确定义与验收表

---

## 一、两份文档的关系

| 项 | 冻结接口.docx | INTERFACES.md |
|---|---|---|
| 性质 | 草案（"待冻结的 v0.1 接口契约"） | **冻结版 v0.1** |
| 严格程度 | 表格列名宽泛（"最小表达方式"） | 明确标注 **FROZEN / NOT VERIFIED** |
| 独有内容 | — | 五种状态的精确定义、run_id/task_id 规则、感知新鲜度规则、8 项验收用例、变更流程 |
| 结论 | 参考其"为什么这么设计" | **实现时以它为准** |

两份文档都明确写了：**当前只有文档，没有 `.msg` / `.srv` / `.action`，也没有任何算法代码；接口契约已冻结，但实现与验证均 NOT VERIFIED。**

---

## 二、"冻结接口"是什么意思（你问的第三个问题）

"冻结"= **这份接口契约定稿了，谁都不能单方面改**。具体冻结了什么：

1. **名字冻结**：topic / service / action 的名称固定（如 `/perception/results`、`/cmd_vel`）
2. **类型冻结**：消息类型固定（`sensor_msgs/msg/Image`、`std_msgs/msg/Bool`……）
3. **字段冻结**：自定义消息的字段**顺序**都冻结（如 PerceptionResult 的 8 个字段先后不能动）
4. **语义冻结**：枚举值含义固定（`RED/YELLOW/GREEN/UNKNOWN`）、状态值固定（EXECUTING=1…CANCELED=5）
5. **坐标冻结**：TF 父子关系、`frame_id` 命名、坐标轴方向（车体 x前/y左/z上；光学 z前/x右/y下）
6. **权限冻结**：谁负责什么——**A 唯一速度出口、C 唯一任务调度、B 不控车**

**注意"冻结"≠"已经做好"**：冻结只是"后续实现的基准"。要改冻结项，必须先说明原因 + 说明对 A/B/C 上下游的影响 + 升级版本号 + 三方同步，不允许任何一方偷偷改 topic 或字段。

**你要做的事一句话总结**：**按冻结的名字/类型/字段/坐标，把 B 负责的模型、参数、识别节点做出来，并给出可复现的验证证据。**

---

## 三、角色分工（先看清边界，避免做错方向）

| 角色 | 负责 |
|---|---|
| **A** | 导航、Gazebo/ROS 桥接、**最终速度仲裁（唯一 /cmd_vel 出口）**、建图定位 |
| **B（你）** | **机器人模型、传感器定义、图像识别** |
| **C** | 任务调度、日志、统一启动、决策与展示 |

⚠️ **重点澄清**：你问的"前后左右转向控制"**不是 B 的活**。转向/速度控制全在 A 手里——契约明确规定 `/cmd_vel` 只能由 A 的仲裁节点发布，B 不得绕过、不得自己发速度。B 在"运动"这件事上只提供**两个几何参数 + 轮关节来源说明**，让 A 去配置底盘。

---

## 四、接口全清单（区分"你负责的"和"别碰的"）

### 4.1 属于 B 的接口（4 项，全部要做）

| 接口 | 方向 | 类型 | 你要做什么 |
|---|---|---|---|
| **模型与参数交付表** | B → A | 文档 + 模型文件 | 交付真实尺寸/footprint/传感器位姿/topic/frame/频率 |
| `/perception/set_parameters_atomically` | C → B | `rcl_interfaces/srv/SetParametersAtomically` | 接收 run_id / task_id，**原子**切换；失败则不切换 |
| `/perception/results` | B → C | `community_interfaces/msg/PerceptionResult`（**待实现**） | 发布识别结果（红绿灯/人/车牌） |
| **TF（固定边）** | B 定义 → robot_state_publisher 发布 | TF | 定义 4 条固定变换：`base_footprint→base_link`、`base_link→laser_link`、`base_link→camera_link`、`camera_link→camera_optical_frame` |

**B 的节点名冻结为 `/perception`**，启动上下文为空，没有 run_id/task_id 时不发布任务结果。

### 4.2 不属于 B 的（看到别动）

| 接口 | 归属 A | 说明 |
|---|---|---|
| `/cmd_vel`（`geometry_msgs/msg/Twist`，20Hz） | A | 唯一速度出口；B 绝不发布 |
| `/scan`（LaserScan，10Hz） | A 桥接 B 的雷达后发布 | **B 提供传感器源，A 负责桥接发布**，不能两边各发一份 |
| `/camera/image_raw`、`/camera/camera_info`（15Hz） | A 桥接 B 的相机后发布 | 同上，B 出源、A 桥接 |
| `/odom`、`/clock`、`map→odom` | A | |
| `/navigation/task`、`/navigation/set_paused`、`/motion_permission` | A / C | |

### 4.3 PerceptionResult 字段（顺序冻结，一个字都不能改）

| 顺序 | 字段 | 类型 | 含义 |
|---|---|---|---|
| 1 | run_id | string | C 下发的轮次 |
| 2 | task_id | string | C 下发的任务 |
| 3 | header | std_msgs/Header | stamp=原图采集 ROS 时间；frame_id=`camera_optical_frame` |
| 4 | class_name | string | `traffic_light` / `person` / `license_plate` |
| 5 | result | string | 见下面枚举 |
| 6 | confidence | float32 | **[0,1]** 有限数 |
| 7 | bbox | `vision_msgs/BoundingBox2D` | 原始像素坐标；轴对齐，theta=0 |
| 8 | target_id | string | B 的目标关联 ID，未知为空 |

**result 枚举（冻结）**：
- `traffic_light` → `RED` / `YELLOW` / `GREEN` / `UNKNOWN`
- `person` → `COMMUNITY` / `NON_COMMUNITY` / `UNKNOWN`
- `license_plate` → 成功为 OCR 字符，失败为空字符串

**关键规则（很多人会踩）**：
- **一条消息 = 一幅原图上的一个目标**；一张图可发多条；没检测到可以不发
- **"没有消息"绝不等于"绿灯"或"没人"**——C 会按新鲜度超时处理
- 车牌的 confidence 必须是**字符识别置信度**，不能用检测框置信度冒充；没有就输出 UNKNOWN + 0，**不许编造高分**
- 处理图像时就要**绑定上下文**，不能在推理完成时补当前的 run_id；上下文切换时的旧帧要么保留旧 ID、要么丢弃
- `target_id` 为空不能作为跨帧去重依据

---

## 五、模型与参数交付表（已按 rbot 模型实值填好）

### 5.1 这些数值是怎么量出来的（方法，可复现）

**没有一个是猜的**，全部来自 rbot 模型文件的原始声明。对应关系：

| 要填的数值 | 去哪个文件找 | 关键行 |
|---|---|---|
| 底盘尺寸 / 碰撞盒 / 质量 | `src/robot/rlai_description/urdf/base/base.urdf.xacro` | `<box size="0.50 0.40 0.15"/>` |
| 轮半径 / 轮距 | `.../base/wheels.urdf.xacro` + `.../robot.urdf.xacro`(第 45 行) | `wheel_separation="0.35" wheel_radius="0.0625"` |
| 万向轮位置 | `.../base/wheels.urdf.xacro`(第 132–135 行) | `x="±0.20" y="±0.14"` |
| 雷达位姿 | `.../sensors/lidar_2d.urdf.xacro` + `robot.urdf.xacro`(第 54–57 行) | `xyz="0.20 0.0 0.18"` |
| 相机位姿 | `.../sensors/depth_camera.urdf.xacro` + `robot.urdf.xacro`(第 69–72 行) | `xyz="0.237 0.0 0.125"` |
| 传感器频率/话题/frame | `.../gazebo/gazebo_sensors.urdf.xacro` | `<update_rate>` / `<topic>` / `<gz_frame_id>` |
| ROS 侧话题名 | `src/simulation/rlai_gazebo/config/ros_gz_bridge.yaml` | — |

**一键核对命令**（在 Ubuntu 的 `~/rbot` 下跑，把输出跟下表逐项比）：

```bash
xacro install/rlai_description/share/rlai_description/urdf/robot.urdf.xacro sim_mode:=gazebo > /tmp/rlai.urdf
grep -nE "wheel_separation|wheel_radius|box size|origin xyz|update_rate|<topic>" /tmp/rlai.urdf
```

### 5.2 几何参数（实值，已消灭 TBD）

| 字段 | 冻结定义 | **实值** | 依据 / 算法 |
|---|---|---|---|
| robot_width | 整车碰撞外轮廓最大横向宽度（含轮子和突出部分） | **0.40 m** | 底盘碰撞盒宽 0.40（y=±0.20）；驱动轮外缘仅 ±0.195、万向轮 ±0.15，都更窄，故取 0.40 |
| robot_length | 整车碰撞外轮廓最大纵向长度 | **0.502 m**（✅ 已定，B 决策 2026-09-27） | 底盘**网格**实测 x∈[−0.2500, **+0.2520**] → 严格覆盖整车水平投影，符合契约"覆盖整车水平投影"字面要求。**A 的 Nav2 footprint 必须与此一致**（原碰撞盒值 0.500 为参考，未采用） |
| wheel_radius | 驱动轮有效滚动半径（不等径分左右） | **0.0625 m**（左右同径） | `wheel_radius="0.0625"` |
| wheel_separation | 左右驱动轮滚动平面间距 | **0.35 m** | `wheel_separation="0.35"`（轮心在 y=±0.175） |
| footprint | base_footprint 下二维顶点，逆时针、不自交、不重复首点 | **`[[0.252,-0.20],[0.252,0.20],[-0.25,0.20],[-0.25,-0.20]]`** | 与 robot_length=0.502 保持一致：前缘 x=+0.252（网格实测值），后缘 x=−0.25；4 点、逆时针、无重复首点 |
| base_footprint→base_link | 抬高量 | **0.0625 m**（rpy 全 0） | 抬一个轮半径，让轮子正好落在地面 |
| robot_height（附带，非契约必填） | 离地最大高度 | ≈**0.30 m** | 载荷板顶 z≈0.24 + base_link 抬高 0.0625 ≈ 0.30 |

**footprint 为什么就是这个矩形**：驱动轮横向只到 ±0.195、纵向 ±0.0625；万向轮到 (±0.20, ±0.14)；相机到 x=0.2495；载荷板 0.44×0.32 更小——**全部落在底盘网格的实际范围（前 +0.252 / 后 −0.25 × ±0.20）里面**，所以最紧的凸多边形就是底盘外框本身。**前缘取 +0.252（网格实测），与 robot_length=0.502 一致**。**不含导航安全余量**（A 自己加 inflation）。

### 5.3 传感器与 TF 位姿（实值）

| 变换 | 冻结定义 | **实值** | 契约要求的 frame 名 | 是否需改 |
|---|---|---|---|---|
| base_footprint→base_link | 固定 | xyz=(0,0,**0.0625**), rpy=(0,0,0) | 同名 | 否 |
| laser_pose | base_link→laser_link 的 xyz+rpy | xyz=(**0.20, 0, 0.18**), rpy=(0,0,0) | 子 frame 必须叫 **`laser_link`** | **要改名**（rbot 现在叫 `lidar_2d_link`） |
| camera_pose | base_link→camera_link 的 xyz+rpy | xyz=(**0.237, 0, 0.125**), rpy=(0,0,0) | 子 frame 必须叫 **`camera_link`** | **要改名**（rbot 现在叫 `depth_camera_link`） |
| camera→optical | camera_link→camera_optical_frame | xyz=(0,0,0), rpy=(**−π/2, 0, −π/2**) | 子 frame 必须叫 **`camera_optical_frame`** | **要改名**（rbot 现在叫 `depth_camera_rgb_optical_frame`） |

⚠️ **修正一处旧参考值**：之前表里写 "camera_pose rbot ≈ (0.22, 0, 0.18)" 是**错的**——模型里实际是 **x=0.237、z=0.125**（前脸与底盘前缘 0.25 齐平）。以本表为准。

### 5.4 话题 / frame / 频率

默认启用的传感器：**2D 雷达、RGB-D 相机、IMU**（`robot.urdf.xacro` 默认 `true`）；3D 雷达 / 双目 / GPS 默认关。

| 传感器 | ROS 话题（实值） | 消息类型 | Gazebo 源 | frame（实值） | 契约要求 | 配置频率 | 实测频率 |
|---|---|---|---|---|---|---|---|
| 2D 雷达 | `/scan` | sensor_msgs/msg/LaserScan | gz `/scan` | `lidar_2d_link` | topic 一致；frame 要 `laser_link` | 15 Hz | **5.4 Hz** |
| RGB 相机 | `/depth_camera/image_raw` | sensor_msgs/msg/Image | gz 同名 | `depth_camera_rgb_optical_frame` | `/camera/image_raw` + `camera_optical_frame` | 30 Hz | **3.3 Hz** |
| 相机内参 | `/depth_camera/camera_info` | sensor_msgs/msg/CameraInfo | gz 同名 | 同上 | `/camera/camera_info` | 30 Hz | **待实测**（随图像） |
| 深度图 | `/depth_camera/depth` | sensor_msgs/msg/Image | gz 同名 | `depth_camera_depth_optical_frame` | 契约未要求 | 30 Hz | **待实测**（随图像） |
| IMU | `/imu/data_raw` | sensor_msgs/msg/Imu | gz 同名 | `imu_link` | 契约未单列 | 200 Hz | **74 Hz** |
| 时钟 | `/clock` | rosgraph_msgs/msg/Clock | gz `/clock` | — | A 负责 | — | — |
| 轮关节 | `/joint_states` | sensor_msgs/msg/JointState | **ros2_control 发布，非桥接** | — | A 负责 | 标称 50 Hz | **19.5 Hz 实测** |
| 里程计（EKF 融合输出） | `/odometry/filtered` | nav_msgs/msg/Odometry | ros2_control 轮速 + IMU | header=`odom`，**child=`base_footprint`** | 契约话题名是 **`/odom`**，header=odom / child=base_footprint / 30 Hz | 30 Hz | **5.6 Hz 实测** |
| 固定 TF | `/tf_static` | tf2_msgs/msg/TFMessage | robot_state_publisher | — | 契约同 | **static** | static |

**⚠️ 里程计链路说明（契约第 3 节红线）**：契约明确"**禁止使用场景真值代替定位/里程计估计**"。rbot 里存在两条 odom：
- `/gazebo/ground_truth/odom`（Gazebo 真值，**契约禁止**用于定位）
- `/diff_drive_controller/odom`（轮速推算，50 Hz）→ 进 EKF 与 IMU 融合 → 输出 `/odometry/filtered` + `odom→base_footprint` TF

**结论**：`/odom` 应取 `EKF 的 /odometry/filtered`（A 负责 remap 或重映射到 `/odom`），**不是** ground_truth。B 在这一点上只需交付"轮式里程计源 = diff_drive_controller，50 Hz；IMU 源 = /imu/data，200 Hz"。

**⚠️ 两处数值必须同步（契约"不允许各维护一套"）**：`wheel_radius=0.0625`、`wheel_separation=0.35` 在**两个文件里各写了一份**——`urdf/robot.urdf.xacro`（模型）与 `rlai_control/config/controllers.yaml`(第 25–26 行，驱动配置)。**当前两处一致 ✅**，但改任何一个都要同步改另一个。

**⚠️ 编码与 QoS 待确认**：契约要求 `/camera/image_raw` 的 encoding 以合法字段为准、QoS 为 **BE depth 5**；但 `ros_gz_bridge` 默认 QoS 是 **reliable**，可能与契约冲突 → 实测时必须用 `ros2 topic info -v` 核对 QoS，用 `ros2 topic echo --once` 核对 encoding（Gazebo `RGB_INT8` 桥接后通常是 `rgb8`，但需实测确认）。

- **相机规格**：640×480、HFoV 87°（1.5184 rad）、RGB_INT8；深度 R_FLOAT32、near 0.1 / far 10 m。
- **雷达规格**：720 采样、FOV ±π、量程 0.30–25 m、噪声 σ=0.01 m。
- **轮关节说明（契约要求注明）**：轮子由 `diff_drive_controller` 驱动，`/joint_states` **由 ros2_control 的 `joint_state_broadcaster` 唯一发布**；rbot 的 `ros_gz_bridge.yaml` **故意不桥接** `/joint_states`（该文件第 2 行注释写明）。B 只声明"轮关节存在、来源是 ros2_control"，不重复发布。

### 5.5 实测频率结果（**已于 2026-09-27 完成 3 项**）

```bash
# 正确测法：一次一个，观察 10 秒后 Ctrl+C（不要用 timeout 包）
source ~/rbot/install/setup.bash
ros2 topic hz /scan                       # 配置 15 → 实测 5.4 Hz
ros2 topic hz /joint_states               # 配置 50 → 实测 19.5 Hz
ros2 topic hz /odometry/filtered          # 配置 30 → 实测 5.6 Hz
ros2 topic hz /depth_camera/image_raw     # 配置 30 → 未测（预计 ≈11）
ros2 topic hz /imu/data_raw               # 配置 200 → 未测（预计 ≈74）
```

**⚠️ 结论：仿真 RTF ≈ 0.37（只有实时的 37%），全表按 36%–39% 达成。** 详见第九节。

### 5.6 数据可信度校验（第三方独立核对，2026-09-27）

上面的数值**不是只看一个文件就下的结论**，做了三重核对：

**① 交叉核对：URDF 声明 vs 网格模型包围盒**

用 `stl_bbox.py` 直接解析 `rlai_meshes/meshes/*.stl` 的真实三角面片，算包围盒（`scale=0.001`），跟 URDF 里的手写 collision 值比对：

| 项 | URDF collision 声明 | STL 实测包围盒 | 结论 |
|---|---|---|---|
| 底盘宽度 | 0.40（Y=±0.20） | Y: ±0.2000 → **0.4000** | ✅ 一致 |
| 底盘长度 | 0.50（X=±0.25） | X: [−0.2500, **+0.2520**] → **0.5020** | ⚠️ **前缘多 2 mm** |
| 驱动轮半径 | 0.0625 | X/Y: ±0.0625 → 直径 0.125 | ✅ 一致 |
| 驱动轮厚度 | 0.040 | Z: ±0.0200 → 0.040 | ✅ 一致 |
| 载荷板 | 0.440×0.320，z∈[0.22,0.24] | X: [−0.22,+0.14], Y: ±0.16, Z: [0.15,0.24] | ⚠️ 网格含立柱（z 从 0.15 起），collision 只留顶板——**作者有意为之**，文件注释已说明"忽略立柱以免导航膨胀过大" |

**② 排除"启动文件偷偷覆盖"的风险**

读了 `gazebo.launch.py`(第 170–184 行)：xacro 展开时**只传传感器开关和 sim_mode**，**不传任何尺寸/位姿参数**。所以 `robot.urdf.xacro` 里写死的 `0.35 / 0.0625 / 0.20 / 0.237` 就是最终值，不会被覆盖。✅

**③ 未能完成的核对（如实说明）**

- **没跑过 `xacro`**：Windows 上没装 ROS，我是靠"两个独立文件互相印证"代替展开验证的。风险很低（数值都是字面量、非宏计算），但**严格来说仍属推断**。
- **频率是"配置值"不是"实测值"**：`<update_rate>` 只是 Gazebo 被要求的频率，虚拟机跑不动时会掉。**必须实测**（5.5 节命令）。这一项**目前不可信，别当结论用**。

**结论一句话**：几何/位姿/话题/frame **可信**（有交叉证据，误差 ≤2 mm）；**频率不可信**（配置 ≠ 实测）。

**已决策（2026-09-27，B）**：`robot_length` 取 **0.502**（footprint 前缘 +0.252），严格覆盖底盘网格实测范围，符合契约"覆盖整车水平投影"的字面要求。**A 的 Nav2 footprint 必须与此保持一致**（契约禁止 A/B 各维护一套数值）。差异 2 mm，对导航无实质影响。

**你自己复核的命令（Ubuntu 上跑，最权威）**：

```bash
cd ~/rbot
# 展开模型，肉眼核对上面每一个数
xacro install/rlai_description/share/rlai_description/urdf/robot.urdf.xacro sim_mode:=gazebo > /tmp/rlai.urdf
grep -nE "wheel_separation|wheel_radius|box size=|origin xyz=|update_rate|<topic>|<gz_frame_id>" /tmp/rlai.urdf | head -60

# 跑起来后，直接在运行时读 TF（比看文件更硬）
ros2 run tf2_ros tf2_echo base_link lidar_2d_link   # 应打印 0.20 0.00 0.18
ros2 run tf2_ros tf2_echo base_link depth_camera_link  # 应打印 0.237 0.00 0.125
ros2 run tf2_ros tf2_echo base_footprint base_link  # 应打印 0 0 0.0625
```

**硬性要求**：交付表必须与模型一致，**不允许 A/B 各维护一套数值**；footprint 不含导航安全余量（A 单独加）。

---

## 六、当前 rbot 模型 vs 冻结契约 的差异（必须适配的地方）

这是最容易出问题的地方——rbot 现成模型的名字和契约**对不上**：

| 项 | 冻结契约要求 | rbot 现状 | 处理 |
|---|---|---|---|
| 相机图像话题 | `/camera/image_raw` | `/depth_camera/image_raw` | 需改 remap 或改交付表并走变更流程 |
| 相机内参 | `/camera/camera_info` | `/depth_camera/camera_info` | 同上 |
| 光学 frame | `camera_optical_frame` | `depth_camera_rgb_optical_frame` | **必须改名**（frame 冻结） |
| 雷达 frame | `laser_link` | 已核实：rbot 是 `lidar_2d_link` | **必须改名** |
| 相机 frame（本体） | `camera_link` | 已核实：rbot 是 `depth_camera_link` | **必须改名** |
| 图像频率 | 15 Hz | 30 Hz | 按契约下调或走变更 |
| 速度话题类型 | `geometry_msgs/msg/Twist` | rbot 内部是 TwistStamped | 契约已说明：**A 内部适配**，B 不用管 |
| 相机数量 | 单相机即可 | rbot 默认带深度+RGB | 交付表须写清实际启用的那路 |

---

## 七、你要做的事（执行顺序）

1. ~~**确认并填写参数交付表**~~ ✅ **已完成**（见第五节）：几何参数、位姿、话题、frame、配置频率已全部填实值。**剩余缺口见第九节**（5 个实测频率 + 2 个待决策项）
2. **定模型与框架**：选定模型来源（可直接基于 rbot 的 `rlai_description` 改造），按契约改 frame 名与话题名
3. **定义 4 条固定 TF**，确保 robot_state_publisher 是唯一发布者，不与桥接重复
4. **实现 `/perception` 节点**：
   - 订阅相机图像（由 A 桥接）
   - 提供 `set_parameters_atomically` 接收 run_id/task_id
   - 做三类识别（红绿灯 / 人 / 车牌）
   - 按冻结字段顺序发布 `PerceptionResult`
5. **创建 `community_interfaces` 接口包**（`PerceptionResult.msg`）——契约目前还没有，需要有人先把 `.msg` 写出来（B 依赖它，建议 B 或 C 牵头）
6. **出验收证据**：对应契约第 8 节里 B 相关的两项——"模型参数一致、实值无 TBD" 与 "感知结果编号/时间/框一致、迟到不放行、丢图有记录"

---

## 八、B 相关验收项（来自契约第 8 节）

| 验收项 | 预期结果 |
|---|---|
| 模型参数 | 尺寸/footprint/安装位姿一致，实值无 TBD |
| 感知 | 回放带原图的三类结果，插入迟到、旧任务和丢图：编号/时间/框一致；迟到不放行；丢图明确记录 |

---

## 九、当前缺口清单（"我现在还缺哪些参数"）

对照契约第 2 节「B 必交参数」逐项审计（**2026-09-27 23:23 更新：决策项已全部拍板**）。共 **21 项已填实值、1 项可选未测**。

### ✅ 已完成：实测频率（**5/5 全部实测完成，2026-09-27 23:03**）

`/scan` 5.4、`/joint_states` 19.5、`/odometry/filtered` 5.6、`/depth_camera/image_raw` 3.3、`/imu/data_raw` 74 Hz —— **全部为实测真值，已写入交付表**。
`/depth_camera/camera_info`、`/depth_camera/depth` 随图像流（同频），可选测。

### ✅ 已完成：里程计链路确认

`/odometry/filtered` **有数据**（5.6 Hz）→ 证明 EKF 双输入（轮速 + IMU）链路完整，`/imu/data` 正常，未断链。
**`/odom` 话题源：确认取 EKF 的 `/odometry/filtered`**（A 负责 remap 到 `/odom`），**不是** ground_truth（契约第 3 节禁止）。

### ✅ 已完成：传感器属性确认（encoding / QoS / 发布者）

- **encoding = `rgb8`** ✅ 实测确认 → 视觉识别按 RGB 解码，红绿通道不错位
- **`/scan` QoS = RELIABLE, VOLATILE**；**发布者 1 个**（`ros_gz_bridge`）；类型正确 ✅ → 与契约 BE 基线方向安全，**不会通信失败**，无需改桥接

### 📊 实测频率结果（本次实测，2026-09-27 23:03）

契约第 2 节要求"**配置目标频率与实测频率分别交付**"。**实测已在 VMware 虚拟机（软件渲染）上完成 3 项**，结果如下。

> ⚠️ **重大发现：仿真 RTF ≈ 0.37，但各传感器降幅不同——相机最严重**
> 世界物理配置 `max_step_size=0.001`、`real_time_factor=1.0`（要求值）；VMware 软件渲染算力不足。
> **数值型传感器**（雷达/IMU/轮关节）达成率一致 36%–39%；**图像型传感器**（相机）仅 11%，被 640×480 渲染额外拖累。
> **影响**：`/scan` 5.4 Hz **低于契约 10 Hz**、相机 3.3 Hz **低于契约 15 Hz**，直接影响 A 的 SLAM 建图/Nav2 导航与 B 的视觉识别响应。**属团队级环境瓶颈，需上报 A/C 共同决策。**

| 参数 | 命令 | 契约基线 | rbot 配置 | **实测（2026-09-27）** | 达成率 | 判定 |
|---|---|---|---|---|---|---|
| `/scan` | `ros2 topic hz /scan` | **10 Hz** | 15 Hz | **5.4 Hz** | 36% | ❌ **低于契约** |
| `/joint_states` | `ros2 topic hz /joint_states` | 标称 50 Hz | 50 Hz | **19.5 Hz** | 39% | ⚠️ 偏低 |
| `/odometry/filtered` | `ros2 topic hz /odometry/filtered` | 30 Hz | 30 Hz | **5.6 Hz** | 19% | ⚠️ 偏低（EKF 跟不上 50 Hz 轮速输入） |
| `/depth_camera/image_raw` | `ros2 topic hz /depth_camera/image_raw` | **15 Hz** | 30 Hz | **3.3 Hz** | **11%** | ❌ **远低于契约（仅 22%）** |
| `/imu/data_raw` | `ros2 topic hz /imu/data_raw` | 未单列 | 200 Hz | **74 Hz** | 37% | ✅ 可用 |
| `/depth_camera/camera_info`、`/depth_camera/depth` | 随图像流 | 契约未要求 | 30 Hz | 未测（同图像流） | — | 可选 |

**测法记录**（可复现）：`source ~/rbot/install/setup.bash && ros2 topic hz <话题>`，观察 10 秒后 `Ctrl+C`；**不要用 `timeout` 包**（SIGTERM 会让 `ros2 topic hz` 来不及打印）。

**降幅规律（重要）**：
- **数值型传感器**（雷达、IMU、轮关节）→ 统一约 **37%**（受物理引擎步频限制）
- **图像型传感器**（相机）→ 仅 **11%**（渲染 640×480 额外开销，软件渲染下被打成瓶颈）
- `/odometry/filtered` 19% 更低 → EKF 自身融合计算在慢仿真下进一步掉速

**缓解方向**（待团队决策）：关 GUI 全 headless、降相机分辨率（640×480→320×240）、关深度相机流（只留 RGB）、精简世界模型、或改用裸机/更强环境。

### ⚪ 缺 1：剩余可选未测的频率（2 项，随图像流）

`/depth_camera/camera_info`、`/depth_camera/depth` —— 与 RGB 图像同源同频（预期 ≈3.3 Hz）。**契约未要求这两路，可选测**。命令同上表。

**另需实测确认的 2 个字段（✅ 均已确认，2026-09-27 23:19）**：

- **`encoding` = `rgb8`** ✅ 已实测确认（`ros2 topic echo /depth_camera/image_raw --field encoding --once`）→ **视觉识别按 RGB 顺序解码，红绿通道不会错位**。Gazebo 源是 `RGB_INT8`，桥接后为标准 `rgb8`。
- **`/scan` 的 QoS = `RELIABLE`, durability `VOLATILE`, depth UNKNOWN** ✅ 已实测（`ros2 topic info -v /scan`）：
  - **发布者只有 1 个**（`ros_gz_bridge`）→ 无重复发布问题 ✅
  - **类型 `sensor_msgs/msg/LaserScan` 正确** ✅
  - **QoS 结论（重要，勿误判）**：发布者 RELIABLE 时，订阅者 BEST_EFFORT **仍可收到**（向下兼容）。**只有"发布 BEST_EFFORT + 订阅 RELIABLE"才会收不到**——当前不是这种情况，**安全，不会通信失败**。实际差别仅是重传略增负载，慢仿真下影响很小。
  - 契约基线写的是 BE depth 5，与实测 RELIABLE **方向安全**，无需修改桥接。（若追求完全对齐可改 `ros_gz_bridge` QoS override，但非必需）

### 🟡 缺 2：需要人拍板的决策（**已全部拍板 ✅**）

| 待决策 | 结论 | 说明 |
|---|---|---|
| `robot_length` / footprint 前缘 | ✅ **取 0.502 / +0.252**（B 决策 2026-09-27） | 严格覆盖网格实测（x 到 +0.2520），符合契约"覆盖整车水平投影"字面要求。**A 的 Nav2 footprint 必须与此一致** |
| `/odom` 最终取哪条链路 | ✅ **取 EKF 的 `/odometry/filtered`** | 已验证有数据（5.6 Hz），链路完整；不用 ground_truth（契约禁止） |

### 🟢 缺 3：原表漏填、本轮已补（2 项）

| 项 | 补上的值 |
|---|---|
| Odometry 的 `child_frame_id` | header=`odom`，**child=`base_footprint`**（契约 frame 行明确要求，原表漏了） |
| 模型文件与版本 | **git `47af3fc3780bd582837f48ce3785d3d68834a1b7`**（2026-05-20）；`rlai_description` 包版本 **0.1.0** |

### ⚪ 契约未强制、但 A 配 Nav2 / 桥接会用到的（建议一并给）

| 参数 | 值 | 状态 |
|---|---|---|
| 相机内参 K/D/P | Gazebo 自动生成，运行时从 camera_info 读 | 需确认**与 640×480 匹配** |
| 雷达规格 | 720 采样、FOV ±π、量程 0.30–25 m、噪声 σ=0.01 m | ✅ 已填 |
| 相机规格 | 640×480、HFoV 87°(1.5184 rad)、near 0.1 / far 10 m | ✅ 已填 |
| IMU 噪声 | gyro σ=0.0003394 rad/s/√Hz、accel σ=0.004 m/s²/√Hz | ✅ 已填 |
| 驱动配置 | `controllers.yaml`：`update_rate=100 Hz`、`odom_publish_rate=50 Hz`、`enable_odom_tf=false` | ✅ 已填 |

### 📌 两个"要不要走变更流程"的频率差异

契约基线 vs rbot 实际对不上：`/scan` 15→**10** Hz、`/camera/image_raw` 30→**15** Hz。按契约第 7 节，**调整表内可调参数只需"记录实际配置和测试"，无需升级版本** → 直接改 `gazebo_sensors.urdf.xacro` 的 `<update_rate>` 并记录即可，**不用走冻结变更流程**。

### 📌 参数之外还欠的东西（提醒，非本次范围）

- `community_interfaces` 接口包（`PerceptionResult.msg`）——**契约里至今不存在**
- `/perception` 识别节点本体
- 4 条固定 TF 的改名落地（`lidar_2d_link`→`laser_link`、`depth_camera_link`→`camera_link`、`depth_camera_rgb_optical_frame`→`camera_optical_frame`）

**契约第 7 节锁定期要求**：模型实值、传感器安装实值 **"B 交付后底盘联调前锁定"**。即上面 🔴🟡 清完、A 认可后，这张表就该冻结，后续改动需同步 A。
