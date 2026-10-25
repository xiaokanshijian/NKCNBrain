import axios from 'axios'
import { API_BASE_URL } from '@/config/apiConfig'

// 呼吸音频分析API端点（独立服务器）
const AUDIO_ANALYSIS_API_URL = (process.env.VUE_APP_SERVICE_8000_API_RESPLLM_PREDICT_URL || "http://localhost:8000/api/respllm/predict/")

export function findMetadataFile(audioFileName, fileNameList) {
  if (!fileNameList || fileNameList.length === 0) return null;
  const audioNameWithoutExt = audioFileName.replace(/\.[^/.]+$/, '');
  const txtFile = fileNameList.find(fileName => {
    const nameWithoutExt = fileName.replace(/\.[^/.]+$/, '');
    return nameWithoutExt === audioNameWithoutExt && fileName.toLowerCase().endsWith('.txt');
  });
  return txtFile || null;
}

export async function readMetadataFile(metadataFileName, userId) {
  const url = encodeURIComponent(metadataFileName) + "&userbook=" + encodeURIComponent(userId);
  const fileUrl = `${API_BASE_URL}/api/pdf/?url=${url}`;
  const response = await fetch(fileUrl);
  if (!response.ok) throw new Error('无法读取元数据文件');
  return await response.text();
}

export function parseMetadataFromText(text) {
  const metadata = {};
  if (!text || text.trim() === '') return metadata;
  const lines = text.split('\n');
  for (const line of lines) {
    const trimmedLine = line.trim();
    if (trimmedLine && trimmedLine.includes(':')) {
      const [key, ...valueParts] = trimmedLine.split(':');
      const value = valueParts.join(':').trim();
      const normalizedKey = key.trim().toLowerCase();
      if (normalizedKey === 'task_type' || normalizedKey === 'tasktype') metadata.task_type = value;
      else if (normalizedKey === 'modality') metadata.modality = value;
      else if (normalizedKey === 'gender' || normalizedKey === '性别') metadata.gender = value;
      else if (normalizedKey === 'age' || normalizedKey === '年龄') metadata.age = value;
      else if (normalizedKey === 'symptoms' || normalizedKey === '症状') metadata.symptoms = value;
      else if (normalizedKey === 'medhistory' || normalizedKey === '病史') metadata.medhistory = value;
      else if (normalizedKey === 'location' || normalizedKey === '录音位置') metadata.location = value;
    }
  }
  return metadata;
}

export function getLongTermUserIdFromAudioOrBlockName(audioFileNameOrBlockId) {
  if (!audioFileNameOrBlockId || typeof audioFileNameOrBlockId !== 'string') return null;
  const baseName = audioFileNameOrBlockId.replace(/\.[^/.]+$/, '').trim();
  const m = baseName.match(/^(.+)_(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2})$/);
  return m ? m[1] : null;
}

export function findLongTermBlockFileName(longTermUserId, fileNameList) {
  if (!longTermUserId || !fileNameList || fileNameList.length === 0) return null;
  const expectedName = `${longTermUserId}_LONG.txt`;
  return fileNameList.find(name => name === expectedName) || null;
}

export function parseBlockFileContent(text) {
  const result = { blockId: '', prevHash: '', bodyLines: [], bodyMap: {} };
  if (!text || !text.trim()) return result;
  const lines = text.split('\n');
  let section = null;
  for (const line of lines) {
    const t = line.trim();
    if (t === '[BLOCK_HEADER]') { section = 'header'; continue; }
    if (t === '[BLOCK_BODY]') { section = 'body'; continue; }
    if (t.includes(':')) {
      const [key, ...valueParts] = t.split(':');
      const value = valueParts.join(':').trim();
      const k = key.trim();
      if (section === 'header') {
        if (k.toLowerCase() === 'block_id') result.blockId = value;
        if (k.toLowerCase() === 'prev_hash') result.prevHash = value;
      }
      if (section === 'body') {
        result.bodyLines.push(t);
        result.bodyMap[k] = value;
      }
    }
  }
  return result;
}

const LONG_BLOCK_BODY_TO_METADATA = {
  Gender: 'gender',
  Age: 'age',
  Height: 'height',
  Weight: 'weight',
  Birth_Time: 'birth_time',
  Birth_Place: 'birth_place',
  Location: 'location',
  Medical_History: 'medhistory',
  Family_History: 'family_history'
};

export function parseLongTermBlockBodyToMetadata(bodyMap) {
  const meta = {};
  if (!bodyMap) return meta;
  for (const [blockKey, apiKey] of Object.entries(LONG_BLOCK_BODY_TO_METADATA)) {
    const val = bodyMap[blockKey];
    if (val != null && String(val).trim() !== '') meta[apiKey] = String(val).trim();
  }
  return meta;
}

export async function readLongTermBlockAsMetadata(longTermUserId, fileNameList, userbook) {
  const longFileName = findLongTermBlockFileName(longTermUserId, fileNameList);
  if (!longFileName) return {};
  try {
    const content = await readMetadataFile(longFileName, userbook);
    const parsed = parseBlockFileContent(content);
    return parseLongTermBlockBodyToMetadata(parsed.bodyMap);
  } catch (e) {
    console.warn('读取长期记忆块失败:', e);
    return {};
  }
}

export async function loadMergedMetadataForInference(audioFileName, fileNameList, userbook) {
  const shortMeta = await loadAudioMetadata(audioFileName, fileNameList, userbook);
  const longTermUserId = getLongTermUserIdFromAudioOrBlockName(audioFileName);
  const longMeta = longTermUserId ? await readLongTermBlockAsMetadata(longTermUserId, fileNameList, userbook) : {};
  const merged = { ...longMeta };
  Object.keys(shortMeta).forEach(k => {
    if (shortMeta[k] != null && shortMeta[k] !== '') merged[k] = shortMeta[k];
  });
  return merged;
}

export function buildSummaryFromInferenceResult(rawResult) {
  if (rawResult == null) return '';
  const data = rawResult.prediction_result ?? rawResult.result ?? rawResult;
  const parts = [];
  if (data.prediction) parts.push(`预测: ${data.prediction}`);
  if (data.confidence != null) parts.push(`置信度: ${(data.confidence * 100).toFixed(2)}%`);
  if (data.explanation) parts.push(`解释: ${data.explanation}`);
  if (data.recommendation) parts.push(`建议: ${data.recommendation}`);
  if (data.answer) parts.push(`回答: ${data.answer}`);
  if (parts.length === 0) return typeof data === 'object' ? JSON.stringify(data) : String(data);
  return parts.join('\n');
}

function formatBlockBodyForSummary(bodyMap) {
  const lines = [];
  if (!bodyMap) return lines;
  const skipKeys = new Set(['Summary', 'summary']);
  for (const [k, v] of Object.entries(bodyMap)) {
    if (skipKeys.has(k)) continue;
    const val = v != null ? String(v).trim() : '';
    if (val !== '') lines.push(`${k}: ${val}`);
  }
  return lines;
}

export async function buildFullSummaryForBlock(blockId, userbook, opts) {
  const { inferenceResult, model_id, metadata = {}, userText = '' } = opts || {};
  const parts = [];
  try {
    const content = await readMetadataFile(blockId + '.txt', userbook);
    const parsed = parseBlockFileContent(content);
    const bodyLines = formatBlockBodyForSummary(parsed.bodyMap);
    if (bodyLines.length > 0) parts.push(bodyLines.join('\n'));
  } catch (e) {
    console.warn('[buildFullSummaryForBlock] 读取块 body 失败:', blockId, e);
  }
  if (model_id === '4001') {
    const taskType = metadata.task_type || (inferenceResult && inferenceResult.task_type) || '';
    if (taskType) parts.push(`task_type: ${taskType}`);
    parts.push(buildSummaryFromInferenceResult(inferenceResult));
  } else if (model_id === '4002') {
    const metaParts = [];
    if (metadata.gender) metaParts.push(`Gender: ${metadata.gender}`);
    if (metadata.age) metaParts.push(`Age: ${metadata.age}`);
    if (metadata.symptoms) metaParts.push(`Symptoms: ${metadata.symptoms}`);
    const questionLine = metaParts.length > 0 ? `${metaParts.join('. ')}. ${userText}`.trim() : (userText || '').trim();
    if (questionLine) parts.push(`问题: ${questionLine}`);
    const res = inferenceResult && (inferenceResult.result || inferenceResult);
    const answer = (res && (res.answer || (res.result && res.result.answer))) || '';
    if (answer) parts.push(`回答: ${answer}`);
  } else {
    parts.push(buildSummaryFromInferenceResult(inferenceResult));
  }
  return parts.filter(Boolean).join('\n');
}

export async function saveAudioBlockSummary(blockId, summaryText, userbook) {
  const url = `${API_BASE_URL}/api/save_audio_block_summary`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      userbook: userbook || '',
      block_id: blockId || '',
      summary_text: summaryText != null ? String(summaryText) : ''
    })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.msg || res.statusText || '保存 Summary 失败');
  }
  const data = await res.json().catch(() => ({}));
  if (data.error_num !== 0) throw new Error(data.msg || '保存 Summary 失败');
}

export async function readSummaryFileForBlockId(blockId, userbook) {
  if (!blockId || !userbook) return '';
  const url = `${API_BASE_URL}/api/get_audio_block_summary?userbook=${encodeURIComponent(userbook)}&block_id=${encodeURIComponent(blockId)}`;
  try {
    const res = await fetch(url);
    if (res.ok) return await res.text();
    return '';
  } catch (e) {
    console.warn('[readSummaryFileForBlockId]', blockId, e);
    return '';
  }
}

const SHORT_TERM_BLOCK_ID_REGEX = /^(.+)_(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2})$/;

export function formatBlockIdAsDate(blockId) {
  if (!blockId || typeof blockId !== 'string') return blockId || '';
  const m = blockId.match(SHORT_TERM_BLOCK_ID_REGEX);
  if (!m) return blockId;
  const userId = m[1];
  const parts = m[2].split('_');
  if (parts.length !== 6) return blockId;
  const [y, mo, d, h, mi, s] = parts;
  return `用户 ${userId}，${y}年${mo}月${d}日 ${h}点${mi}分${s}秒`;
}

export async function listAudioBlockSummaries(userbook) {
  if (!userbook) return [];
  const url = `${API_BASE_URL}/api/list_audio_block_summaries?userbook=${encodeURIComponent(userbook)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return [];
    const data = await res.json();
    return (data && data.block_ids) || [];
  } catch (e) {
    console.warn('[listAudioBlockSummaries]', e);
    return [];
  }
}

export async function getPreviousBlockIdsByPrevHash(currentBlockId, userbook, limit = 3) {
  const list = [];
  let nextBlockId = currentBlockId;
  const seen = new Set();
  for (let i = 0; i < limit; i++) {
    try {
      const content = await readMetadataFile(nextBlockId + '.txt', userbook);
      const parsed = parseBlockFileContent(content);
      const prevHash = (parsed.prevHash || '').trim();
      if (!prevHash || prevHash.toUpperCase() === 'NULL') break;
      if (prevHash.endsWith('_LONG')) break;
      if (seen.has(prevHash)) break;
      seen.add(prevHash);
      list.push(prevHash);
      nextBlockId = prevHash;
    } catch (e) {
      console.warn('[回溯 Prev_Hash] 读取块失败:', nextBlockId, e);
      break;
    }
  }
  return list.reverse();
}

export async function getPreviousBlockIdsByDate(currentBlockId, userbook, limit = 3) {
  const allIds = await listAudioBlockSummaries(userbook);
  const prefix = getLongTermUserIdFromAudioOrBlockName(currentBlockId);
  if (!prefix) return [];

  // 从 block_id 直接解析时间戳，保证“时间顺序”且不依赖 currentBlockId 是否存在于 summary 列表里
  const curMatch = currentBlockId && currentBlockId.match(SHORT_TERM_BLOCK_ID_REGEX);
  const curTs = curMatch ? curMatch[2] : null;

  const sameUser = allIds.filter(
    id => (id === currentBlockId || id.startsWith(prefix + '_')) && !id.endsWith('_LONG')
  );

  if (curTs) {
    const candidates = sameUser
      .map(id => {
        const m = id.match(SHORT_TERM_BLOCK_ID_REGEX);
        return m ? { id, ts: m[2] } : null;
      })
      .filter(Boolean)
      .filter(x => x.ts && x.ts < curTs)
      .sort((a, b) => (a.ts || '').localeCompare(b.ts || ''))
      .map(x => x.id);

    // 不强行补满；只返回最多 limit 个，且顺序严格按时间（旧 -> 新）
    return candidates.slice(Math.max(0, candidates.length - limit));
  }

  // fallback：保持旧逻辑（按列表排序取 idx-limit..idx）
  const sorted = sameUser.sort((a, b) => {
    const ma = a.match(SHORT_TERM_BLOCK_ID_REGEX);
    const mb = b.match(SHORT_TERM_BLOCK_ID_REGEX);
    if (!ma || !mb) return 0;
    return (ma[2] || '').localeCompare(mb[2] || '');
  });
  const idx = sorted.indexOf(currentBlockId);
  if (idx <= 0) return [];
  const start = Math.max(0, idx - limit);
  return sorted.slice(start, idx);
}

export async function getPreviousBlockIdsForBacktrack(currentBlockId, userbook, limit = 3) {
  const byDate = await getPreviousBlockIdsByDate(currentBlockId, userbook, limit);
  if (byDate.length > 0) return byDate;

  // fallback：prev_hash 可能不是时间顺序，因此对结果再按 block_id 时间戳排序/过滤
  const byPrevHash = await getPreviousBlockIdsByPrevHash(currentBlockId, userbook, limit);
  if (byPrevHash.length === 0) return [];

  const curMatch = currentBlockId && currentBlockId.match(SHORT_TERM_BLOCK_ID_REGEX);
  const curTs = curMatch ? curMatch[2] : null;

  const filtered = curTs
    ? byPrevHash.filter(id => {
      const m = id.match(SHORT_TERM_BLOCK_ID_REGEX);
      return m && m[2] && m[2] < curTs;
    })
    : byPrevHash.slice();

  filtered.sort((a, b) => {
    const ma = a.match(SHORT_TERM_BLOCK_ID_REGEX);
    const mb = b.match(SHORT_TERM_BLOCK_ID_REGEX);
    return (ma?.[2] || '').localeCompare(mb?.[2] || '');
  });

  return filtered.slice(Math.max(0, filtered.length - limit));
}

export async function fetchMemoryTierContext(userbook, userId) {
  if (!userbook || !userId) return { long_narrative: '', mid_excerpts: [] };
  const url = `${API_BASE_URL}/api/get_memory_tier_context?userbook=${encodeURIComponent(userbook)}&user_id=${encodeURIComponent(userId)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return { long_narrative: '', mid_excerpts: [] };
    const data = await res.json().catch(() => ({}));
    return {
      long_narrative: (data && data.long_narrative) || '',
      mid_excerpts: Array.isArray(data && data.mid_excerpts) ? data.mid_excerpts : []
    };
  } catch (e) {
    console.warn('[fetchMemoryTierContext]', e);
    return { long_narrative: '', mid_excerpts: [] };
  }
}

export async function getBacktrackHistoryPrompt(userbook, previousBlockIds, currentBlockId) {
  const longTermUid = currentBlockId ? getLongTermUserIdFromAudioOrBlockName(currentBlockId) : null;
  let tierHeader = '';
  let hasMidMemory = false;

  if (longTermUid) {
    const tier = await fetchMemoryTierContext(userbook, longTermUid);
    const midList = (tier.mid_excerpts || []).filter(
      ex => ex != null && String(ex).trim() !== ''
    );
    hasMidMemory = midList.length > 0;
    const parts = [];
    if (tier.long_narrative && String(tier.long_narrative).trim()) {
      parts.push(`长期记忆档案（模型整理）：\n${String(tier.long_narrative).trim()}`);
    }
    if (hasMidMemory) {
      const midLines = midList.map((ex, i) => `（${i + 1}）${String(ex).trim()}`);
      parts.push(`近期中期记忆（模型整理）：\n${midLines.join('\n')}`);
    }
    if (parts.length) tierHeader = parts.join('\n\n') + '\n\n';
  }

  // 已有中期记忆时只用长+中期，不再拼接短期块「回溯历史」
  if (hasMidMemory) {
    return tierHeader;
  }

  const filtered = (previousBlockIds || []).filter(id => !id.endsWith('_LONG'));
  if (filtered.length === 0) {
    return tierHeader;
  }
  const lines = ['回溯历史：'];
  for (let i = 0; i < filtered.length; i++) {
    const blockId = filtered[i];
    const summary = await readSummaryFileForBlockId(blockId, userbook);
    const dateLabel = formatBlockIdAsDate(blockId);
    lines.push(`[${i + 1}] ${dateLabel}`);
    lines.push(summary ? `Summary: ${summary.trim()}` : 'Summary: （暂无）');
  }
  lines.push('');
  return tierHeader + lines.join('\n');
}

export async function loadAudioMetadata(audioFileName, fileNameList, userId) {
  let metadata = {};
  try {
    const metadataFileName = findMetadataFile(audioFileName, fileNameList);
    if (metadataFileName) {
      const metadataContent = await readMetadataFile(metadataFileName, userId);
      metadata = parseMetadataFromText(metadataContent);
    }
  } catch (error) {
    console.warn('加载元数据失败:', error);
  }
  return metadata;
}

export function uploadAudioForAnalysis(params) {
  const formData = new FormData();
  formData.append('audio', params.audioFile);
  formData.append('task_type', params.task_type);
  formData.append('modality', params.modality);
  if (params.metadata && Object.keys(params.metadata).length > 0) {
    formData.append('metadata', JSON.stringify(params.metadata));
  }
  formData.append('return_probs', params.return_probs !== undefined ? params.return_probs.toString() : 'true');
  return axios.post(AUDIO_ANALYSIS_API_URL, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  }).then(response => response.data || response).catch(error => {
    console.error('音频分析API调用失败:', error);
    if (error.response) throw new Error(error.response.data?.message || error.response.data?.msg || '服务器错误');
    if (error.request) throw new Error('网络请求失败，请检查网络连接');
    throw new Error(error.message || '未知错误');
  });
}

function getTaskTypeName(taskType) {
  const map = {
    'covid': 'COVID-19检测',
    'copd': 'COPD检测',
    'smoker': '吸烟者检测',
    'asthma': '哮喘检测',
    'obstructive': '阻塞性疾病检测'
  };
  return map[taskType] || taskType;
}

function getModalityName(modality) {
  const map = {
    'cough': '咳嗽声',
    'breath': '呼吸声',
    'lung': '肺部声音'
  };
  return map[modality] || modality;
}

export function formatAnalysisResultAsPrompt(analysisResult) {
  let data = analysisResult;
  if (analysisResult && analysisResult.data) data = analysisResult.data;
  if (!data) return '';
  let result = null;
  let metadata = {};
  let taskType = '';
  let modality = '';
  let audioFilename = '';
  if (data.result) {
    result = data.result;
    if (data.metadata) metadata = data.metadata;
    if (data.task_type) taskType = data.task_type;
    if (data.modality) modality = data.modality;
    if (data.audio_filename) audioFilename = data.audio_filename;
  } else if (data.prediction_result) {
    result = data.prediction_result;
    metadata = data.metadata || {};
    taskType = data.task_type || '';
    modality = data.modality || '';
    audioFilename = data.audio_filename || '';
  } else if (data.prediction || data.confidence !== undefined) {
    result = data;
    metadata = data.metadata || {};
    taskType = data.task_type || '';
    modality = data.modality || '';
    audioFilename = data.audio_filename || '';
  } else {
    return '';
  }
  if (!result) return '';
  let prompt = '\n\n=== 音频分析结果 ===\n';
  if (taskType) prompt += `任务类型: ${getTaskTypeName(taskType)}\n`;
  if (modality) prompt += `音频模态: ${getModalityName(modality)}\n`;
  if (audioFilename) prompt += `音频文件名: ${audioFilename}\n`;
  if (taskType || modality || audioFilename) prompt += '\n';
  if (metadata && Object.keys(metadata).length > 0) {
    prompt += '--- 用户信息 ---\n';
    if (metadata.gender) prompt += `性别: ${metadata.gender}\n`;
    if (metadata.age) prompt += `年龄: ${metadata.age}\n`;
    if (metadata.symptoms) prompt += `症状: ${metadata.symptoms}\n`;
    if (metadata.medhistory) prompt += `病史: ${metadata.medhistory}\n`;
    prompt += '\n';
  }
  prompt += '--- 预测结果 ---\n';
  if (result.prediction) prompt += `预测: ${result.prediction}\n`;
  if (result.confidence !== undefined) prompt += `置信度: ${(result.confidence * 100).toFixed(2)}%\n`;
  if (result.explanation) prompt += `解释: ${result.explanation}\n`;
  if (result.recommendation) prompt += `\n--- 建议 ---\n${result.recommendation}\n`;
  prompt += '\n=== 以上为音频分析结果，请在回答用户问题时参考这些信息 ===\n\n';
  return prompt;
}
