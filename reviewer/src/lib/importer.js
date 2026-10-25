import JSZip from 'jszip'
import { classifyArtifact, extractPageNumber, normalizePath } from './artifacts.js'

function createId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function baseName(path) {
  return normalizePath(path).split('/').pop() || ''
}

function withoutExtension(name) {
  return name.replace(/\.[^.]+$/, '')
}

function samplePrefixForManifest(path, manifest) {
  const parts = normalizePath(path).split('/')
  let directoryIndex = Math.max(0, parts.length - 2)
  const groupIndex = parts.findIndex(part => part === manifest.group_id)
  if (groupIndex >= 0) directoryIndex = groupIndex
  if (directoryIndex > 0 && parts[directoryIndex - 1].startsWith('批改记录_')) directoryIndex -= 1
  return parts.slice(0, directoryIndex + 1).join('/')
}

function relativeToPrefix(path, prefix) {
  const normalized = normalizePath(path)
  if (!prefix) return normalized
  if (normalized === prefix) return baseName(normalized)
  return normalized.startsWith(`${prefix}/`) ? normalized.slice(prefix.length + 1) : null
}

function knownSamplesMap(builtinRuns) {
  const map = new Map()
  for (const run of builtinRuns || []) {
    for (const sample of run.samples || []) {
      if (!map.has(sample.groupId)) map.set(sample.groupId, sample)
    }
  }
  return map
}

function bestPdf(files, manifest, known) {
  const pdfs = files.filter(file => file.path.toLowerCase().endsWith('.pdf'))
  const selected = (manifest.selected_files || [])[0] || ''
  const direct = pdfs.find(file => baseName(file.path) === selected)
  if (direct) return direct
  if (known?.pdf?.name) {
    const knownMatch = pdfs.find(file => baseName(file.path) === known.pdf.name)
    if (knownMatch) return knownMatch
  }
  return pdfs.length === 1 ? pdfs[0] : null
}

async function readManifest(file) {
  try {
    return { value: JSON.parse(await file.blob.text()), error: null }
  } catch (error) {
    return { value: null, error: error.message }
  }
}

export function normalizeImportedPath(path) {
  return normalizePath(path)
}

export async function filesFromFileList(fileList) {
  return Array.from(fileList || []).map(file => ({
    path: normalizePath(file.webkitRelativePath || file.name),
    blob: file,
    name: file.name,
    type: file.type,
    size: file.size,
  }))
}

export async function filesFromZip(zipFile) {
  const zip = await JSZip.loadAsync(zipFile)
  const output = []
  for (const [rawPath, item] of Object.entries(zip.files)) {
    if (item.dir) continue
    const path = normalizePath(rawPath)
    if (!path) continue
    const blob = await item.async('blob')
    output.push({ path, blob, name: baseName(path), type: blob.type, size: blob.size })
  }
  return output
}

export async function buildImportedDataset(name, rawFiles, builtinRuns = []) {
  const datasetId = `dataset-${createId()}`
  const runId = `import-${createId()}`
  const known = knownSamplesMap(builtinRuns)
  const files = rawFiles
    .map(file => ({ ...file, path: normalizePath(file.path) }))
    .filter(file => file.path && file.blob)
  const manifestCandidates = files.filter(file => baseName(file.path).toLowerCase() === 'manifest.json')
  const parsed = []
  const parseErrors = []
  for (const file of manifestCandidates) {
    const result = await readManifest(file)
    if (result.value?.group_id) parsed.push({ file, manifest: result.value })
    else parseErrors.push({ path: file.path, error: result.error || 'manifest 缺少 group_id' })
  }
  if (!parsed.length) throw new Error('未找到可识别的 manifest.json（需要包含 group_id）')

  const bestByGroup = new Map()
  for (const item of parsed) {
    const current = bestByGroup.get(item.manifest.group_id)
    if (!current || item.file.path.length < current.file.path.length) bestByGroup.set(item.manifest.group_id, item)
  }

  const storedFiles = []
  const samples = []
  for (const { file: manifestFile, manifest } of bestByGroup.values()) {
    const prefix = samplePrefixForManifest(manifestFile.path, manifest)
    const sampleFiles = files.filter(candidate => relativeToPrefix(candidate.path, prefix) != null)
    const knownSample = known.get(manifest.group_id)
    const selectedPdf = bestPdf(files, manifest, knownSample)
    const displayFromPrefix = baseName(prefix).replace(/^批改记录_/, '')
    const selectedName = withoutExtension((manifest.selected_files || [])[0] || '')
    const displayName = knownSample?.displayName || displayFromPrefix || selectedName || manifest.group_id
    const entries = []

    for (const candidate of sampleFiles) {
      const relativePath = relativeToPrefix(candidate.path, prefix)
      const storageKey = `${datasetId}:${candidate.path}`
      entries.push({
        id: `${runId}:${manifest.group_id}:${relativePath}`,
        runId,
        sampleId: manifest.group_id,
        datasetId,
        storageKey,
        name: baseName(candidate.path),
        relativePath,
        extension: `.${baseName(candidate.path).split('.').pop()}`.toLowerCase(),
        size: candidate.size,
        type: candidate.type,
        stage: classifyArtifact(relativePath),
        page: extractPageNumber(relativePath),
        source: 'imported',
      })
      storedFiles.push({
        storageKey,
        datasetId,
        blob: candidate.blob,
        name: baseName(candidate.path),
        type: candidate.type,
        size: candidate.size,
        relativePath: candidate.path,
      })
    }

    let pdf = knownSample?.pdf ? { ...knownSample.pdf } : null
    if (selectedPdf) {
      const storageKey = `${datasetId}:${selectedPdf.path}`
      if (!storedFiles.some(item => item.storageKey === storageKey)) {
        storedFiles.push({
          storageKey,
          datasetId,
          blob: selectedPdf.blob,
          name: baseName(selectedPdf.path),
          type: selectedPdf.type || 'application/pdf',
          size: selectedPdf.size,
          relativePath: selectedPdf.path,
        })
      }
      pdf = { name: baseName(selectedPdf.path), source: 'imported', storageKey, datasetId }
    }

    samples.push({
      id: manifest.group_id,
      groupId: manifest.group_id,
      displayName,
      sourceFileName: (manifest.selected_files || [])[0] || pdf?.name || '',
      subject: manifest.subject || knownSample?.subject || 'unknown',
      subjectLabel: manifest.subject_label || knownSample?.subjectLabel || '未知学科',
      pageCount: (manifest.input_units || []).length || knownSample?.pageCount || 0,
      createdAt: manifest.created_at || null,
      updatedAt: manifest.updated_at || new Date().toISOString(),
      manifestPath: relativeToPrefix(manifestFile.path, prefix),
      pdf,
      files: entries,
      importWarnings: pdf ? [] : ['未找到原始 PDF，可继续查看阶段文件并在后续导入中补充。'],
    })
  }

  const totalSize = storedFiles.reduce((sum, file) => sum + (file.size || 0), 0)
  const run = {
    id: runId,
    name,
    shortName: name,
    source: 'imported',
    datasetId,
    files: [],
    samples,
  }
  const dataset = {
    id: datasetId,
    name,
    createdAt: new Date().toISOString(),
    totalSize,
    parseErrors,
    runs: [run],
  }
  return { dataset, storedFiles }
}
