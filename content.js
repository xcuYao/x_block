/**
 * X Block 一键拉黑
 * 在每条推文的"三个点"按钮旁注入一键拉黑按钮，
 * 点击后自动模拟原生三步操作：caret -> Block 菜单项 -> 二次确认。
 */
(function () {
  'use strict';

  const SELECTORS = {
    tweet: 'article[data-testid="tweet"]',
    caret: 'button[data-testid="caret"]',
    blockMenuItem: 'div[data-testid="block"]',
    confirmButton: 'button[data-testid="confirmationSheetConfirm"]',
    userName: '[data-testid="User-Name"]',
    profileLink: 'a[role="link"][href^="/"], a[href^="/"]'
  };

  // 屏蔽掉的系统路径，避免把导航链接误当成用户名
  const RESERVED_PATHS = new Set([
    'home', 'explore', 'notifications', 'messages', 'search',
    'settings', 'i', 'compose', 'login', 'logout', 'signup'
  ]);

  const STEP_TIMEOUT = 1500;

  const processed = new WeakSet();

  /** 禁止图标 SVG */
  const ICON_SVG =
    '<svg class="xb-icon" viewBox="0 0 24 24" aria-hidden="true">' +
    '<path d="M12 3.75a8.25 8.25 0 1 0 0 16.5 8.25 8.25 0 0 0 0-16.5zM2.25 12c0-5.385 4.365-9.75 9.75-9.75 2.4 0 4.605.87 6.31 2.31L4.56 18.31A9.71 9.71 0 0 1 2.25 12zm9.75 9.75a9.71 9.71 0 0 1-6.31-2.31L19.44 5.69A9.71 9.71 0 0 1 21.75 12c0 5.385-4.365 9.75-9.75 9.75z"/>' +
    '</svg>';

  /**
   * 等待元素出现在 DOM 中（基于 MutationObserver）
   * @returns {Promise<Element|null>}
   */
  function waitForEl(selector, { timeout = STEP_TIMEOUT, root = document } = {}) {
    return new Promise((resolve) => {
      const found = root.querySelector(selector);
      if (found) {
        resolve(found);
        return;
      }
      const timer = setTimeout(() => {
        observer.disconnect();
        resolve(null);
      }, timeout);
      const observer = new MutationObserver(() => {
        const el = root.querySelector(selector);
        if (el) {
          clearTimeout(timer);
          observer.disconnect();
          resolve(el);
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }

  /** 从推文容器中解析作者用户名 */
  function getUsername(article) {
    const nameContainer = article.querySelector(SELECTORS.userName);
    if (nameContainer) {
      const links = nameContainer.querySelectorAll(SELECTORS.profileLink);
      for (const link of links) {
        const username = extractUsernameFromHref(link.getAttribute('href'));
        if (username) return username;
      }
    }
    // 兜底：遍历文章内所有个人链接
    const links = article.querySelectorAll(SELECTORS.profileLink);
    for (const link of links) {
      const username = extractUsernameFromHref(link.getAttribute('href'));
      if (username) return username;
    }
    return null;
  }

  function extractUsernameFromHref(href) {
    if (!href) return null;
    const clean = href.split('?')[0].split('#')[0];
    const match = clean.match(/^\/([a-zA-Z0-9_]{1,15})$/);
    if (!match) return null;
    const username = match[1];
    if (RESERVED_PATHS.has(username.toLowerCase())) return null;
    return username;
  }

  /** 触发真实的鼠标点击，X 对某些按钮要求事件序列 */
  function realClick(el) {
    if (!el) return;
    const opts = { bubbles: true, cancelable: true, view: window, button: 0 };
    el.dispatchEvent(new PointerEvent('pointerdown', opts));
    el.dispatchEvent(new MouseEvent('mousedown', opts));
    el.dispatchEvent(new PointerEvent('pointerup', opts));
    el.dispatchEvent(new MouseEvent('mouseup', opts));
    el.dispatchEvent(new MouseEvent('click', opts));
  }

  /** 发送 Escape 关闭可能残留的菜单/弹层 */
  function closeOverlays() {
    const opts = { bubbles: true, cancelable: true, key: 'Escape', code: 'Escape' };
    document.dispatchEvent(new KeyboardEvent('keydown', opts));
    document.dispatchEvent(new KeyboardEvent('keyup', opts));
  }

  /** 执行原生拉黑流程 */
  async function performNativeBlock(article, button, username) {
    setLoading(button, true);
    try {
      // 1. 打开"三个点"菜单
      const caret = article.querySelector(SELECTORS.caret);
      if (!caret) throw new Error('caret button not found');
      caret.scrollIntoView({ block: 'center' });
      realClick(caret);

      // 2. 点击 Block 菜单项
      const blockItem = await waitForEl(SELECTORS.blockMenuItem);
      if (!blockItem) throw new Error('block menu item not found');
      realClick(blockItem);

      // 3. 点击二次确认按钮
      const confirmBtn = await waitForEl(SELECTORS.confirmButton);
      if (!confirmBtn) throw new Error('confirm button not found');
      realClick(confirmBtn);

      // 4. 等待确认弹层关闭，作为成功判据
      await waitForSheetClosed();

      // 淡出并移除该推文（React 通常已自行移除，做兜底）
      fadeOutAndRemove(article);
    } catch (err) {
      console.warn('[X Block] block failed for @' + username + ':', err);
      closeOverlays();
      setLoading(button, false);
    }
  }

  /** 等待确认弹层消失（最长 2s） */
  function waitForSheetClosed(timeout = 2000) {
    return new Promise((resolve) => {
      const start = Date.now();
      const tick = () => {
        const stillOpen = document.querySelector(SELECTORS.confirmButton);
        if (!stillOpen) {
          resolve();
          return;
        }
        if (Date.now() - start > timeout) {
          resolve(); // 超时也继续，避免卡死
          return;
        }
        setTimeout(tick, 100);
      };
      tick();
    });
  }

  function fadeOutAndRemove(article) {
    if (!article || !article.isConnected) return;
    article.classList.add('xb-fade-out');
    setTimeout(() => {
      if (article.isConnected) article.remove();
    }, 320);
  }

  function setLoading(button, loading) {
    if (!button) return;
    if (loading) {
      button.classList.add('is-loading');
      button.disabled = true;
    } else {
      button.classList.remove('is-loading');
      button.disabled = false;
    }
  }

  /** 创建一键拉黑按钮 */
  function createButton(username, article) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'xb-block-btn';
    button.setAttribute('aria-label', '一键拉黑 @' + username);
    button.setAttribute('title', '一键拉黑 @' + username);
    button.innerHTML = ICON_SVG;

    button.addEventListener(
      'click',
      (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (button.classList.contains('is-loading')) return;
        performNativeBlock(article, button, username);
      },
      true
    );
    return button;
  }

  /** 为单条推文注入按钮 */
  function processArticle(article) {
    if (!article || processed.has(article)) return;
    const caret = article.querySelector(SELECTORS.caret);
    if (!caret) return;
    // 若该推文已经被注入（例如节点被复用），跳过
    if (article.querySelector('.xb-block-btn')) {
      processed.add(article);
      return;
    }
    const username = getUsername(article);
    if (!username) return;

    const button = createButton(username, article);
    // 紧贴三个点按钮左侧插入
    caret.parentNode.insertBefore(button, caret);
    processed.add(article);
  }

  function scan() {
    const articles = document.querySelectorAll(SELECTORS.tweet);
    articles.forEach(processArticle);
  }

  // 批量防抖处理新增节点
  let scheduled = false;
  function scheduleScan() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      scan();
    });
  }

  function observe() {
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.addedNodes && mutation.addedNodes.length) {
          scheduleScan();
          break;
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function init() {
    scan();
    observe();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
