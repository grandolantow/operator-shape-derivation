# EleWise 类算子场景路由

> 本文档用于**场景判定**和**策略选择**。确定场景后，按链接进入对应详细文档。

---

## 场景判定流程

EleWise（Elementwise）：输入输出 Shape 相同，逐元素独立计算，无跨元素依赖。直接展平还要求实际地址连续；非连续 stride 须保留地址映射或使用适用的搬运方案。不区分一元/二元，Sin、Cos、Abs、Add、Mul 等均可。

```
给定: N 个输入 shape + M 个输出 shape

Step 1 — Shape 判定:
  所有输入输出 shape 完全相同且地址连续？
    ├─ YES → EleWise，展平为 dim0，1D 线性处理 → 进入 Step 2
    └─ NO  → 按实际广播或非连续 stride 组织，不能直接展平

Step 2 — dtype × 运算 判定（决定 Compute 路径）:
  运算为 Add/Sub / 以加减为主的累加链路 AND dtype ∈ {FP16, BF16} AND spec 未声明"输入同量级"？
    ├─ YES → 符合原中间舍入合同后评估升精度：Cast→FP32 计算→Cast，需额外 K 份 FP32 中间 Buffer
    └─ NO  → 原 dtype 直接计算分支
  两分支的 UB 预算与 ubFormer 公式见 [tiling.md](tiling.md)
  （乘法/除法等其他场景暂未覆盖，先沿用原 dtype 直算分支继续 tiling。"未覆盖"只是
  路由事实，不是"Mul/Div 直算精度足够"的结论；dtype 分支的精度决策与证据分级
  见 [../common/api-precision-notes.md](../common/api-precision-notes.md) 相应章节）
```

**Step 2 策略说明**：半精度“大数吃小数”时评估升精度，但必须符合原算子的中间舍入与精度合同；不能因升精度改写原语义。K 值与 Cast 写法等属 API 实现细节。tiling-design 负责宏观切块（分支判定、UB 预算、ubFormer），API 实现细节由 Compute 阶段落地时确定。

---

## 通用规则

- **多核对齐**：使用目标方案的字节粒度，元素数等价随 dtype 变化；经验目标粒度不保证每核下限。
- **UB 对齐**：目标平台确认粒度后逐物理 buffer 对齐，不从示例 256B 推断通用最优。
- **区分首/尾 block**：尾 block 数据量可能小于首 block，循环次数和 tail 大小不同

常量定义和计算公式详见 [tiling.md](tiling.md)。

---

## 跨场景参考

| 主题 | 文档 |
|------|------|
| EleWise Tiling 详细计算（常量、公式、模板、dtype 分支 UB 预算） | [tiling.md](tiling.md) |
| Broadcast 场景路由（输入 Shape 不同时） | CANNBot `references/broadcast/patterns.md` |

[来源](../SOURCES.md)。
