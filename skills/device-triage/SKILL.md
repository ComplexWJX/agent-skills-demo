---
name: device-triage
description: 当用户要求排查 ONU 或其他设备离线、心跳中断、连接仍在但业务无响应、ping 发出后仍无法判断在线时使用。
---

# 设备离线排查

1. 用户未提供设备编号时，先询问编号，不得猜测。
2. 调用 get_device_status(device_id) 获取业务心跳与连接状态。
   若设备不存在，报告未找到并结束，不得编造证据。
3. 调用 read_skill_reference，skill_name 为 device-triage，
   relative_path 为 references/offline-rules.md，加载判断口径。
4. 调用 get_device_events(device_id) 读取事件。
5. 结合心跳年龄、预期间隔和事件给出结论。写明工具返回的观测时间和数据来源。
6. 输出依次包含：观测结论、证据、可能原因、下一步排查。
   缺乏证据时明确说“尚不能确认”，不要将可能原因写成事实。

## 支持资源

references/offline-rules.md：离线判断口径及 ping 与业务心跳的区别，诊断时必读。

