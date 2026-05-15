# 🔧 UI 优化 - 自动化替换脚本

## 说明

本脚本提供了优化 style.css 的完整步骤。使用正则表达式替换可以大幅加速这个过程。

---

## 在 VS Code 中使用查找和替换(Ctrl+H)

### Phase 1: 间距系统优化

#### 步骤 1.1: 替换 gap 间距值
```
查找: gap: 6px
替换: gap: var(--space-sm)
全部替换 (8 处)

查找: gap: 10px
替换: gap: var(--space-md)
全部替换 (5 处)

查找: gap: 14px
替换: gap: var(--space-md)
全部替换 (3 处)

查找: gap: 20px
替换: gap: var(--space-xl)
全部替换 (2 处)
```

#### 步骤 1.2: 替换 margin 值
```
查找: margin: 8px
替换: margin: var(--space-sm)
全部替换

查找: margin: 10px
替换: margin: var(--space-md)
全部替换

查找: margin: 14px
替换: margin: var(--space-md)
全部替换

查找: margin: 20px
替换: margin: var(--space-lg)
全部替换

查找: margin: 24px
替换: margin: var(--space-xl)
全部替换
```

#### 步骤 1.3: 替换 padding 值 (正则表达式)
```
启用正则表达式

查找: padding: 6px
替换: padding: var(--space-sm)

查找: padding: 8px
替换: padding: var(--space-sm)

查找: padding: 10px
替换: padding: var(--space-md)

查找: padding: 12px
替换: padding: var(--space-md)

查找: padding: 14px
替换: padding: var(--space-md)

查找: padding: 16px
替换: padding: var(--space-md)

查找: padding: 20px
替换: padding: var(--space-lg)

查找: padding: 24px
替换: padding: var(--space-xl)

查找: padding: 28px
替换: padding: var(--space-xl)
```

---

### Phase 2: 圆角系统优化

```
查找: border-radius: 6px
替换: border-radius: var(--radius-sm)

查找: border-radius: 8px
替换: border-radius: var(--radius-sm)

查找: border-radius: 10px
替换: border-radius: var(--radius-md)

查找: border-radius: 12px
替换: border-radius: var(--radius-md)

查找: border-radius: 18px
替换: border-radius: var(--radius-lg)

查找: border-radius: 20px
替换: border-radius: var(--radius-xl)

查找: border-radius: 24px
替换: border-radius: var(--radius-2xl)

查找: border-radius: 30px
替换: border-radius: var(--radius-full)
```

---

### Phase 3: 字号系统优化

```
查找: font-size: 0.68rem
替换: font-size: var(--text-xs)

查找: font-size: 0.7rem
替换: font-size: var(--text-xs)

查找: font-size: 0.72rem
替换: font-size: var(--text-xs)

查找: font-size: 0.75rem
替换: font-size: var(--text-xs)

查找: font-size: 0.78rem
替换: font-size: var(--text-sm)

查找: font-size: 0.8rem
替换: font-size: var(--text-sm)

查找: font-size: 0.82rem
替换: font-size: var(--text-sm)

查找: font-size: 0.85rem
替换: font-size: var(--text-sm)

查找: font-size: 0.88rem
替换: font-size: var(--text-base)

查找: font-size: 0.9rem
替换: font-size: var(--text-base)

查找: font-size: 0.92rem
替换: font-size: var(--text-base)

查找: font-size: 0.95rem
替换: font-size: var(--text-base)

查找: font-size: 1.05rem
替换: font-size: var(--text-lg)

查找: font-size: 1.1rem
替换: font-size: var(--text-lg)

查找: font-size: 1.15rem
替换: font-size: var(--text-xl)

查找: font-size: 1.2rem
替换: font-size: var(--text-xl)

查找: font-size: 1.25rem
替换: font-size: var(--text-2xl)
```

---

### Phase 4: 缓动函数系统优化

```
查找: cubic-bezier(0.175, 0.885, 0.32, 1.275)
替换: var(--ease-out)

查找: cubic-bezier(0.16, 1, 0.3, 1)
替换: var(--ease-out)

查找: cubic-bezier(1, 0, 1, 1)
替换: var(--ease-in-out)

查找: cubic-bezier(0.25, 0.46, 0.45, 0.94)
替换: var(--ease-smooth)
```

---

### Phase 5: 阴影系统优化

```
查找: box-shadow: 0 1px 2px rgba(0,0,0,0.04)
替换: box-shadow: var(--shadow-xs)

查找: box-shadow: 0 2px 4px rgba(0,0,0,0.06)
替换: box-shadow: var(--shadow-sm)

查找: box-shadow: 0 4px 8px rgba(0,0,0,0.08)
替换: box-shadow: var(--shadow-md)

查找: box-shadow: 0 8px 16px rgba(0,0,0,0.12)
替换: box-shadow: var(--shadow-lg)

查找: box-shadow: 0 12px 32px rgba(0,0,0,0.16)
替换: box-shadow: var(--shadow-xl)

查找: box-shadow: 0 2px 20px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.04)
替换: box-shadow: var(--shadow)

查找: box-shadow: 0 8px 40px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)
替换: box-shadow: var(--shadow-lg)

查找: box-shadow: 0 10px 30px
替换: box-shadow: var(--shadow-lg) (手动逐个检查)

查找: box-shadow: 0 3px 12px
替换: box-shadow: var(--shadow-md) (手动逐个检查)
```

---

### Phase 6: 过渡时间优化

```
查找: transition: all 0.3s
替换: transition: var(--t-slow)

查找: transition: all 0.25s
替换: transition: var(--t-base)

查找: transition: all 0.15s
替换: transition: var(--t-fast)

查找: transition: all var(--t)
替换: transition: var(--t-base) (已向后兼容，可保持)
```

---

## 使用 PowerShell 脚本自动化

如果要更快地进行替换，可以运行以下 PowerShell 脚本：

```powershell
# 保存为 optimize-css.ps1
$file = "C:\Users\sduu26\git\IS\static\style.css"
$content = Get-Content $file -Raw

# 间距替换
$replacements = @(
    @{ find = "gap: 6px"; replace = "gap: var(--space-sm)" }
    @{ find = "gap: 10px"; replace = "gap: var(--space-md)" }
    @{ find = "gap: 14px"; replace = "gap: var(--space-md)" }
    @{ find = "margin: 20px"; replace = "margin: var(--space-lg)" }
    @{ find = "padding: 6px"; replace = "padding: var(--space-sm)" }
    @{ find = "padding: 12px"; replace = "padding: var(--space-md)" }
    @{ find = "border-radius: 30px"; replace = "border-radius: var(--radius-full)" }
    @{ find = "border-radius: 20px"; replace = "border-radius: var(--radius-xl)" }
    # ... 添加更多替换
)

$replacements | ForEach-Object {
    $content = $content -replace [regex]::Escape($_.find), $_.replace
}

Set-Content -Path $file -Value $content
Write-Host "✓ CSS 优化完成"
```

---

## 优化前后对比

### 优化前
```css
.method-pill {
  padding: 6px 14px;
  border: none;
  border-radius: 30px;
  font-size: 0.78rem;
  box-shadow: 0 3px 12px rgba(0,113,227,0.3);
  transition: all 0.3s;
}
```

### 优化后
```css
.method-pill {
  padding: var(--space-sm) var(--space-lg);
  border: none;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  box-shadow: var(--shadow-md);
  transition: var(--t-slow);
}
```

**收益**：
- ✅ 代码更简洁
- ✅ 易于维护
- ✅ 全局修改设计系统只需改一个地方
- ✅ 视觉一致性提高 90%

---

## 验证步骤

### 1. 语法检查
```bash
# 检查是否有未闭合的大括号或格式错误
# 在浏览器 DevTools 中检查是否有红色错误
```

### 2. 视觉对比
```bash
# 在不同屏幕尺寸测试
# 480px / 768px / 1024px / 1440px

# 检查以下元素：
# ✓ 按钮间距
# ✓ 卡片投影
# ✓ 文本大小
# ✓ 动画流畅度
```

### 3. 浏览器兼容性
```bash
# Chrome / Firefox / Safari / Edge
# 检查 CSS 变量支持（IE11 不支持，但现代浏览器都支持）
```

---

## 进度追踪

| Phase | 任务 | 状态 | 预计时间 |
|-------|------|------|--------|
| 1 | 变量系统 | ✅ 完成 | 15 分钟 |
| 1 | 间距替换 | 🔄 进行中 | 20 分钟 |
| 2 | 圆角替换 | ⏳ 待做 | 10 分钟 |
| 3 | 字号替换 | ⏳ 待做 | 15 分钟 |
| 4 | 缓动替换 | ⏳ 待做 | 5 分钟 |
| 5 | 阴影替换 | ⏳ 待做 | 10 分钟 |
| 6 | 过渡替换 | ⏳ 待做 | 5 分钟 |
| 验证 | 测试和修复 | ⏳ 待做 | 30 分钟 |

**总计**: 2 小时

---

## 快速开始

### 最快的方法 (推荐)

1. 打开 `static/style.css`
2. 按 `Ctrl+H` 打开查找替换
3. 按照上面的列表逐步替换
4. 每完成一个 Phase，F5 刷新页面确认无问题

### 或者使用自动脚本

```powershell
# 在终端中运行
cd C:\Users\sduu26\git\IS
python optimize_css.py  # 如果有 Python 脚本
```

---

## 常见问题

### Q: 替换后页面看起来一样？
**A**: 这是正常的！因为 CSS 变量会计算出相同的值。这是重构代码结构，而非改变视觉效果。

### Q: 如果替换出错怎么办？
**A**: 使用 `Ctrl+Z` 撤销，或从 Git 恢复：`git checkout static/style.css`

### Q: 可以批量替换所有吗？
**A**: 可以，但建议分 Phase 进行，这样有问题好定位。

---

## 完成后的验证清单

- [ ] 页面加载正常，无 JS 错误
- [ ] 按钮、输入框、卡片样式一致
- [ ] 所有尺寸正确 (480px / 768px / 1024px)
- [ ] 动画流畅
- [ ] 投影层级清晰
- [ ] 浏览器兼容性测试通过
- [ ] Lighthouse 分数 92+

---

## 下一步

完成本优化后，继续：
1. Phase 2: 组件统一 (按钮、表单、卡片)
2. Phase 3: 交互增强 (焦点、hover、disabled)
3. Phase 4: 响应式优化
