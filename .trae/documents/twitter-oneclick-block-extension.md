# Twitter/X 一键拉黑浏览器插件 — 实现计划

## 一、需求概述

开发一款 Chrome（Manifest V3）浏览器插件，在 Twitter/X 的每条推文（含时间线与评论回复区）的"三个点"菜单按钮**旁边**新增一个"一键拉黑"按钮。点击后直接调用 Twitter 原生拉黑流程（点击三个点 → 点击 Block → 点击二次确认），将三步合并为一步，拉黑成功后该条推文/评论淡出移除。

## 二、现状分析

- 工作目录 `/Users/yaoning/Documents/trae_projects/x_block` 为**空目录**，需从零搭建。
- Twitter/X 为 React 单页应用，内容动态加载（虚拟列表 + 无限滚动），需用 `MutationObserver` 监听 DOM 变化并为新加载的推文注入按钮。
- 关键 DOM 特征（基于现有开源实现与 X 前端结构）：
  - 每条推文容器：`article[data-testid="tweet"]`
  - 右上角"三个点"菜单按钮：`button[data-testid="caret"]`
  - 弹出菜单项中"Block @xxx"：`div[data-testid="block"]`（菜单项文本含 "Block"）
  - 二次确认对话框的确认按钮：`button[data-testid="confirmationSheetConfirm"]`（文本为 "Block"）
  - 作者用户名：`article` 内 `[data-testid="User-Name"]` 中 `a[href^="/"]` 链接，href 形如 `/screen_name`
- 用户决策：按钮出现在**所有推文**；拉黑成功后推文**淡出移除**。

## 三、技术方案与关键决策

### 核心拉黑方式：模拟原生 UI 点击（而非直接调 API）
用户明确要求"点击直接就调用 twitter 的拉黑功能"，因此采用**程序化触发原生 DOM 点击**的方式，自动走完三步：
1. 找到该推文的 `button[data-testid="caret"]` 并 `.click()` 打开菜单；
2. 用 `MutationObserver`/轮询等待菜单项 `div[data-testid="block"]` 出现，点击它；
3. 等待确认弹窗中的 `button[data-testid="confirmationSheetConfirm"]` 出现，点击它；
4. 关闭可能残留的菜单/弹层（按 Escape）。

**为什么不用直接 fetch API**：开源实现（BlockMaster）用 `blocks/create.json` + 硬编码公开 bearer token + ct0 cookie。该方式脆弱（token 可能失效、可能触发风控/429），且不属于"调用 twitter 拉黑功能"的语义。模拟原生 UI 点击最稳健、最贴合需求、无需任何鉴权 token。

### 多语言兼容
X 的"Block"菜单项在不同语言界面下文案不同，因此选择器**优先使用 `data-testid`**（`block`、`confirmationSheetConfirm`、`caret` 均为语言无关的稳定标识），不依赖文本匹配。

### 防重复注入
用 `WeakSet` 记录已处理的 article，避免重复添加按钮。

### 动态加载处理
- 初始扫描全页 `article[data-testid="tweet"]`；
- 用 `MutationObserver` 监听 `document.body`，对子树新增节点做**批量/防抖**处理（类似开源实现的 batch queue），避免性能问题。

### 按钮布局
- 将按钮插入到 `button[data-testid="caret"]` 的**前面**（紧贴三个点左侧），与原生工具栏对齐；
- 复刻 X 原生图标按钮样式（圆形 hover 背景、SVG 禁止图标），通过独立 class `xb-block-btn` 注入 CSS，不污染原站样式；
- 使用内联 SVG（禁止/block 图标），`aria-label` 提供无障碍文案。

### 交互与反馈
- 点击后立即禁用按钮并显示加载态（旋转图标），防止重复点击；
- 监听拉黑成功：X 在拉黑后原推文通常会被 React 移除/替换。为稳妥起见，在点击确认按钮后，**短暂轮询确认弹层是否消失**（或该 article 是否已从 DOM 移除）作为成功判据；成功后对仍存在的 article 手动执行淡出移除（opacity 过渡 300ms 后 `remove()`）；
- 失败则恢复按钮并 `console.warn`（轻量，不做复杂 toast，保持最小实现）。

### 事件处理
- 按钮 click 使用捕获阶段并 `stopPropagation()`，避免触发推文本身的点击跳转；
- 整个自动点击流程中对每个步骤加超时保护（如 1500ms），任一步骤未找到目标则中止并恢复按钮，避免卡死。

## 四、文件清单（全部为新建）

| 文件 | 作用 |
| --- | --- |
| `manifest.json` | Manifest V3 配置，声明 content script 注入到 `x.com` / `twitter.com` |
| `content.js` | 核心逻辑：扫描推文、注入按钮、模拟原生拉黑三步点击、淡出移除 |
| `content.css` | 拉黑按钮样式（圆形 hover、图标、加载态、淡出动画） |
| `icons/icon16.png` / `icon48.png` / `icon128.png` | 插件图标 |

> 图标资源：使用 `assets/image_utils.py`（Pillow）在项目内生成简洁的"禁止/block"主题 PNG 图标（红圈斜杠风格），分别输出 16/48/128 三种尺寸。

### manifest.json 要点
- `manifest_version: 3`
- `content_scripts`：matches `https://x.com/*`、`https://twitter.com/*`，`run_at: document_idle`，注入 `content.css` + `content.js`
- `permissions: []`（无需 storage / tabs；纯 UI 自动化，最小权限）
- `action` 可选，仅展示一个简单 popup 说明（若需最小化可省略；为简单起见**不做 popup**，保持插件无背景页、无设置页）

### content.js 结构
```
IIFE 严格模式
  - SELECTORS 常量（tweet / caret / blockMenuItem / confirmButton）
  - processed = new WeakSet()
  - injectButton(article): 找 caret 按钮，若无或已注入则跳过；提取用户名；创建按钮并插入 caret 前
  - getUsername(article): 从 User-Name 内首条 /screen_name 链接解析
  - performNativeBlock(article, button):
       1. 找 caret 并 click
       2. waitForEl('div[data-testid="block"]') -> click
       3. waitForEl('button[data-testid="confirmationSheetConfirm"]') -> click
       4. waitForArticleGoneOrSheetClosed(article) -> fadeOutAndRemove(article)
       每步带超时，失败恢复按钮并 Escape 关闭弹层
  - waitForEl(selector, {timeout, root}): 返回 Promise，用 MutationObserver 等待
  - processPost/scan: 遍历 article 注入
  - MutationObserver + 防抖 batch 处理新增节点
  - 启动：初始 scan + observe
```

### content.css 要点
- `.xb-block-btn`：与 caret 按钮同尺寸（约 36px）、透明背景、圆形、hover 变浅红背景、红色禁止图标；
- `.xb-block-btn.is-loading .xb-icon`：旋转动画；
- `.xb-fade-out`：`opacity: 0; transition: opacity .3s ease`；
- 所有选择器以 `.xb-` 前缀隔离，避免与原站冲突。

## 五、假设与决策

1. **不做设置页/popup/快捷键/白名单**：用户需求聚焦，保持最小可用实现。
2. **不调用 X 内部 API**：采用模拟原生点击，规避鉴权与风控，符合"调用 twitter 拉黑功能"语义。
3. **使用 `data-testid` 选择器**：语言无关、相对稳定；若 X 未来改版需相应更新选择器（这是所有 X 插件的共性）。
4. **覆盖所有推文**：时间线、评论回复、提及、推文详情页均注入（用户已确认"所有推文"）。
5. **无需 host_permissions**：content script 只操作页面 DOM，不发跨域请求；matches 已限定 x.com/twitter.com。
6. **权限最小化**：不申请 storage/tabs/scripting，降低审核与安全风险。

## 六、验证步骤

1. 打开 Chrome → `chrome://extensions/` → 开启"开发者模式" → "加载已解压的扩展程序" → 选择项目目录。
2. 访问 `https://x.com` 首页时间线，确认每条推文三个点左侧出现红色禁止图标按钮，无样式错位。
3. 进入某条推文详情页，滚动评论区，确认动态加载的评论上也出现按钮。
4. 点击某条（测试）评论的拉黑按钮：
   - 观察到菜单自动打开、Block 自动点击、确认框自动点击；
   - 该评论淡出消失；
   - 刷新后该用户确实处于已拉黑状态（验证为真实调用原生拉黑）。
5. 打开 DevTools Console，确认无报错；快速连续点击不同按钮，确认加载态/防重入正常。
6. 异常路径测试：在菜单打开瞬间手动点别处关闭，确认按钮能恢复、不残留弹层。
