import { API_BASE_URL } from '@/config/apiConfig'
import {
  autoIterateCIReproductionRound,
  evaluateCIDRegionConfidenceBatch,
  getCIDRegionConfidenceResult,
  getCIOverlayHistory,
  getCIOverlayStatus,
  getCIResult,
  markCIAutoIterateRegionsUsed,
  pickCIAutoIterateRegionsByConfidence,
  previewCIAutoIterateReproductionRound,
  recognizeCIDRegion,
  generateCIOverlay,
} from '@/api/continuous_image'

async function readPromptStream(username, analysisId, unitId, includeTmContext = true) {
  const res = await fetch(`${API_BASE_URL}/api/ci/overlay/prompt_stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username,
      analysis_id: analysisId,
      unit_id: unitId,
      include_tm_context: includeTmContext,
    }),
  })
  if (!res.ok || !res.body || !res.body.getReader) {
    throw new Error('overlay_prompt_stream_failed')
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let text = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    text += decoder.decode(value, { stream: true })
  }
  text += decoder.decode()
  return text
}

export const CIWorkflowInterface = {
  async dmtPromptGenerate({ username, analysisId, unitId, includeTmContext = true }) {
    const instructionText = await readPromptStream(username, analysisId, unitId, includeTmContext)
    return { instructionText, includeTmContext }
  },

  async overlayGenerate({ username, analysisId, unitId, instructionText, includeTmContext = true, dmtGenerated = false, referenceImage, imageQuality = 'normal' }) {
    return generateCIOverlay({
      username,
      analysis_id: analysisId,
      unit_id: unitId,
      instruction_text: instructionText || '',
      include_tm_context: includeTmContext,
      dmt_generated: !!dmtGenerated,
      reference_image: referenceImage,
      image_quality: imageQuality,
    })
  },

  async overlayStatus({ username, analysisId, unitId }) {
    return getCIOverlayStatus({ username, analysis_id: analysisId, unit_id: unitId })
  },

  async overlayResult({ username, analysisId, unitId }) {
    return getCIOverlayHistory({ username, analysis_id: analysisId, unit_id: unitId })
  },

  async confidenceEvaluate({ username, analysisId, unitId }) {
    return evaluateCIDRegionConfidenceBatch({ username, analysis_id: analysisId, unit_id: unitId })
  },

  async confidenceResult({ username, analysisId, unitId }) {
    return getCIDRegionConfidenceResult({ username, analysis_id: analysisId, unit_id: unitId })
  },

  async confidencePickAutoRegions({ username, analysisId, unitId, limit = 9 }) {
    return pickCIAutoIterateRegionsByConfidence({ username, analysis_id: analysisId, unit_id: unitId, limit })
  },

  async autoIterMarkUsed({ username, analysisId, unitId, regionIds, status = 'success', note = '' }) {
    return markCIAutoIterateRegionsUsed({
      username,
      analysis_id: analysisId,
      unit_id: unitId,
      region_ids: regionIds || [],
      status,
      note,
    })
  },

  async autoIterateManual({ username, analysisId, unitId, selectedRegionIds, imageQuality = 'normal', iterContext, sketchPreprocess = false, useRecognitionContext = false }) {
    return autoIterateCIReproductionRound({
      username,
      analysis_id: analysisId,
      unit_id: unitId,
      mode: 'full',
      selected_region_ids: selectedRegionIds || [],
      continue_from_cursor: false,
      image_quality: imageQuality,
      iter_context: iterContext,
      sketch_preprocess: !!sketchPreprocess,
      use_recognition_context: !!useRecognitionContext,
    })
  },

  async autoIterateAutoPick({ username, analysisId, unitId, imageQuality = 'normal', iterContext, sketchPreprocess = false, useRecognitionContext = false, limit = 9 }) {
    const pickResp = await pickCIAutoIterateRegionsByConfidence({ username, analysis_id: analysisId, unit_id: unitId, limit })
    const pickData = pickResp?.data || pickResp
    const ids = Array.isArray(pickData?.selected_region_ids) ? pickData.selected_region_ids : []
    if (!ids.length) return { pick: pickResp, run: null }
    const run = await this.autoIterateManual({
      username,
      analysisId,
      unitId,
      selectedRegionIds: ids,
      imageQuality,
      iterContext,
      sketchPreprocess,
      useRecognitionContext,
    })
    return { pick: pickResp, run }
  },

  async recognitionOnlyManual({ username, analysisId, unitId, selectedRegionIds, sketchPreprocess = false, useRecognitionContext = false }) {
    return previewCIAutoIterateReproductionRound({
      username,
      analysis_id: analysisId,
      unit_id: unitId,
      mode: 'full',
      selected_region_ids: selectedRegionIds || [],
      sketch_preprocess: !!sketchPreprocess,
      use_recognition_context: !!useRecognitionContext,
    })
  },

  async recognitionOnlyAutoPick({ username, analysisId, unitId, sketchPreprocess = false, useRecognitionContext = false, limit = 9 }) {
    const pickResp = await pickCIAutoIterateRegionsByConfidence({ username, analysis_id: analysisId, unit_id: unitId, limit })
    const pickData = pickResp?.data || pickResp
    const ids = Array.isArray(pickData?.selected_region_ids) ? pickData.selected_region_ids : []
    if (!ids.length) return { pick: pickResp, preview: null }
    const preview = await this.recognitionOnlyManual({
      username,
      analysisId,
      unitId,
      selectedRegionIds: ids,
      sketchPreprocess,
      useRecognitionContext,
    })
    return { pick: pickResp, preview }
  },

  async singleRegionRecognitionProbe({ username, analysisId, unitId, regionId, sketchPreprocess = false, useRecognitionContext = false, previewOnly = false }) {
    return recognizeCIDRegion({
      username,
      analysis_id: analysisId,
      unit_id: unitId,
      region_id: regionId,
      sketch_preprocess: !!sketchPreprocess,
      use_recognition_context: !!useRecognitionContext,
      preview_only: !!previewOnly,
    })
  },

  async analysisBundle({ username, analysisId }) {
    return getCIResult({ username, analysis_id: analysisId })
  },
}

export default CIWorkflowInterface
