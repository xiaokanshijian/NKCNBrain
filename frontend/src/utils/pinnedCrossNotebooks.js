// /** 跨本子任务簇：主页本子钉子勾选状态（按登录用户隔离） */

/** 主页本子钉子勾选：用于任务簇整理（勾选后点簇内「+」加入），与跨本问答选本无关 */

const STORAGE_KEY_PREFIX = 'pinnedCrossNotebooks_';

export function getPinnedStorageKey() {
  const user = localStorage.getItem('originRealName') || '';
  return STORAGE_KEY_PREFIX + user;
}

export function notebookFullUsername(writer, title) {
  return `${(writer || '').trim()}_${(title || '').trim()}`;
}

export function loadPinnedNotebookKeys() {
  try {
    const raw = localStorage.getItem(getPinnedStorageKey());
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function savePinnedNotebookKeys(list) {
  localStorage.setItem(getPinnedStorageKey(), JSON.stringify(list));
}

export function isNotebookPinned(writer, title) {
  const key = notebookFullUsername(writer, title);
  return loadPinnedNotebookKeys().some((item) => item.key === key);
}

/** @returns {boolean} 操作后是否为勾选状态 */
export function toggleNotebookPin(writer, title, sceneName) {
  const key = notebookFullUsername(writer, title);
  const list = loadPinnedNotebookKeys();
  const idx = list.findIndex((item) => item.key === key);
  if (idx >= 0) {
    list.splice(idx, 1);
    savePinnedNotebookKeys(list);
    return false;
  }
  list.push({ key, writer, title, scene: sceneName || '' });
  savePinnedNotebookKeys(list);
  return true;
}

// /** 供问答 API 使用：排除当前本子，返回 JSON 字符串或空 */
// export function getPinnedCrossNotebooksForApi(currentUserId) {
//   const current = (currentUserId || '').trim();
//   const fullUsernames = loadPinnedNotebookKeys()
//     .map((item) => item.key || notebookFullUsername(item.writer, item.title))
//     .filter((full) => full && full !== current);
//   return fullUsernames.length ? JSON.stringify(fullUsernames) : '';
// }
