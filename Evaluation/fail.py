import matplotlib.pyplot as plt
import numpy as np

# --- 1. 定义类别 ---
categories = [
    "Parsing Failure",
    "Tool Invocation Error",
    "Reasoning Deficit",
    "Timeout",
    "Iteration Limit Exceeded",
    "Context Overflow",
]

# --- 2. 定义模型 ---
models = [
    "Gemini-3-flash",
    "GPT-5-mini",
    "Qwen3-235B-A22B",
    "DeepSeek-V3.2",
]

# --- 3. 数据输入 ---
data = {
    "Gemini-3-flash":  [280, 157,  862,  69, 268, 18],
    "GPT-5-mini":      [ 85, 285, 1089,   1, 718, 37],
    "Qwen3-235B-A22B": [144, 243, 1275,   8, 102,  9],
    "DeepSeek-V3.2":   [835, 107,  702,  12, 540, 11],
}

# --- 4. 自定义颜色 ---
custom_colors = [
    "#FA5C5C",
    "#FFD41D",
    "#5DD3B6",
    "#211C84",
    "#8DBCC7",
    "#DDEB9D",
]

# --- 5. 画布设置 ---
fig, axes = plt.subplots(2, 2, figsize=(12, 12))
fig.suptitle(
    "Agent Failure Analysis Distribution",
    fontsize=20,
    fontweight="bold",
    y=0.95,
)

axes = axes.flatten()
wedges_for_legend = None

# --- 6. 绘图循环 ---
for i, model in enumerate(models):
    ax = axes[i]
    values = data[model]
    total = sum(values)

    wedges, _ = ax.pie(
        values,
        startangle=90,
        colors=custom_colors,
        explode=[0.035] * len(categories),
        wedgeprops={"edgecolor": "white", "linewidth": 2.5},
        radius=0.78,
    )

    if wedges_for_legend is None:
        wedges_for_legend = wedges

    label_infos = []

    for j, p in enumerate(wedges):
        pct = values[j] / total * 100
        if pct >= 10:
            label_text = f"{pct:.1f}%"        # 例: 49.2%
        elif pct >= 1:
            label_text = f"{pct:.1f}%"        # 例: 6.4%
        elif pct >= 0.1:
            label_text = f"{pct:.1f}%"        # 例: 0.41%
        else:
            label_text = f"{pct:.2g}%"        # 例: 0.045%（2 位有效数字）
        ang = (p.theta1 + p.theta2) / 2

        x = np.cos(np.deg2rad(ang))
        y = np.sin(np.deg2rad(ang))

        label_infos.append({
            "text": label_text,
            "x": x,
            "y": y,
            "side": 1 if x >= 0 else -1,
            "xy": (x * 0.80, y * 0.80),
        })

    # --- 标注避让参数 ---
    min_gap = 0.10
    y_limit = 0.92

    for side in [-1, 1]:
        side_labels = [info for info in label_infos if info["side"] == side]
        side_labels.sort(key=lambda d: d["y"])

        ys = [info["y"] * 0.92 for info in side_labels]

        for k in range(1, len(ys)):
            if ys[k] - ys[k - 1] < min_gap:
                ys[k] = ys[k - 1] + min_gap

        if ys and ys[-1] > y_limit:
            shift = ys[-1] - y_limit
            ys = [y - shift for y in ys]

        for k in range(len(ys) - 2, -1, -1):
            if ys[k + 1] - ys[k] < min_gap:
                ys[k] = ys[k + 1] - min_gap

        if ys and ys[0] < -y_limit:
            shift = -y_limit - ys[0]
            ys = [y + shift for y in ys]

        for info, new_y in zip(side_labels, ys):
            info["label_y"] = new_y

    # --- 画标注 ---
    for info in label_infos:
        side = info["side"]

        # 关键修改：沿扇区方向外扩，而不是固定到左右边缘
        label_r = 0.90
        label_x = info["x"] * label_r
        label_y = info["label_y"]

        # 顶部/底部的小扇区稍微外扩一点，避免压到圆环
        if abs(info["y"]) > 0.85:
            label_x = info["x"] * 0.82

        ax.annotate(
            info["text"],
            xy=info["xy"],
            xytext=(label_x, label_y),
            textcoords="data",
            ha="left" if side > 0 else "right",
            va="center",
            fontsize=14,
            fontweight="bold",
            color="black",
            arrowprops=dict(
                arrowstyle="-",
                color="gray",
                lw=1.1,
                shrinkA=0,
                shrinkB=0,
                connectionstyle="arc3,rad=0.05",
            ),
        )

    # --- donut 中心 ---
    centre_circle = plt.Circle((0, 0), 0.48, fc="white")
    ax.add_artist(centre_circle)

    ax.set_title(model, fontsize=16, fontweight="bold", pad=20)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.02, 1.02)

# --- 7. 图例设置 ---
legend = fig.legend(
    wedges_for_legend,
    categories,
    title="Failure Categories",
    loc="lower center",
    bbox_to_anchor=(0.5, -0.02),
    ncol=3,
    fontsize=17,
    title_fontsize=16,
    frameon=True,
)

legend.get_title().set_fontweight("bold")

# --- 8. 布局与导出 ---
plt.tight_layout(rect=[0, 0.08, 1, 0.95])
plt.savefig("Failed.png", dpi=600, bbox_inches="tight")
