import { cp, mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { classifyArtifact, extractPageNumber, normalizePath } from '../src/lib/artifacts.js'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const projectDir = path.resolve(scriptDir, '..')
const repoDir = path.resolve(projectDir, '..')
const sourceRound1 = path.join(repoDir, '连续图片批改测试')
const sourceRound2 = path.join(repoDir, '连续图片批改测试2', '测试结果')
const sourceInputs = path.join(sourceRound1, '测试文件')
const targetRoot = path.join(projectDir, 'public', 'builtin')

function assertInsideProject(target) {
  const relative = path.relative(projectDir, target)
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error(`拒绝写入项目外路径: ${target}`)
  }
}

async function exists(target) {
  try {
    await stat(target)
    return true
  } catch {
    return false
  }
}

async function findFiles(root) {
  const output = []
  async function walk(current) {
    const entries = await readdir(current, { withFileTypes: true })
    for (const entry of entries) {
      const fullPath = path.join(current, entry.name)
      if (entry.isDirectory()) await walk(fullPath)
      else if (entry.isFile()) output.push(fullPath)
    }
  }
  await walk(root)
  return output
}

async function loadJson(target) {
  return JSON.parse(await readFile(target, 'utf8'))
}

async function findManifest(sampleRoot) {
  const files = (await findFiles(sampleRoot)).filter(file => path.basename(file) === 'manifest.json')
  files.sort((a, b) => a.length - b.length)
  return files[0]
}

async function fileEntries(root, publicBase, runId, sampleId) {
  const files = await findFiles(root)
  return Promise.all(files.map(async file => {
    const relativePath = normalizePath(path.relative(root, file))
    const info = await stat(file)
    return {
      id: `${runId}:${sampleId}:${relativePath}`,
      runId,
      sampleId,
      name: path.basename(file),
      relativePath,
      extension: path.extname(file).toLowerCase(),
      size: info.size,
      stage: classifyArtifact(relativePath),
      page: extractPageNumber(relativePath),
      source: 'builtin',
      url: `${publicBase}/${relativePath}`,
    }
  }))
}

async function build() {
  for (const source of [sourceRound1, sourceRound2, sourceInputs]) {
    if (!(await exists(source))) throw new Error(`缺少源目录: ${source}`)
  }
  assertInsideProject(targetRoot)
  await rm(targetRoot, { recursive: true, force: true })
  await mkdir(targetRoot, { recursive: true })

  await cp(sourceInputs, path.join(targetRoot, 'inputs'), { recursive: true })
  await mkdir(path.join(targetRoot, 'round-1'), { recursive: true })
  await mkdir(path.join(targetRoot, 'round-2'), { recursive: true })

  for (const documentName of ['测试摘要.md', '分类错因补充说明.md']) {
    await cp(path.join(sourceRound1, documentName), path.join(targetRoot, 'round-1', documentName))
  }

  const round1Dirs = (await readdir(sourceRound1, { withFileTypes: true }))
    .filter(entry => entry.isDirectory() && entry.name.startsWith('批改记录_'))
    .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }))
  const groupMetadata = new Map()
  const round1Samples = []

  for (const entry of round1Dirs) {
    const source = path.join(sourceRound1, entry.name)
    const target = path.join(targetRoot, 'round-1', entry.name)
    await cp(source, target, { recursive: true })
    const manifestPath = await findManifest(target)
    const manifest = await loadJson(manifestPath)
    const displayName = entry.name.replace(/^批改记录_/, '')
    const pdfName = `${displayName}.pdf`
    groupMetadata.set(manifest.group_id, { displayName, pdfName })
    const files = await fileEntries(target, `/builtin/round-1/${entry.name}`, 'round-1', manifest.group_id)
    round1Samples.push({
      id: manifest.group_id,
      groupId: manifest.group_id,
      displayName,
      sourceFileName: (manifest.selected_files || [])[0] || pdfName,
      subject: manifest.subject,
      subjectLabel: manifest.subject_label,
      pageCount: (manifest.input_units || []).length,
      createdAt: manifest.created_at,
      updatedAt: manifest.updated_at,
      manifestPath: normalizePath(path.relative(target, manifestPath)),
      pdf: { name: pdfName, url: `/builtin/inputs/${pdfName}`, source: 'builtin' },
      files,
    })
  }

  const round2Dirs = (await readdir(sourceRound2, { withFileTypes: true }))
    .filter(entry => entry.isDirectory() && entry.name.startsWith('homework_'))
    .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }))
  const round2Samples = []

  for (const entry of round2Dirs) {
    const source = path.join(sourceRound2, entry.name)
    const target = path.join(targetRoot, 'round-2', entry.name)
    await cp(source, target, { recursive: true })
    const manifestPath = await findManifest(target)
    const manifest = await loadJson(manifestPath)
    const known = groupMetadata.get(manifest.group_id) || {}
    const displayName = known.displayName || `${manifest.subject_label || manifest.subject} · ${manifest.group_id.slice(-8)}`
    const pdfName = known.pdfName || `${displayName}.pdf`
    const files = await fileEntries(target, `/builtin/round-2/${entry.name}`, 'round-2', manifest.group_id)
    round2Samples.push({
      id: manifest.group_id,
      groupId: manifest.group_id,
      displayName,
      sourceFileName: (manifest.selected_files || [])[0] || pdfName,
      subject: manifest.subject,
      subjectLabel: manifest.subject_label,
      pageCount: (manifest.input_units || []).length,
      createdAt: manifest.created_at,
      updatedAt: manifest.updated_at,
      manifestPath: normalizePath(path.relative(target, manifestPath)),
      pdf: { name: pdfName, url: `/builtin/inputs/${pdfName}`, source: 'builtin' },
      files,
    })
  }

  const runDocs = []
  for (const name of ['测试摘要.md', '分类错因补充说明.md']) {
    const full = path.join(targetRoot, 'round-1', name)
    const info = await stat(full)
    runDocs.push({
      id: `round-1:doc:${name}`,
      name,
      relativePath: name,
      extension: '.md',
      size: info.size,
      stage: 'human',
      page: null,
      source: 'builtin',
      url: `/builtin/round-1/${name}`,
    })
  }

  const catalog = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    exclusions: ['黄金集结果'],
    runs: [
      { id: 'round-1', name: '连续图片批改测试 · 第一轮', shortName: '第一轮', source: 'builtin', files: runDocs, samples: round1Samples },
      { id: 'round-2', name: '连续图片批改测试2 · 第二轮', shortName: '第二轮', source: 'builtin', files: [], samples: round2Samples },
    ],
  }
  await writeFile(path.join(targetRoot, 'catalog.json'), `${JSON.stringify(catalog, null, 2)}\n`, 'utf8')

  const totalFiles = catalog.runs.flatMap(run => run.samples.flatMap(sample => sample.files)).length + runDocs.length
  console.log(`已同步 ${catalog.runs.length} 轮、${round1Samples.length + round2Samples.length} 个样本、${totalFiles} 个文件。`)
}

await build()
