import request from '@/utils/request'

export function feedbackMaterialSettings(data) {
  return request.post('/api/ci/material-settings', data)
}

/**
 * 连续图片认知无损理解 API（新架构）
 */

/** 查询记录及服务端材料解析；支持 requested_action / feedback_overrides。 */
export function queryCIAnalyses(data) {
  return request.post('/api/ci/query', data)
}

/** 启动分析；响应保留冻结 feedback_context、config_fingerprint、run_id 和 warnings。 */
export function startCIAnalysis(data) {
  return request.post('/api/ci/start', data)
}

/** 材料表单只消费服务端解析，不在浏览器重复解析文件名。 */
export function queryFeedbackMaterial(data) {
  return queryCIAnalyses({ ...data, requested_action: 'grading' })
}

export function startHomeworkFeedback(data) {
  return startCIAnalysis({ ...data, requested_action: 'grading' })
}

/** 显式图片理解不受已有作业分类缓存影响。 */
export function startImageUnderstanding(data) {
  return startCIAnalysis({ ...data, requested_action: 'understanding' })
}

/** 轮询分析进度 */
export function getCIProgress(taskId) {
  return request.get(`/api/ci/progress/${taskId}/`)
}

/** 按 analysis_id 获取结果 { username, analysis_id, run_id? } */
export function getCIResult(data) {
  return request.post('/api/ci/result', data)
}

/** 列出作业批改历史版本 { username, analysis_id } */
export function listCIHomeworkVersions(data) {
  return request.post('/api/ci/homework/versions', data)
}

/** 设置关键历史版本 { username, analysis_id, run_id, is_key } */
export function markCIHomeworkVersionKey(data) {
  return request.post('/api/ci/homework/version_key', data)
}

/** 默认继承原快照。材料/资料/配置变更只能完整新跑，不与session_ids/resume混用。
 * 旧快照需 full_recompute；curriculum_selection 仅auto或null；refresh_configuration显式刷新。
 */
export function rerunCIHomework(data) {
  return request.post('/api/ci/homework/rerun', data)
}

/** 仅重试当前作业版本的红蓝卡标评分 */
export function retryCIHomeworkRedBlue(data) {
  return request.post('/api/ci/homework/red_blue/retry', data)
}

/** 迭代理解层（不迭代 D 层 OCR）{ username, analysis_id, redo_scope?: 'mt'|'t' } */
export function redoCIAnalysis(data) {
  return request.post('/api/ci/redo', data)
}

/** 列出可进行双科交叉诊断的候选配对 { username } */
export function listCIPass3Pairs(data) {
  return request.post('/api/ci/pass3/pairs', data)
}

/** 启动双科交叉诊断（Pass3）{ username, analysis_id_a, analysis_id_b } */
export function startCIPass3(data) {
  return request.post('/api/ci/pass3/start', data)
}

/** 仅生成/补生成复现图 { username, analysis_id, force_rebuild?, use_sketch_input?, use_original_sketch_as_r? } */
export function startCIReproduction(data) {
  return request.post('/api/ci/reproduction/start', data)
}

/** 无完整 M/T 理解时原草图直出 R { username, files } */
export function startCISketchRQuickstart(data) {
  return request.post('/api/ci/sketch_r/quickstart', data)
}

/** 保存R层单页生成依据 { username, analysis_id, unit_id, iter_context } */
export function updateCIReproductionContext(data) {
  return request.post('/api/ci/reproduction/update_context', data)
}

/** 启动R层单页图片迭代 { username, analysis_id, unit_id, revision_instruction?, reference_image?, image_quality?, iter_context? } */
export function iterateCIReproductionUnit(data) {
  return request.post('/api/ci/reproduction/iterate', data)
}

/** 启动基于覆盖层版面的R层单页定向迭代 { username, analysis_id, unit_id, selected_regions, iteration_mode?, reference_image?, image_quality?, iter_context? } */
export function iterateCIReproductionLayoutRegions(data) {
  return request.post('/api/ci/reproduction/iterate_layout_regions', data)
}

/** 预览基于D版面的单图自动迭代识别结果 { username, analysis_id, unit_id, selected_region_ids, mode? } */
export function previewCIAutoIterateReproductionRound(data) {
  return request.post('/api/ci/reproduction/auto_iterate_preview', data)
}

/** 启动基于D版面的单图自动迭代轮次 { username, analysis_id, unit_id, mode?, selected_region_ids?, gray_resolutions?, start_region_id?, continue_from_cursor?, image_quality?, iter_context? } */
export function autoIterateCIReproductionRound(data) {
  return request.post('/api/ci/reproduction/auto_iterate_round', data)
}

/** 将已保存的轻量 D 区识字结果贴补到当前 R 层复现图 */
export function applyCILiteBundleToReproduction(data) {
  return request.post('/api/ci/reproduction/apply_lite_bundle', data)
}

/** 单 D 版面 Gemini+Qwen 识字预览，后端写入 ci_audit/d_region_recognition_audit.jsonl */
export function recognizeCIDRegion(data) {
  return request.post('/api/ci/reproduction/recognize_d_region', data)
}

/** 批量评估 D 区字迹识别置信度（D1为参照） */
export function evaluateCIDRegionConfidenceBatch(data) {
  return request.post('/api/ci/reproduction/d_confidence_batch', data)
}

/** 读取已保存的 D 区字迹识别置信度结果 */
export function getCIDRegionConfidenceResult(params) {
  return request.get('/api/ci/reproduction/d_confidence_result', { params })
}

/** 按置信度自动挑选用于全自动迭代的D区 */
export function pickCIAutoIterateRegionsByConfidence(params) {
  return request.get('/api/ci/reproduction/d_confidence_pick_auto_regions', { params })
}

/** 记录自动挑选D区是否成功完成迭代 */
export function markCIAutoIterateRegionsUsed(data) {
  return request.post('/api/ci/reproduction/d_confidence_mark_used', data)
}

/** 回滚R层单页复现图到上一版本 { username, analysis_id, unit_id } */
export function rollbackCIReproductionUnit(data) {
  return request.post('/api/ci/reproduction/rollback', data)
}

/** 保存R层单页手工编辑后的复现图 { username, analysis_id, unit_id, reproduction_image } */
export function saveCIReproduction(data) {
  return request.post('/api/ci/reproduction/save', data)
}

/** 仅估算原草图手写区域占比并写入 overlay_layer（可选；DMT 流式会读取 ci_dmt_coarse_layout） */
export function estimateCIOverlayHandwriting(data) {
  return request.post('/api/ci/overlay/estimate_handwriting', data)
}

export function generateCIOverlay(data) {
  return request.post('/api/ci/overlay/generate', data)
}

export function getCIOverlayStatus(params) {
  return request.get('/api/ci/overlay/status', { params })
}

export function getCIOverlayHistory(params) {
  return request.get('/api/ci/overlay/history', { params })
}

export function saveCIOverlay(data) {
  return request.post('/api/ci/overlay/save', data)
}

export function iterateCIOverlay(data) {
  return request.post('/api/ci/overlay/iterate', data)
}

/** 查询 PDF 页数 { username, filename } */
export function getCIPdfPageCount(data) {
  return request.post('/api/ci/pdf_page_count', data)
}

/** 单图：更新完善整体纪要(T层) */
export function refineCISingleTLayer(data) {
  return request.post('/api/ci/single/refine_t_layer', data)
}

/** 单图：回退整体纪要(T层)到上一版 */
export function rollbackCISingleTLayer(data) {
  return request.post('/api/ci/single/refine_t_layer_rollback', data)
}

/** 单图：更新完善原图片三层理解（预览，不落库） */
export function previewRefineCISingleImageUnderstanding(data) {
  return request.post('/api/ci/single/refine_image_understanding_preview', data)
}

/** 单图：确认写入更新后的原图片三层理解（更新向量库） */
export function applyRefineCISingleImageUnderstanding(data) {
  return request.post('/api/ci/single/refine_image_understanding_apply', data)
}

/** 单图：基于轻量 D 识字预览 / 确认写入整体纪要(T层)（校正路径，不影响「按R层更新T」） */
export function previewRefineCISingleTLayerFromDLite(data) {
  return request.post('/api/ci/single/refine_t_layer_from_d_lite_preview', data)
}

export function applyRefineCISingleTLayerFromDLite(data) {
  return request.post('/api/ci/single/refine_t_layer_from_d_lite_apply', data)
}

/** 单图：基于轻量 D 识字预览三层理解（确认写入仍用 applyRefineCISingleImageUnderstanding） */
export function previewRefineCISingleImageUnderstandingFromDLite(data) {
  return request.post('/api/ci/single/refine_image_understanding_preview_from_d_lite', data)
}

/** 读取近两日（当日或前一日）轻量 D 三层理解预览缓存（批量自动化预生成） */
export function getCIDLiteImageUnderstandingPreviewCache(data) {
  return request.post('/api/ci/single/d_lite_image_understanding_preview_cache', data)
}

// ── 旧架构兼容（保留，供旧代码调用）──────────────────────────

export function startContinuousImageAnalysis(data) {
  return request.post('/api/start_continuous_image_analysis', data)
}

export function getContinuousImageAnalysisProgress(taskId) {
  return request.get(`/api/continuous_image_analysis_progress/${taskId}/`)
}

export function getContinuousImageAnalysisResult(data) {
  return request.post('/api/get_continuous_image_analysis_result', data)
}
