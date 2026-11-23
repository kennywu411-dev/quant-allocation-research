
import pandas as _pd

# 不用 bottleneck 加速 pandas 的求和与均值：它的浮点求和顺序不同，会让已记录的结果在小数点后第 9 位对不上
# （2026-11-19 环境里装了 bottleneck 之后，第一轮回归测试因此失败；2026-11-23 查明）。
_pd.set_option("compute.use_bottleneck", False)
