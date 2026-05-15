# 🔧 style.css 代码改进检查清单

## 优先级排序：需要立即改进的地方

---

## 🔴 HIGH PRIORITY (立即改进)

### 1. 按钮样式混乱，需要统一
**位置**：style.css 中多个地方

**现状**：
```css
/* 现在有多个按钮类 */
.btn-pill { ... }
.example-tag { ... }
.magic-btn { ... }
.journey-submit { ... }
.story-submit { ... }
.btn { ... }（可能还有）
```

**问题**：难以维护，样式不一致，用户体验不统一

**建议**：
```css
/* 统一为 3 种主类型 */
.btn-primary { ... }
.btn-secondary { ... }
.btn-ghost { ... }

/* 配合尺寸修饰符 */
.btn.sm { ... }
.btn.md { ... }
.btn.lg { ... }
```

**代码位置**：
- line 208: `.example-tag`
- line 220: `.vec-ex-tag`
- line 231: `.history-chip`
- line 248: `.journey-submit`
- line 456: `.story-submit`
- line 370: `.magic-btn`

---

### 2. 间距值混乱，需要标准化
**现状**：
```css
gap: 6px;      /* ❌ 不在 8px 基数 */
gap: 8px;
gap: 10px;     /* ❌ 不在 8px 基数 */
gap: 12px;     /* ❌ 不在 8px 基数 */
gap: 14px;     /* ❌ 不在 8px 基数 */
gap: 16px;
gap: 20px;     /* ❌ 不在 8px 基数 */
gap: 24px;
gap: 28px;     /* ❌ 不在 8px 基数 */
```

**建议**：统一为 8px 基数
```css
gap: 8px;      /* 1x */
gap: 16px;     /* 2x */
gap: 24px;     /* 3x */
gap: 32px;     /* 4x */
```

**需要替换的值**：
- `padding: 6px` → `8px`
- `padding: 10px` → `8px` 或 `12px`
- `gap: 10px` → `8px` 或 `16px`
- `padding: 12px` → `16px`
- `gap: 14px` → `16px`
- `margin: 20px` → `16px` 或 `24px`

---

### 3. 圆角值混乱
**现状**：
```css
border-radius: 4px;    /* ❌ 混乱 */
border-radius: 6px;    /* ❌ 混乱 */
border-radius: 8px;
border-radius: 10px;   /* ❌ 混乱 */
border-radius: 12px;
border-radius: 16px;
border-radius: 18px;   /* 混乱 */
border-radius: 20px;
border-radius: 24px;
border-radius: 30px;   /* ❌ 混乱 */
```

**建议**：统一为 4 级
```css
--radius-sm: 8px;      /* 小组件 */
--radius-md: 12px;     /* 按钮、输入框 */
--radius-lg: 16px;     /* 卡片 */
--radius-xl: 20px;     /* 大容器 */
--radius-full: 9999px; /* 完全圆形 */
```

**替换映射**：
- `4px` → 不需要
- `6px` → `8px`
- `10px` → `12px`
- `18px` → `16px` 或 `20px`
- `20px` → `20px` (保留)
- `24px` → `20px` 或更大
- `30px` → `--radius-full`

---

### 4. 阴影值混乱，层级不清
**现状**：
```css
box-shadow: 0 1px 4px rgba(0,0,0,0.06);
box-shadow: 0 3px 12px rgba(0,0,0,0.3);
box-shadow: 0 4px 15px rgba(0,0,0,0.06);
box-shadow: 0 8px 16px rgba(0,0,0,0.12);
box-shadow: 0 10px 30px rgba(0, 113, 227, 0.15);  /* 颜色特定 */
/* ... 等等，非常混乱 */
```

**建议**：使用阴影系统
```css
--shadow-xs: 0 1px 2px rgba(0,0,0,0.04);
--shadow-sm: 0 2px 4px rgba(0,0,0,0.06);
--shadow-md: 0 4px 8px rgba(0,0,0,0.08);
--shadow-lg: 0 8px 16px rgba(0,0,0,0.12);
--shadow-xl: 0 12px 32px rgba(0,0,0,0.16);
```

**替换所有的**：
- `box-shadow: 0 1px 4px ...` → `var(--shadow-xs)`
- `box-shadow: 0 3px 12px ...` → `var(--shadow-md)`
- `box-shadow: 0 4px 15px ...` → `var(--shadow-md)`
- `box-shadow: 0 10px 30px ...` → `var(--shadow-lg)` (移除颜色）
- 等等...

---

### 5. 动画缓动函数不够 Apple 风格
**现状**：
```css
cubic-bezier(0.175, 0.885, 0.32, 1.275)   /* 过于夸张 */
cubic-bezier(0.16, 1, 0.3, 1)             /* 可以，但不一致 */
cubic-bezier(1, 0, 1, 1)                  /* 线性，不自然 */
```

**建议**：
```css
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);     /* 标准缓动 */
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);       /* 出现 */
--ease-in: cubic-bezier(0.7, 0, 0.84, 0);        /* 消失 */
```

**需要更新的地方**：
- 所有 `cubic-bezier(0.175, 0.885, 0.32, 1.275)` → `var(--ease-out)`
- 所有 `cubic-bezier(1, 0, 1, 1)` → `var(--ease-in-out)`

---

## 🟡 MEDIUM PRIORITY (下一阶段)

### 6. 选择器样式分散
**问题**：
- `#topk-select` 和 `#category-select` 的样式几乎相同
- 表单元素没有统一的类

**建议**：
```css
/* 为所有 select 添加统一类 */
select {
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--divider);
  border-radius: var(--radius-md);
  background: var(--card);
  color: var(--text);
  font-family: inherit;
  font-size: var(--text-base);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,...");
  background-repeat: no-repeat;
  background-position: right var(--space-md) center;
  padding-right: var(--space-xl);
  transition: var(--t-base);
}

select:hover {
  border-color: rgba(0,113,227,0.2);
}

select:focus-visible {
  box-shadow: 0 0 0 3px rgba(0,113,227,0.1);
}
```

---

### 7. 输入框样式不一致
**问题**：
- `.journey-input` 和 `input[type="text"]` 样式混乱
- 焦点状态处理不统一

**建议**：统一所有输入框样式

---

### 8. 颜色对比度检查
**需要检查的地方**：
```css
--text3: #a1a1a6;  /* 在 #ffffff 上的对比度可能只有 4.5:1 (边界) */
```

**建议**：确保所有文本对比度 >= 4.5:1 (WCAG AA)

**工具**：https://webaim.org/resources/contrastchecker/

---

### 9. 加载状态优化
**现状**：
```css
#spinner { display: none; /* 简单的旋转 */ }
```

**建议**：
```css
#spinner {
  display: none;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  padding: 60px 0;
}

.spinner-ring {
  width: 40px;
  height: 40px;
  border: 3px solid var(--divider);
  border-top-color: var(--blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

#spinner.show {
  display: flex;
}
```

---

### 10. 响应式设计碎片化
**现状**：@media 查询分散在各处

**建议**：统一集中在文件底部

```css
/* 移动设备 */
@media (max-width: 480px) {
  :root { --card-size: 120px; }
  .hero h1 { font-size: 1.8rem; }
  /* ... */
}

/* 平板 */
@media (max-width: 768px) {
  .metric-desc { grid-template-columns: repeat(2, 1fr); }
  /* ... */
}

/* 桌面 */
@media (min-width: 1024px) {
  /* ... */
}
```

---

## 🟢 LOW PRIORITY (后续优化)

### 11. 深色模式支持
**建议**：
```css
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1d1d1f;
    --card: #2a2a2e;
    --text: #f5f5f7;
    --text2: #a1a1a6;
    /* ... */
  }
}
```

---

### 12. 运动偏好设置
**建议**：
```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 📊 快速评分

| 维度 | 当前 | 目标 | 难度 |
|------|------|------|------|
| 间距系统 | 3/10 | 9/10 | 中等 |
| 按钮统一 | 4/10 | 9/10 | 简单 |
| 圆角规范 | 5/10 | 9/10 | 简单 |
| 阴影系统 | 4/10 | 9/10 | 简单 |
| 动画缓动 | 6/10 | 9/10 | 简单 |
| 颜色对比 | 7/10 | 9/10 | 简单 |
| 响应式 | 6/10 | 9/10 | 中等 |
| 可访问性 | 5/10 | 9/10 | 中等 |

**总体估计**：
- 高优先级修复：4-6 小时
- 中优先级优化：2-3 小时
- 测试和验证：1-2 小时
- **总计**：7-11 小时完整优化

---

## 实施路线图

### Week 1 (高优先级)
- [ ] Day 1: 创建 CSS 变量系统（间距、圆角、阴影、缓动）
- [ ] Day 2: 统一按钮样式（替换所有 .btn-* 类）
- [ ] Day 3: 规范化圆角和阴影
- [ ] Day 4: 更新动画缓动函数

### Week 2 (中优先级)
- [ ] Day 1: 表单元素统一样式
- [ ] Day 2: 响应式设计集中管理
- [ ] Day 3: 颜色对比度检查和修正
- [ ] Day 4: 加载状态增强

### Week 3 (测试和反馈)
- [ ] Day 1-2: 浏览器兼容性测试
- [ ] Day 3: 用户反馈收集
- [ ] Day 4: 迭代优化

---

## 验收标准

✅ **设计系统**
- [ ] 所有间距都是 8px 的倍数
- [ ] 所有圆角都在预定义列表中
- [ ] 所有阴影都使用系统变量
- [ ] 所有缓动函数都在预定义列表中

✅ **组件一致性**
- [ ] 所有按钮使用相同的类系统
- [ ] 所有表单元素样式一致
- [ ] 所有卡片使用一致的投影

✅ **可访问性**
- [ ] 所有文本对比度 >= 4.5:1
- [ ] 所有交互元素有焦点指示器
- [ ] 支持键盘导航
- [ ] 支持运动偏好设置

✅ **性能**
- [ ] CSS 文件大小不增加 > 10%
- [ ] 页面 Lighthouse 分数 >= 90

✅ **用户体验**
- [ ] 动画平滑自然
- [ ] 交互反馈明确
- [ ] 响应式布局完美
- [ ] 在所有设备上都能使用
