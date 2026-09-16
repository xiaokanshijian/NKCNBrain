<template>
  <div>
    <div v-for="(item, index) in visibleMixedContent" :key="index">
      <template v-if="item.type === 'text'">
        <div :ref="'paragraph' + index" 
             @dblclick="startFromSelection($event, item.content, index)"
             @click="handleClick($event, item, index)"
             class="markdown-container">
          <div class="markdown-text">
            <span v-for="(char, charIndex) in item.content" 
                  :key="charIndex" 
                  :style="item.charStyles ? item.charStyles[charIndex] : getCharStyle(item.colors, charIndex)"
                  :class="item.charClasses ? item.charClasses[charIndex] : getCharClassWithModifyTag(char, charIndex, item.content, item.modifyTags)">
              {{ char }}
            </span>
          </div>
        </div>
      </template>
      <template v-else>
        <div ref="codeBlock" class="original-code-block">
          <button class="copy-button" @click="copyCode(item.content, $event)">复制内容</button>
          <pre><code>{{ item.content }}</code></pre>
        </div>
      </template>
    </div>
  </div>
</template>

<script>
export default {
  props: {
    answer: {
      type: String,
      required: false,
      default: ''
    }
  },
  data() {
    return {
      mixedContent: [],
      visibleMixedContent: [], // 🔥 分批渲染：只渲染可见的内容
      highlightedIndex: -1, // 当前高亮的字符起始位置
      highlightDuration: 15, // 高亮字符数
      isDoubleAble: true,   // 控制不可在高亮的2s内（html结构还未恢复）再次双击，避免错误
      lineTypes: {}, // 存储每行的类型，如 'heading-1', 'list-item' 等
      tableRanges: [], // 存储表格的范围 [{contentIndex, startLine, endLine}, ...]
      renderedTableSignatures: new Set(), // 新增：记录已渲染表格的签名
      renderedHRSignatures: new Set(), // 新增：记录已渲染分隔线的签名
      renderBatchSize: 2000, // 🔥 每批渲染的字符数
      renderDelay: 0 // 🔥 渲染延迟（毫秒），用于控制渲染速度
    };
  },
  mounted() {
    const perfStart = performance.now();
    console.log('[AnswerParser] 🚀 开始处理内容，长度:', this.answer.length);
    
    this.processAnswer();
    const processTime = performance.now() - perfStart;
    console.log('[AnswerParser] ⏱️ processAnswer 耗时:', processTime.toFixed(2), 'ms');
    
      this.$nextTick(() => {
        const nextTickStart = performance.now();
        
        const step1 = performance.now();
        this.identifyLineTypes();
        console.log('[AnswerParser] ⏱️ identifyLineTypes 耗时:', (performance.now() - step1).toFixed(2), 'ms');
        
        const step2 = performance.now();
        this.precomputeCharClasses(); // 预计算类名以提高性能
        console.log('[AnswerParser] ⏱️ precomputeCharClasses 耗时:', (performance.now() - step2).toFixed(2), 'ms');
        
        const step3 = performance.now();
        this.handleHeadings();
        console.log('[AnswerParser] ⏱️ handleHeadings 耗时:', (performance.now() - step3).toFixed(2), 'ms');
        
        const step4 = performance.now();
        this.identifyBoldRanges();
        console.log('[AnswerParser] ⏱️ identifyBoldRanges 耗时:', (performance.now() - step4).toFixed(2), 'ms');
        
        const step5 = performance.now();
        this.handleHorizontalRules();
        console.log('[AnswerParser] ⏱️ handleHorizontalRules 耗时:', (performance.now() - step5).toFixed(2), 'ms');
        
        const step6 = performance.now();
        this.identifyAndRenderTables();
        console.log('[AnswerParser] ⏱️ identifyAndRenderTables 耗时:', (performance.now() - step6).toFixed(2), 'ms');
        
        const step7 = performance.now();
        this.fixInconsistentStyles();
        console.log('[AnswerParser] ⏱️ fixInconsistentStyles 耗时:', (performance.now() - step7).toFixed(2), 'ms');
        
        const beforeRenderTime = performance.now();
        console.log('[AnswerParser] 🎨 准备渲染，数据处理总耗时:', (beforeRenderTime - perfStart).toFixed(2), 'ms');
        
        // 🔥 监控Vue渲染性能
        this.$nextTick(() => {
          const renderTime = performance.now() - beforeRenderTime;
          console.log('[AnswerParser] 🎨 Vue虚拟DOM渲染耗时:', renderTime.toFixed(2), 'ms');
          
          // 🔥 监控浏览器实际DOM渲染和布局时间
          requestAnimationFrame(() => {
            const domRenderTime = performance.now() - beforeRenderTime;
            console.log('[AnswerParser] 🎨 浏览器DOM渲染耗时:', domRenderTime.toFixed(2), 'ms');
            
            // 再等一帧，确保布局完成
            requestAnimationFrame(() => {
              const layoutTime = performance.now() - beforeRenderTime;
              const totalTime = performance.now() - perfStart;
              const domNodeCount = this.$el ? this.$el.querySelectorAll('span').length : 'N/A';
              
              console.log('[AnswerParser] 🎨 浏览器布局完成耗时:', layoutTime.toFixed(2), 'ms');
              console.log('[AnswerParser] ✅ 总耗时（含渲染和布局）:', totalTime.toFixed(2), 'ms');
              console.log('[AnswerParser] 📊 内容统计:', {
                总字符数: this.answer.length,
                文本段落数: this.mixedContent.filter(item => item.type === 'text').length,
                代码块数: this.mixedContent.filter(item => item.type === 'code').length,
                DOM节点数: domNodeCount
              });
              
              // 🔥 如果DOM节点数很大，给出性能警告
              if (typeof domNodeCount === 'number' && domNodeCount > 10000) {
                console.warn('[AnswerParser] ⚠️ 性能警告: DOM节点数过多(' + domNodeCount + ')，可能导致渲染卡顿');
              }
            });
          });
        });
      });
  },
  watch: {
    answer(newVal, oldVal) {
      const perfStart = performance.now();
      console.log('[AnswerParser] 🔄 内容更新，长度:', newVal.length);
      
      this.processUpdateAnswer();
      const processTime = performance.now() - perfStart;
      console.log('[AnswerParser] ⏱️ processUpdateAnswer 耗时:', processTime.toFixed(2), 'ms');
      
      this.$nextTick(() => {
        const nextTickStart = performance.now();
        
        const step1 = performance.now();
        this.identifyLineTypes();
        console.log('[AnswerParser] ⏱️ identifyLineTypes 耗时:', (performance.now() - step1).toFixed(2), 'ms');
        
        const step2 = performance.now();
        this.precomputeCharClasses(); // 预计算类名以提高性能
        console.log('[AnswerParser] ⏱️ precomputeCharClasses 耗时:', (performance.now() - step2).toFixed(2), 'ms');
        
        const step3 = performance.now();
        this.handleHeadings();
        console.log('[AnswerParser] ⏱️ handleHeadings 耗时:', (performance.now() - step3).toFixed(2), 'ms');
        
        const step4 = performance.now();
        this.identifyBoldRanges();
        console.log('[AnswerParser] ⏱️ identifyBoldRanges 耗时:', (performance.now() - step4).toFixed(2), 'ms');
        
        const step5 = performance.now();
        this.handleHorizontalRules();
        console.log('[AnswerParser] ⏱️ handleHorizontalRules 耗时:', (performance.now() - step5).toFixed(2), 'ms');
        
        const step6 = performance.now();
        this.identifyAndRenderTables();
        console.log('[AnswerParser] ⏱️ identifyAndRenderTables 耗时:', (performance.now() - step6).toFixed(2), 'ms');
        
        const step7 = performance.now();
        // 🔥 延迟非关键样式修复，避免阻塞初始渲染
        this.$nextTick(() => {
          if (typeof requestIdleCallback !== 'undefined') {
            requestIdleCallback(() => {
              this.fixInconsistentStyles();
              console.log('[AnswerParser] ⏱️ fixInconsistentStyles 耗时:', (performance.now() - step7).toFixed(2), 'ms');
            }, { timeout: 1000 });
          } else {
            // 降级方案：延迟执行
            setTimeout(() => {
              this.fixInconsistentStyles();
              console.log('[AnswerParser] ⏱️ fixInconsistentStyles 耗时:', (performance.now() - step7).toFixed(2), 'ms');
            }, 100);
          }
        });
        
        const beforeRenderTime = performance.now();
        console.log('[AnswerParser] 🎨 准备渲染，数据处理总耗时:', (beforeRenderTime - perfStart).toFixed(2), 'ms');
        
        // 🔥 监控Vue渲染性能
        this.$nextTick(() => {
          const renderTime = performance.now() - beforeRenderTime;
          console.log('[AnswerParser] 🎨 Vue虚拟DOM渲染耗时:', renderTime.toFixed(2), 'ms');
          
          // 🔥 监控浏览器实际DOM渲染和布局时间
          requestAnimationFrame(() => {
            const domRenderTime = performance.now() - beforeRenderTime;
            console.log('[AnswerParser] 🎨 浏览器DOM渲染耗时:', domRenderTime.toFixed(2), 'ms');
            
            // 再等一帧，确保布局完成
            requestAnimationFrame(() => {
              const layoutTime = performance.now() - beforeRenderTime;
              console.log('[AnswerParser] 🎨 浏览器布局完成耗时:', layoutTime.toFixed(2), 'ms');
              
              // 🔥 监控重绘和合成时间（可能需要多帧）
              let frameCount = 0;
              const maxFrames = 10; // 最多监控10帧
              const checkPaint = () => {
                frameCount++;
                const currentTime = performance.now() - beforeRenderTime;
                
                if (frameCount >= maxFrames || currentTime > 5000) {
                  const totalTime = performance.now() - perfStart;
                  console.log('[AnswerParser] 🎨 浏览器重绘/合成完成耗时:', currentTime.toFixed(2), 'ms');
                  console.log('[AnswerParser] ✅ 更新总耗时（含渲染和布局）:', totalTime.toFixed(2), 'ms');
                  console.log('[AnswerParser] 📊 内容统计:', {
                    总字符数: this.answer.length,
                    文本段落数: this.mixedContent.filter(item => item.type === 'text').length,
                    代码块数: this.mixedContent.filter(item => item.type === 'code').length,
                    DOM节点数: this.$el ? this.$el.querySelectorAll('span').length : 'N/A'
                  });
                  
                  // 🔥 如果DOM节点数很大，给出性能警告
                  const domNodeCount = this.$el ? this.$el.querySelectorAll('span').length : 0;
                  if (domNodeCount > 10000) {
                    console.warn('[AnswerParser] ⚠️ 性能警告: DOM节点数过多(' + domNodeCount + ')，可能导致渲染卡顿');
                  }
                } else {
                  requestAnimationFrame(checkPaint);
                }
              };
              requestAnimationFrame(checkPaint);
            });
          });
        });
      });
    },
  },
  methods: {
    insertTestImage() {
      this.$nextTick(() => {
        // 查找所有段落容器
        const containers = document.querySelectorAll('.markdown-container');
        
        if (containers.length > 0) {
          // 在第一个段落后插入测试图片
          const firstContainer = containers[0];
          const markdownText = firstContainer.querySelector('.markdown-text');
          
          if (markdownText) {
            // 创建图片容器
            const imgContainer = document.createElement('div');
            imgContainer.style.margin = '16px 0';
            imgContainer.style.textAlign = 'center';
            imgContainer.style.border = '1px solid #ddd';
            imgContainer.style.padding = '10px';
            imgContainer.style.borderRadius = '4px';
            
            // 创建简单测试图片 - 使用最小的有效base64图片
            const img = document.createElement('img');
            img.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
            img.alt = '测试图片';
            img.style.width = '100px';
            img.style.height = '100px';
            img.style.backgroundColor = 'blue'; // 给1x1透明gif加上背景色以便可见
            
            // 添加图片到容器
            imgContainer.appendChild(img);
            
            // 插入图片容器
            markdownText.parentNode.insertBefore(imgContainer, markdownText.nextSibling);
            
            // 添加一个常规图片作为比较
            const regularImgContainer = document.createElement('div');
            regularImgContainer.style.margin = '16px 0';
            regularImgContainer.style.textAlign = 'center';
            regularImgContainer.style.border = '1px solid #ddd';
            regularImgContainer.style.padding = '10px';
            regularImgContainer.style.borderRadius = '4px';
            
            const regularImg = document.createElement('img');
            regularImg.src = 'https://via.placeholder.com/100x100.png?text=Test';
            regularImg.alt = '在线图片测试';
            regularImg.style.width = '100px';
            regularImg.style.height = '100px';
            
            regularImgContainer.appendChild(regularImg);
            
            // 插入常规图片容器
            markdownText.parentNode.insertBefore(regularImgContainer, imgContainer.nextSibling);
          }
        }
      });
    },

    // 检测并渲染图片
    checkAndRenderImages() {
      this.mixedContent.forEach((item, contentIndex) => {
        if (item.type !== 'text') return;
        
        const paragraph = this.$refs[`paragraph${contentIndex}`];
        if (!paragraph || !paragraph[0]) return;
        
        const text = item.content;
        const lines = text.split('\n');
        let lineStartIndex = 0;
        
        lines.forEach((line, lineIndex) => {
          // 检查该行是否是图片语法 ![alt](url)
          const imgRegex = /^!\[(.*?)\]\((.*?)\)$/;
          const match = line.trim().match(imgRegex);
          
          if (match) {
            const altText = match[1];
            const imgUrl = match[2];
            
            // 创建图片元素
            const imgContainer = document.createElement('div');
            imgContainer.className = 'md-image-container';
            
            const img = document.createElement('img');
            img.src = imgUrl;
            img.alt = altText;
            img.className = 'md-rendered-image';
            
            imgContainer.appendChild(img);
            
            // 获取该行开始和结束的位置
            const lineStart = lineStartIndex;
            const lineEnd = lineStartIndex + line.length;
            
            // 获取所有span
            const spans = paragraph[0].querySelectorAll('.markdown-text span');
            
            // 隐藏该行的所有字符
            for (let i = lineStart; i < lineEnd && i < spans.length; i++) {
              spans[i].style.opacity = '0';
              spans[i].style.height = '0';
              spans[i].style.position = 'absolute';
              spans[i].style.pointerEvents = 'none';
            }
            
            // 在第一个span前插入图片
            if (spans[lineStart]) {
              const parent = spans[lineStart].parentNode;
              parent.insertBefore(imgContainer, spans[lineStart]);
            }
          }
          
          // 更新行开始索引
          lineStartIndex += line.length + 1; // +1 是换行符
        });
      });
    },

    // 修复不一致的样式问题
    fixInconsistentStyles() {
      this.mixedContent.forEach((item, contentIndex) => {
        if (item.type !== 'text') return;
        
        const paragraph = this.$refs[`paragraph${contentIndex}`];
        if (!paragraph || !paragraph[0]) return;
        
        // 获取所有span元素
        const spans = paragraph[0].querySelectorAll('.markdown-text span');
        
        // 遍历行类型信息，确保每一行的样式一致
        Object.entries(this.lineTypes[contentIndex] || {}).forEach(([lineStart, lineInfo]) => {
          if (lineInfo.type === 'heading') {
            const level = lineInfo.level;
            
            // 确保所有标题标记符号具有一致的样式
            for (let i = parseInt(lineStart); i < parseInt(lineStart) + level; i++) {
              if (spans[i]) {
                spans[i].classList.add('md-heading-marker');
                spans[i].style.color = '#9a9a9a';
                spans[i].style.opacity = '0.35';
              }
            }
            
            // 确保标题内容所有字符都具有正确的样式和字体大小
            for (let i = parseInt(lineStart) + level + 1; i < parseInt(lineStart) + lineInfo.length; i++) {
              if (spans[i]) {
                // 设置标题内容样式
                spans[i].classList.add(`h${level}-text`);
              }
            }
          }
        });
      });
    },
    
    // 专门处理标题的方法
    handleHeadings() {
      this.mixedContent.forEach((item, contentIndex) => {
        if (item.type !== 'text') return;
        
        const text = item.content;
        const paragraph = this.$refs[`paragraph${contentIndex}`];
        if (!paragraph || !paragraph[0]) return;
        
        const spans = paragraph[0].querySelectorAll('.markdown-text span');
        
        // 遍历每一行，查找标题
        const lines = text.split('\n');
        let currentPosition = 0;
        
        lines.forEach((line, lineIndex) => {
          // 检查是否是标题行
          const headingMatch = line.match(/^(#{1,6})\s+(.*?)$/);
          if (headingMatch) {
            const level = headingMatch[1].length;
            const titleContent = headingMatch[2];
            
            // 为标题标记符号设置统一样式
            for (let i = 0; i < level; i++) {
              if (spans[currentPosition + i]) {
                spans[currentPosition + i].classList.add('md-heading-marker');
                spans[currentPosition + i].style.color = '#9a9a9a';
                spans[currentPosition + i].style.opacity = '0.35';
              }
            }
            
            // 为空格设置样式
            if (spans[currentPosition + level]) {
              spans[currentPosition + level].classList.add('md-heading-space');
            }
            
            // 为标题内容设置统一样式
            const contentStart = currentPosition + level + 1;
            for (let i = 0; i < titleContent.length; i++) {
              if (spans[contentStart + i]) {
                spans[contentStart + i].classList.add(`h${level}-text`);
                spans[contentStart + i].style.fontWeight = '600';
              }
            }
          }
          
          // 更新当前位置
          currentPosition += line.length + 1; // +1 是换行符
        });
      });
    },
    
    // 修改isTableFinal方法，添加更严格的完整性检查
    isTableFinal(lines, startLine, endLine) {
      // 基本表格完整性检查 - 至少需要3行(表头、分隔行、数据行)
      if (endLine - startLine < 2) return false;
      
      // 检查是否有分隔行(第二行)
      const secondLine = lines[startLine + 1].trim();
      if (!secondLine.startsWith('|') || !secondLine.endsWith('|')) return false;
      
      // 分隔行检查 - 应只包含 |、-、:、空格
      const separatorContent = secondLine.replace(/\|/g, '').trim();
      if (!/^[\s\-:]+$/.test(separatorContent)) return false;
      
      // 列数一致性检查
      const cellCounts = [];
      for (let i = startLine; i <= endLine; i++) {
        const line = lines[i].trim();
        if (!line.startsWith('|') || !line.endsWith('|')) return false;
        cellCounts.push(line.split('|').length - 1);
      }
      
      // 所有行的单元格数量应该一致
      if (new Set(cellCounts).size !== 1) return false;
      
      // 新增：检查表格后是否有空行，且空行后一行不是表格
      const hasEmptyLineAfter = endLine < lines.length - 2 && 
                            lines[endLine + 1].trim() === '' && 
                            lines[endLine + 2].trim() !== '' &&
                            !(lines[endLine + 2].trim().startsWith('|') && 
                              lines[endLine + 2].trim().endsWith('|'));
                              
      // 如果表格是文本的最后内容，也认为是完整的
      const isLastContent = endLine >= lines.length - 1;
      
      // 只有在表格后有空行且空行后不是表格行，或者是最后的内容时，才认为表格是完整的
      return hasEmptyLineAfter || isLastContent;
    },

    // 修改identifyAndRenderTables方法
    identifyAndRenderTables() {
      this.mixedContent.forEach((item, contentIndex) => {
        if (item.type !== 'text') return;
        
        const text = item.content;
        const lines = text.split('\n');
        let tableStart = -1;
        
        // 清除之前的表格范围信息，但只清除当前contentIndex的
        this.tableRanges = this.tableRanges.filter(range => range.contentIndex !== contentIndex);
        
        // 找到表格开始和结束的行
        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          
          // 如果行包含至少两个 |，可能是表格行
          if (line.indexOf('|') !== line.lastIndexOf('|')) {
            // 如果是新表格的开始
            if (tableStart === -1) {
              tableStart = i;
            }
            
            // 检查是否到达表格末尾或文本末尾
            if (i === lines.length - 1 || 
                !(lines[i + 1].trim().startsWith('|') && 
                  lines[i + 1].trim().endsWith('|') && 
                  lines[i + 1].trim().indexOf('|') !== lines[i + 1].trim().lastIndexOf('|'))) {
              
              // 找到了表格的结束
              if (tableStart !== -1 && i - tableStart >= 1) {
                // 检查是否是最终版本的表格
                if (this.isTableFinal(lines, tableStart, i)) {
                  // 创建全局唯一的表格签名
                  const tableContent = lines.slice(tableStart, i + 1).join('');
                  const tableSignature = `${contentIndex}-${tableStart}-${i}-${tableContent.length}`;
                  
                  // 检查是否已经渲染过这个表格
                  if (!this.renderedTableSignatures.has(tableSignature)) {
                    this.renderTable(contentIndex, tableStart, i);
                    // 记录已渲染的表格签名
                    this.renderedTableSignatures.add(tableSignature);
                  }
                }
                tableStart = -1;
              }
            }
          } else if (tableStart !== -1) {
            // 如果当前行不是表格行，但已开始一个表格
            if (i - tableStart >= 2) {
              // 检查是否是最终版本的表格
              if (this.isTableFinal(lines, tableStart, i - 1)) {
                // 创建全局唯一的表格签名
                const tableContent = lines.slice(tableStart, i).join('');
                const tableSignature = `${contentIndex}-${tableStart}-${i-1}-${tableContent.length}`;
                
                // 检查是否已经渲染过这个表格
                if (!this.renderedTableSignatures.has(tableSignature)) {
                  this.renderTable(contentIndex, tableStart, i - 1);
                  // 记录已渲染的表格签名
                  this.renderedTableSignatures.add(tableSignature);
                }
              }
            }
            tableStart = -1;
          }
        }
      });
    },
    
    // 渲染表格
    renderTable(contentIndex, startLine, endLine) {
      const paragraph = this.$refs[`paragraph${contentIndex}`];
      if (!paragraph || !paragraph[0]) return;
      
      const text = this.mixedContent[contentIndex].content;
      const lines = text.split('\n');
      const tableLines = lines.slice(startLine, endLine + 1);
      
      // 计算表格开始的位置
      let startIndex = 0;
      for (let i = 0; i < startLine; i++) {
        startIndex += lines[i].length + 1; // +1 是换行符
      }
      
      // 计算表格结束的位置
      let endIndex = startIndex;
      for (let i = 0; i < tableLines.length; i++) {
        endIndex += tableLines[i].length + 1; // +1 是换行符
      }
      endIndex--; // 去掉最后一个换行符
      
      // 获取当前段落的span
      const spans = paragraph[0].querySelectorAll('.markdown-text span');
      
      // 创建表格容器
      const tableContainer = document.createElement('div');
      tableContainer.className = 'md-table-container';
      tableContainer.style.position = 'relative';
      tableContainer.style.margin = '1em 0';
      tableContainer.style.overflow = 'auto';
      tableContainer.style.borderRadius = '3px';
      tableContainer.style.border = '1px solid #dfe2e5';
      
      // 创建表格
      const table = document.createElement('table');
      table.className = 'md-table';
      table.style.borderCollapse = 'collapse';
      table.style.width = '100%';
      table.style.fontSize = '14px';
      
      // 解析表格内容
      let currentRow = 0;
      let hasHeader = false;
      
      // 处理每一行
      tableLines.forEach((line, lineIndex) => {
        const cells = line.split('|').filter(cell => cell !== '');
        
        // 是否是分隔行（例如 |---|---|---| ）
        const isSeparatorRow = cells.every(cell => {
          const trimmed = cell.trim();
          return /^[-:]+$/.test(trimmed);
        });
        
        if (isSeparatorRow) {
          hasHeader = true; // 有分隔行，表示上一行是表头
        } else {
          // 创建行
          const row = document.createElement('tr');
          
          // 设置行样式
          if (currentRow % 2 === 0) {
            row.style.backgroundColor = '#ffffff';
          } else {
            row.style.backgroundColor = '#f6f8fa';
          }
          
          // 处理单元格
          cells.forEach(cellContent => {
            const cell = document.createElement(hasHeader && currentRow === 0 ? 'th' : 'td');
            cell.textContent = cellContent.trim();
            cell.style.padding = '8px 13px';
            cell.style.border = '1px solid #dfe2e5';
            
            if (hasHeader && currentRow === 0) {
              cell.style.backgroundColor = '#f6f8fa';
              cell.style.fontWeight = 'bold';
              cell.style.textAlign = 'center';
            }
            
            row.appendChild(cell);
          });
          
          table.appendChild(row);
          currentRow++;
        }
      });
      
      // 添加表格到容器
      tableContainer.appendChild(table);
      
      // 隐藏原始表格字符
      for (let i = startIndex; i <= endIndex && i < spans.length; i++) {
        spans[i].classList.add('md-table-original-char');
        spans[i].style.opacity = '0';
        spans[i].style.position = 'absolute';
        spans[i].style.pointerEvents = 'none';
        spans[i].style.height = '0';
      }
      
      // 第一个span前插入表格容器
      if (spans[startIndex]) {
        const parent = spans[startIndex].parentNode;
        parent.insertBefore(tableContainer, spans[startIndex]);
      }
      
      // 保存表格范围信息
      this.tableRanges.push({
        contentIndex,
        startLine,
        endLine,
        startIndex,
        endIndex
      });
    },
    
    // 修改处理横线(---)的方法
    handleHorizontalRules() {
      this.mixedContent.forEach((item, contentIndex) => {
        if (item.type !== 'text') return;
        
        const paragraph = this.$refs[`paragraph${contentIndex}`];
        if (!paragraph || !paragraph[0]) return;
        
        const text = item.content;
        const lines = text.split('\n');
        
        lines.forEach((line, lineIndex) => {
          // 检查是否是水平分隔线
          if (line.trim().match(/^(\*{3,}|-{3,}|_{3,})$/)) {
            // 计算该行的起始位置
            let lineStartIndex = 0;
            for (let i = 0; i < lineIndex; i++) {
              lineStartIndex += lines[i].length + 1; // +1 是换行符
            }
            
            // 创建分隔线的唯一签名
            const hrSignature = `${contentIndex}-${lineIndex}-${lineStartIndex}-${line.trim().length}`;
            
            // 检查是否已经渲染过这个分隔线
            if (this.renderedHRSignatures.has(hrSignature)) {
              return; // 已渲染过，跳过
            }
            
            // 检查分隔线是否完整（后面有空行或是最后一行）
            const isComplete = lineIndex === lines.length - 1 || 
                              (lineIndex < lines.length - 1 && 
                              (lines[lineIndex + 1].trim() === '' || 
                              !lines[lineIndex + 1].trim().match(/^(\*{3,}|-{3,}|_{3,})$/)));
            
            // 只渲染完整的分隔线
            if (isComplete) {
              const container = paragraph[0];
              const spans = container.querySelectorAll('.markdown-text span');
              
              // 为这一整行创建一个特殊的容器
              const hrDiv = document.createElement('div');
              hrDiv.className = 'md-hr-container';
              hrDiv.setAttribute('data-hr-key', hrSignature);
              hrDiv.style.height = '1px';
              hrDiv.style.backgroundColor = '#ddd';
              hrDiv.style.margin = '16px 0';
              hrDiv.style.width = '100%';
              hrDiv.style.position = 'relative';
              
              // 隐藏原始字符
              for (let i = lineStartIndex; i < lineStartIndex + line.length && i < spans.length; i++) {
                spans[i].classList.add('md-hr-char');
                spans[i].style.opacity = '0';
                spans[i].style.height = '0';
                spans[i].style.position = 'absolute';
                spans[i].style.pointerEvents = 'none';
              }
              
              // 将hr添加到适当的位置
              if (spans[lineStartIndex]) {
                const parent = spans[lineStartIndex].parentNode;
                // 检查是否已经有相同的分隔线
                const existingHr = parent.querySelector(`[data-hr-key="${hrSignature}"]`);
                if (!existingHr) {
                  parent.insertBefore(hrDiv, spans[lineStartIndex]);
                  // 记录已渲染的分隔线
                  this.renderedHRSignatures.add(hrSignature);
                }
              }
            }
          }
        });
      });
    },
    
    // 识别所有加粗范围
    identifyBoldRanges() {
      this.mixedContent.forEach((item, contentIndex) => {
        if (item.type !== 'text') return;
        
        const text = item.content;
        const paragraph = this.$refs[`paragraph${contentIndex}`];
        if (!paragraph || !paragraph[0]) return;
        
        // 寻找所有加粗+斜体文本的范围（***文本***格式，优先处理）
        const boldItalicPattern = /\*\*\*(.*?)\*\*\*/g;
        const spans = paragraph[0].querySelectorAll('.markdown-text span');
        
        let match;
        // 先处理***格式（粗体+斜体）
        const processedRanges = [];
        while ((match = boldItalicPattern.exec(text)) !== null) {
          const boldItalicContent = match[1];
          const startIndex = match.index + 3; // 跳过前三个***
          const endIndex = startIndex + boldItalicContent.length;
          processedRanges.push({start: match.index, end: match.index + match[0].length});
          
          // 给加粗+斜体范围内的字符添加样式
          for (let i = startIndex; i < endIndex; i++) {
            if (spans[i]) {
              spans[i].classList.add('md-bold-italic');
              spans[i].style.fontWeight = '600';
              spans[i].style.fontStyle = 'italic';
            }
          }
          
          // 降低***标记的不透明度
          for (let i = 0; i < 3; i++) {
            if (spans[match.index + i]) {
              spans[match.index + i].classList.add('md-bold-marker');
              spans[match.index + i].style.color = '#9a9a9a';
              spans[match.index + i].style.opacity = '0.35';
            }
          }
          for (let i = 0; i < 3; i++) {
            if (spans[endIndex + i]) {
              spans[endIndex + i].classList.add('md-bold-marker');
              spans[endIndex + i].style.color = '#9a9a9a';
              spans[endIndex + i].style.opacity = '0.35';
            }
          }
        }
        
        // 再处理**格式（仅加粗），但要排除已经被***处理的区域
        const boldPattern = /\*\*(.*?)\*\*/g;
        boldPattern.lastIndex = 0; // 重置正则表达式
        while ((match = boldPattern.exec(text)) !== null) {
          // 检查是否与已处理的***区域重叠
          const isOverlapping = processedRanges.some(range => 
            (match.index >= range.start && match.index < range.end) ||
            (match.index + match[0].length > range.start && match.index + match[0].length <= range.end)
          );
          
          if (isOverlapping) {
            continue; // 跳过已处理的区域
          }
          
          const boldContent = match[1];
          const startIndex = match.index + 2; // 跳过前两个**
          const endIndex = startIndex + boldContent.length;
          
          // 给加粗范围内的字符添加加粗样式
          for (let i = startIndex; i < endIndex; i++) {
            if (spans[i]) {
              spans[i].classList.add('md-bold');
              spans[i].style.fontWeight = '600';
            }
          }
          
          // 降低**标记的不透明度
          if (spans[match.index]) {
            spans[match.index].classList.add('md-bold-marker');
            spans[match.index].style.color = '#9a9a9a';
            spans[match.index].style.opacity = '0.35';
          }
          if (spans[match.index + 1]) {
            spans[match.index + 1].classList.add('md-bold-marker');
            spans[match.index + 1].style.color = '#9a9a9a';
            spans[match.index + 1].style.opacity = '0.35';
          }
          if (spans[endIndex]) {
            spans[endIndex].classList.add('md-bold-marker');
            spans[endIndex].style.color = '#9a9a9a';
            spans[endIndex].style.opacity = '0.35';
          }
          if (spans[endIndex + 1]) {
            spans[endIndex + 1].classList.add('md-bold-marker');
            spans[endIndex + 1].style.color = '#9a9a9a';
            spans[endIndex + 1].style.opacity = '0.35';
          }
        }
      });
    },
    
    // 识别每行的类型
    identifyLineTypes() {
      this.mixedContent.forEach((item, contentIndex) => {
        if (item.type !== 'text') return;
        
        const text = item.content;
        const lines = text.split('\n');
        this.lineTypes[contentIndex] = {};
        
        lines.forEach((line, lineIndex) => {
          // 计算该行在当前文本中的起始索引（相对于当前item.content）
          let lineStartIndex = 0;
          for (let i = 0; i < lineIndex; i++) {
            lineStartIndex += lines[i].length + 1; // +1 是换行符
          }
          
          // 🔥 对于分段，需要检查该行是否跨越了分段边界
          // 如果行在分段内，直接使用相对位置；如果跨越边界，可能需要特殊处理
          // 但通常分段会在合适的位置（如行边界）分割，所以这里先简单处理
          
          // 标题行 - 如 # 标题
          if (line.match(/^#{1,6}\s/)) {
            const level = line.match(/^(#{1,6})\s/)[1].length;
            this.lineTypes[contentIndex][lineStartIndex] = { 
              type: 'heading', 
              level: level,
              length: line.length
            };
          }
          // 列表项 - 如 - 列表项 或 1. 列表项
          else if (line.match(/^\s*[-*+]\s/) || line.match(/^\s*\d+\.\s/)) {
            this.lineTypes[contentIndex][lineStartIndex] = { 
              type: 'list-item',
              length: line.length
            };
          }
          // 引用块 - 如 > 引用
          else if (line.match(/^\s*>\s/)) {
            this.lineTypes[contentIndex][lineStartIndex] = { 
              type: 'blockquote',
              length: line.length
            };
          }
          // 分隔线 - 如 ---
          else if (line.match(/^(\*{3,}|-{3,}|_{3,})$/)) {
            this.lineTypes[contentIndex][lineStartIndex] = { 
              type: 'hr',
              length: line.length
            };
          }
          // 表格行 - 如 | 表头 | 表头 |
          else if (line.indexOf('|') !== line.lastIndexOf('|')) {
            this.lineTypes[contentIndex][lineStartIndex] = { 
              type: 'table-row',
              length: line.length
            };
          }
          // 普通段落
          else {
            this.lineTypes[contentIndex][lineStartIndex] = { 
              type: 'paragraph',
              length: line.length
            };
          }
        });
      });
    },
    
    // 为每个字符分配CSS类
    getCharClass(char, index, text) {
      const classes = [];
      
      // 寻找当前字符所在的行的起始索引
      const lineStart = this.getLineStartIndex(text, index);
      const lineEnd = this.getLineEndIndex(text, index);
      
      // 找到当前行在全文中的位置
      const contentIndex = this.getContentIndexByCharIndex(index);
      
      // 如果有行类型信息，添加到类中
      if (contentIndex !== -1 && this.lineTypes[contentIndex] && this.lineTypes[contentIndex][lineStart]) {
        const lineType = this.lineTypes[contentIndex][lineStart];
        
        if (lineType.type === 'heading') {
          // 标题行
          classes.push(`h${lineType.level}-line`);
          
          // 标题文本内容
          if (index > lineStart + lineType.level) {
            classes.push(`h${lineType.level}-text`);
          }
        }
        
        else if (lineType.type === 'list-item') {
          // 列表项行
          classes.push('list-item-line');
          
          // 列表项标记 (-, *, +, 1.)
          const listMarkerMatch = text.substring(lineStart).match(/^(\s*[-*+]\s|\s*\d+\.\s)/);
          if (listMarkerMatch && index >= lineStart && index < lineStart + listMarkerMatch[0].length) {
            classes.push('md-list-marker');
          }
        }
        
        else if (lineType.type === 'blockquote') {
          // 引用块行
          classes.push('blockquote-line');
          
          // 引用块标记 (>)
          const quoteMatch = text.substring(lineStart).match(/^(\s*>\s)/);
          if (quoteMatch && index >= lineStart && index < lineStart + quoteMatch[0].length) {
            classes.push('md-blockquote-marker');
          }
          // 引用块内容
          else if (quoteMatch && index >= lineStart + quoteMatch[0].length && index < lineStart + lineType.length) {
            classes.push('md-blockquote-content');
          }
        }
        
        else if (lineType.type === 'hr') {
          // 分隔线行
          classes.push('hr-line');
        }
        
        else if (lineType.type === 'table-row') {
          // 表格行
          classes.push('table-row-line');
          
          // 表格分隔符 (|)
          if (char === '|') {
            classes.push('md-table-marker');
          }
        }
      }
      
      // 处理行内样式
      
      // 行内代码 `代码`
      if (this.isInlineCode(text, index)) {
        classes.push('md-inline-code');
      } else if (char === '`') {
        // 行内代码的反引号
        classes.push('md-code-marker');
      }
      
      // 链接文本 [链接文本](URL)
      if (this.isLinkText(text, index)) {
        classes.push('md-link-text');
      } else if (this.isLinkMarker(text, index)) {
        // 链接的标记符号 [](URL)
        classes.push('md-link-marker');
      }
      
      // 标记符号颜色设置，但不添加视觉样式
      if ((char === '*' || char === '_') && !classes.includes('md-link-text') && 
          !classes.includes('md-link-marker') && !classes.includes('md-inline-code')) {
        classes.push('md-marker');
      }

      return classes.join(' ');
    },
    
    // 获取字符所在内容项的索引
    getContentIndexByCharIndex(globalIndex) {
      let currentIndex = 0;
      
      for (let i = 0; i < this.mixedContent.length; i++) {
        const item = this.mixedContent[i];
        
        if (item.type === 'text') {
          const textLength = item.content.length;
          
          if (globalIndex >= currentIndex && globalIndex < currentIndex + textLength) {
            return i;
          }
          
          currentIndex += textLength;
        } else {
          // 代码块，跳过
          currentIndex += item.content.length + 6; // +6 是 ``` 标记符
        }
      }
      
      return -1;
    },
    
    // 获取行首位置
    getLineStartIndex(text, index) {
      let i = index;
      while (i > 0 && text[i-1] !== '\n') {
        i--;
      }
      return i;
    },
    
    // 获取行尾位置
    getLineEndIndex(text, index) {
      let i = index;
      while (i < text.length && text[i] !== '\n') {
        i++;
      }
      return i;
    },
    
    // 判断是否是行内代码
    isInlineCode(text, index) {
      // 预处理：找到所有反引号对
      const backtickPairs = this.findBacktickPairs(text);
      
      // 检查当前索引是否在任何一对反引号之间
      for (const pair of backtickPairs) {
        if (index > pair.start && index < pair.end) {
          return true;
        }
      }
      
      return false;
    },
    
    // 查找所有反引号对
    findBacktickPairs(text) {
      const pairs = [];
      let i = 0;
      
      while (i < text.length) {
        // 查找开始反引号
        if (text[i] === '`' && (i === 0 || text[i-1] !== '\\')) {
          const start = i;
          i++;
          
          // 查找结束反引号
          while (i < text.length) {
            if (text[i] === '`' && (i === 0 || text[i-1] !== '\\')) {
              const end = i;
              pairs.push({ start, end });
              i++;
              break;
            }
            i++;
          }
        } else {
          i++;
        }
      }
      
      return pairs;
    },
    
    // 判断是否是链接文本 [文本]
    isLinkText(text, index) {
      // 查找 [文本](链接) 格式中的文本部分
      let leftPos = -1;
      let rightPos = -1;
      
      // 查找左侧 [
      for (let i = index - 1; i >= 0; i--) {
        if (text[i] === '[') {
          leftPos = i + 1;
          break;
        }
      }
      
      // 如果找到左侧 [，查找右侧 ]
      if (leftPos !== -1) {
        for (let i = index + 1; i < text.length; i++) {
          if (text[i] === ']') {
            rightPos = i;
            break;
          }
        }
      }
      
      // 检查 ] 后面是否跟着 (链接)
      if (rightPos !== -1 && rightPos + 1 < text.length && text[rightPos + 1] === '(') {
        // 查找右括号
        for (let i = rightPos + 2; i < text.length; i++) {
          if (text[i] === ')') {
            // 确认这是一个完整的链接格式
            return index >= leftPos && index < rightPos;
          }
        }
      }
      
      return false;
    },
    
    // 判断是否是链接标记 [、]、(、)
    isLinkMarker(text, index) {
      // 检查当前字符是否是链接格式的标记字符
      if (text[index] === '[' || text[index] === ']' || text[index] === '(' || text[index] === ')') {
        // 判断是否在链接格式中
        // [文本](链接) 格式
        
        // 如果是 [，检查是否有对应的 ](
        if (text[index] === '[') {
          for (let i = index + 1; i < text.length - 1; i++) {
            if (text[i] === ']' && text[i + 1] === '(') {
              // 查找右括号
              for (let j = i + 2; j < text.length; j++) {
                if (text[j] === ')') {
                  return true;
                }
              }
            }
          }
        }
        
        // 如果是 ]，检查是否有对应的 [(
        if (text[index] === ']') {
          if (index + 1 < text.length && text[index + 1] === '(') {
            // 向前查找 [
            for (let i = index - 1; i >= 0; i--) {
              if (text[i] === '[') {
                return true;
              }
            }
          }
        }
        
        // 如果是 (，检查是否在 ](链接) 中
        if (text[index] === '(') {
          if (index > 0 && text[index - 1] === ']') {
            // 向前查找 [
            for (let i = index - 2; i >= 0; i--) {
              if (text[i] === '[') {
                return true;
              }
            }
          }
        }
        
        // 如果是 )，检查是否在 [文本](链接) 中
        if (text[index] === ')') {
          // 向前查找 (
          let foundOpenParen = false;
          let openParenIndex = -1;
          
          for (let i = index - 1; i >= 0; i--) {
            if (text[i] === '(') {
              foundOpenParen = true;
              openParenIndex = i;
              break;
            }
          }
          
          if (foundOpenParen && openParenIndex > 0 && text[openParenIndex - 1] === ']') {
            // 向前查找 [
            for (let i = openParenIndex - 2; i >= 0; i--) {
              if (text[i] === '[') {
                return true;
              }
            }
          }
        }
      }
      
      return false;
    },
    
    // 获取文本颜色（优化版本 - 使用标签缓存）
    getTextColor(text, index, tagRanges = null) {
      // 如果提供了标签范围缓存，使用缓存；否则使用旧的方法（向后兼容）
      if (tagRanges && tagRanges.length > 0) {
        // 从最内层（第7次）到最外层（第1次）检查，优先使用内层标签的颜色
        const getModifyColor = (level) => {
          const colors = {1: 'red', 2: 'blue', 3: 'purple', 4: '#FFA500', 5: '#FF8C00', 6: '#32CD32', 7: '#00CED1'};
          return colors[level] || 'black';
        };
        for (let i = 7; i >= 1; i--) {
          for (const range of tagRanges) {
            if (range.level === i && index >= range.contentStart && index < range.contentEnd) {
              return getModifyColor(i);
            }
          }
        }
        return 'black';
      }
      
      // 向后兼容：如果没有缓存，使用旧方法（但这种情况应该很少）
      const getModifyColor = (level) => {
        const colors = {1: 'red', 2: 'blue', 3: 'purple', 4: '#FFA500', 5: '#FF8C00', 6: '#32CD32', 7: '#00CED1'};
        return colors[level] || 'black';
      };
      for(let i = 7; i >= 1; i--) {
        const startTag = `<第${i}次修改内容>`;
        const endTag = `</第${i}次修改内容>`;
        
        let pos = 0;
        
        while(true) {
          const startPos = text.indexOf(startTag, pos);
          if(startPos === -1) break;
          
          const endPos = text.indexOf(endTag, startPos);
          if(endPos === -1) break;
          
          const contentStart = startPos + startTag.length;
          const contentEnd = endPos;
          
          if(index >= contentStart && index < contentEnd) {
            return getModifyColor(i);
          }
          
          pos = endPos + endTag.length;
        }
      }
      return 'black';
    },
    
    processUpdateAnswer() {
      this.mixedContent = [];
      this.visibleMixedContent = []; // 🔥 重置可见内容
      const codeRegex = /```(.*?)```/gs;
      const textParts = this.answer.split(codeRegex);
      
      textParts.forEach((part, index) => {
        if (index % 2 === 0) {
          // 文本部分 - 先处理完整内容
          const processedContent = this.processModifyTags(part);
          const text = processedContent.text;
          const textLength = text.length;
          
          // 🔥 如果文本很长，分段处理（但保留完整文本用于后续处理）
          // 🔥 计算当前文本块在answer中的起始位置
          let textBlockStartInAnswer = 0;
          for (let k = 0; k < index; k++) {
            if (k % 2 === 0) {
              // 文本块
              const prevText = textParts[k];
              textBlockStartInAnswer += prevText.length;
            } else {
              // 代码块（包括标记）
              textBlockStartInAnswer += textParts[k].length + '``````'.length;
            }
          }
          
          if (textLength > this.renderBatchSize) {
            // 先创建完整的textItem用于样式处理
            const textArray = Array.from(text);
            const colors = textArray.map((char, idx) => 
              this.getTextColor(text, idx, processedContent.tags)
            );
            
            const fullTextItem = { 
              type: 'text', 
              content: text, // 🔥 保存完整文本
              colors: colors,
              modifyTags: processedContent.tags,
              charClasses: null,
              charStyles: null,
              isSegment: false,
              _fullText: text, // 🔥 标记为完整文本，用于后续分段
              _segmentData: {
                tags: processedContent.tags,
                fullColors: colors
              }
            };
            
            // 然后分段
            let startIndex = 0;
            let segmentIndex = 0;
            
            while (startIndex < textLength) {
              let endIndex = Math.min(startIndex + this.renderBatchSize, textLength);
              
              // 🔥 如果不是最后一段，尽量在换行符处分割，避免在行中间分割
              if (endIndex < textLength) {
                // 向后查找最近的换行符（在最后200个字符内查找）
                let searchStart = Math.max(startIndex, endIndex - 200);
                let newlinePos = text.indexOf('\n', searchStart);
                if (newlinePos !== -1 && newlinePos < endIndex && newlinePos > startIndex + this.renderBatchSize * 0.8) {
                  endIndex = newlinePos + 1; // 包含换行符
                }
              }
              
              const segmentText = text.substring(startIndex, endIndex);
              const segmentColors = segmentText.split('').map((char, idx) => colors[startIndex + idx]);
              
              // 🔥 将modifyTags转换为相对于本段的相对位置
              const segmentTags = processedContent.tags.map(tag => {
                // 检查标签是否与本段有交集
                const tagStart = tag.startPos;
                const tagEnd = tag.endPos;
                
                // 如果标签完全在本段之前或之后，返回null（将在后面过滤）
                if (tagEnd <= startIndex || tagStart >= endIndex) {
                  return null;
                }
                
                // 计算标签在本段中的相对位置
                const relativeStart = Math.max(0, tagStart - startIndex);
                const relativeContentStart = Math.max(0, tag.contentStart - startIndex);
                const relativeContentEnd = Math.min(endIndex - startIndex, tag.contentEnd - startIndex);
                const relativeEnd = Math.min(endIndex - startIndex, tagEnd - startIndex);
                
                // 只保留与本段有交集的标签
                if (relativeEnd <= 0 || relativeStart >= (endIndex - startIndex)) {
                  return null;
                }
                
                return {
                  level: tag.level,
                  startPos: relativeStart,
                  contentStart: relativeContentStart,
                  contentEnd: relativeContentEnd,
                  endPos: relativeEnd,
                  startTagLength: tag.startTagLength,
                  endTagLength: tag.endTagLength
                };
              }).filter(tag => tag !== null); // 过滤掉null值
              
              // 创建分段item
              const segmentItem = { 
                type: 'text', 
                content: segmentText,
                colors: segmentColors,
                modifyTags: segmentTags, // 🔥 使用转换后的相对位置标签
                charClasses: null,
                charStyles: null,
                originalStartIndex: startIndex,
                originalEndIndex: endIndex,
                isSegment: true,
                segmentIndex: segmentIndex,
                textBlockStartInAnswer: textBlockStartInAnswer // 🔥 记录原始文本块在answer中的起始位置
              };
              
              Object.freeze(segmentItem.colors);
              Object.freeze(segmentItem.modifyTags);
              Object.seal(segmentItem);
              
              this.mixedContent.push(segmentItem);
              startIndex = endIndex;
              segmentIndex++;
            }
            
            // 🔥 保存完整item引用，供后续处理使用（不添加到mixedContent）
            // 所有分段都通过parentFullTextItem引用它
            
          } else {
            // 短文本，正常处理
            // 🔥 计算当前文本块在answer中的起始位置（在processUpdateAnswer中也需要）
            let textBlockStartInAnswerForShort = 0;
            for (let k = 0; k < index; k++) {
              if (k % 2 === 0) {
                textBlockStartInAnswerForShort += textParts[k].length;
              } else {
                textBlockStartInAnswerForShort += textParts[k].length + '``````'.length;
              }
            }
            
            const processedContent = this.processModifyTags(part);
            const textArray = Array.from(processedContent.text);
            const colors = textArray.map((char, idx) => 
              this.getTextColor(processedContent.text, idx, processedContent.tags)
            );
            
            const textItem = { 
              type: 'text', 
              content: processedContent.text,
              colors: colors,
              modifyTags: processedContent.tags,
              charClasses: null,
              charStyles: null,
              isSegment: false,
              textBlockStartInAnswer: textBlockStartInAnswerForShort // 🔥 记录在answer中的起始位置
            };
            
            Object.freeze(textItem.colors);
            Object.freeze(textItem.modifyTags);
            Object.seal(textItem);
            
            this.mixedContent.push(textItem);
          }
        } else {
          // 代码部分
          this.mixedContent.push({ type: 'code', content: part });
        }
      });
      
      // 🔥 初始化可见内容：先渲染第一批
      this.initializeVisibleContent();
    },
    
    // 🔥 初始化可见内容：先渲染第一批，然后分批渲染剩余
    initializeVisibleContent() {
      this.visibleMixedContent = [];
      let totalChars = 0;
      const initialBatchSize = this.renderBatchSize * 2; // 初始渲染2批
      
      for (let i = 0; i < this.mixedContent.length; i++) {
        const item = this.mixedContent[i];
        
        if (item.type === 'text') {
          if (item.isSegment) {
            // 如果是分段，检查是否应该渲染
            if (totalChars < initialBatchSize) {
              this.visibleMixedContent.push(item);
              totalChars += item.content.length;
            } else {
              break; // 停止添加，剩余内容将在后续分批渲染
            }
          } else {
            // 非分段，直接添加
            this.visibleMixedContent.push(item);
            totalChars += item.content.length;
            if (totalChars >= initialBatchSize) {
              break;
            }
          }
        } else {
          // 代码块，直接添加
          this.visibleMixedContent.push(item);
        }
      }
      
      // 🔥 分批渲染剩余内容
      this.renderRemainingContent();
    },
    
    // 🔥 分批渲染剩余内容
    renderRemainingContent() {
      const currentVisibleCount = this.visibleMixedContent.length;
      const totalMixedCount = this.mixedContent.length;
      
      if (currentVisibleCount >= totalMixedCount) {
        // 所有内容已渲染
        return;
      }
      
      // 计算下一批要渲染的内容
      let totalChars = 0;
      const batchSize = this.renderBatchSize;
      
      for (let i = currentVisibleCount; i < this.mixedContent.length && totalChars < batchSize; i++) {
        const item = this.mixedContent[i];
        if (item.type === 'text') {
          totalChars += item.content.length;
        }
        this.visibleMixedContent.push(item);
      }
      
      // 🔥 使用requestAnimationFrame继续渲染下一批
      if (this.visibleMixedContent.length < this.mixedContent.length) {
        requestAnimationFrame(() => {
          this.renderRemainingContent();
        });
      }
    },
    
    // 🔥 优化样式绑定性能：返回字符串而不是对象，减少Vue响应式开销
    getCharStyle(colors, charIndex) {
      const color = colors[charIndex];
      return color && color !== 'black' ? `color: ${color}` : '';
    },
    
    // 🔥 获取字符类（包括修改标签类 - 优化版本）
    getCharClassWithModifyTag(char, index, text, tagRanges = null) {
      const baseClasses = this.getCharClass(char, index, text);
      const modifyTagClass = this.getModifyTagClass(text, index, tagRanges);
      return baseClasses + (modifyTagClass ? ' ' + modifyTagClass : '');
    },
    
    // 🔥 获取修改标签类名（优化版本 - 使用标签缓存）
    getModifyTagClass(text, index, tagRanges = null) {
      // 如果提供了标签范围缓存，使用缓存；否则使用旧的方法（向后兼容）
      if (tagRanges && tagRanges.length > 0) {
        // 从最内层（第7次）到最外层（第1次）检查，优先使用内层标签的样式
        const getModifyContentClass = (level) => {
          return `modify-content-${level}`;
        };
        for (let i = 7; i >= 1; i--) {
          for (const range of tagRanges) {
            if (range.level === i) {
              // 检查是否在标签内容内（不包括标签本身）
              if (index >= range.contentStart && index < range.contentEnd) {
                return getModifyContentClass(i);
              }
              // 检查是否在标签本身（用于淡化显示）
              if (index >= range.startPos && index < range.contentStart) {
                return 'modify-tag-fade'; // 标签开始部分淡化
              }
              if (index >= range.contentEnd && index < range.endPos) {
                return 'modify-tag-fade'; // 标签结束部分淡化
              }
            }
          }
        }
        return '';
      }
      
      // 向后兼容：如果没有缓存，使用旧方法（但这种情况应该很少）
      for (let i = 3; i >= 1; i--) {
        const startTag = `<第${i}次修改内容>`;
        const endTag = `</第${i}次修改内容>`;
        
        let pos = 0;
        while (true) {
          const startPos = text.indexOf(startTag, pos);
          if (startPos === -1) break;
          
          const endPos = text.indexOf(endTag, startPos);
          if (endPos === -1) break;
          
          const contentStart = startPos + startTag.length;
          const contentEnd = endPos;
          
          if (index >= contentStart && index < contentEnd) {
            return i === 1 ? 'modify-content-1' : (i === 2 ? 'modify-content-2' : 'modify-content-3');
          }
          
          pos = endPos + endTag.length;
        }
      }
      
      // 检查标签本身（用于淡化显示）
      for (let i = 1; i <= 7; i++) {
        const startTag = `<第${i}次修改内容>`;
        const endTag = `</第${i}次修改内容>`;
        
        let pos = 0;
        while (true) {
          const startPos = text.indexOf(startTag, pos);
          if (startPos === -1) break;
          
          const endPos = text.indexOf(endTag, startPos);
          if (endPos === -1) break;
          
          const contentStart = startPos + startTag.length;
          
          if (index >= startPos && index < contentStart) {
            return 'modify-tag-fade';
          }
          if (index >= endPos && index < endPos + endTag.length) {
            return 'modify-tag-fade';
          }
          
          pos = endPos + endTag.length;
        }
      }
      
      return '';
    },
    
    // 🔥 处理修改标签的方法 - 预先解析所有标签位置以提高性能
    processModifyTags(text) {
      // 预先解析所有标签位置，避免后续重复遍历
      const tagRanges = [];
      
      // 从最内层（第7次）到最外层（第1次）解析标签
      for (let i = 7; i >= 1; i--) {
        const startTag = `<第${i}次修改内容>`;
        const endTag = `</第${i}次修改内容>`;
        
        let pos = 0;
        while (true) {
          const startPos = text.indexOf(startTag, pos);
          if (startPos === -1) break;
          
          const endPos = text.indexOf(endTag, startPos);
          if (endPos === -1) break;
          
          const contentStart = startPos + startTag.length;
          const contentEnd = endPos;
          
          tagRanges.push({
            level: i,
            startPos: startPos,
            contentStart: contentStart,
            contentEnd: contentEnd,
            endPos: endPos + endTag.length,
            startTagLength: startTag.length,
            endTagLength: endTag.length
          });
          
          pos = endPos + endTag.length;
        }
      }
      
      // 按位置排序，确保正确的优先级处理
      tagRanges.sort((a, b) => a.startPos - b.startPos);
      
      return {
        text: text,
        tags: tagRanges // 保存标签信息用于后续快速查询
      };
    },
    
    // 🔥 预计算所有字符的类名，避免在模板渲染时重复计算（深度优化版本）
    precomputeCharClasses() {
      this.mixedContent.forEach((item, contentIndex) => {
        if (item.type !== 'text') return;
        
        const text = item.content;
        const textLength = text.length;
        const textArray = Array.from(text);
        
        // 🔥 预计算样式字符串数组，避免模板中函数调用（提升性能）
        item.charStyles = textArray.map((char, index) => {
          const color = item.colors[index];
          return color && color !== 'black' ? `color: ${color}` : '';
        });
        
        // 预计算反引号对（用于行内代码判断）
        const backtickPairs = this.findBacktickPairs(text);
        
        // 预计算链接位置（用于链接判断）
        const linkRanges = this.findLinkRanges(text);
        
        // 🔥 预计算所有行的起始位置和标记信息，避免重复计算
        const lines = text.split('\n');
        const lineStartIndices = [0]; // 每行的起始位置
        const lineMarkerInfo = []; // 每行的标记信息 {lineStart, markerLength, lineType}
        
        let currentPos = 0;
        lines.forEach((line, lineIndex) => {
          const lineStart = currentPos;
          lineStartIndices.push(currentPos + line.length + 1); // +1 for \n
          
          // 预计算行标记（只计算一次）
          const lineType = this.lineTypes[contentIndex] && this.lineTypes[contentIndex][lineStart] 
            ? this.lineTypes[contentIndex][lineStart] 
            : null;
          
          let markerLength = 0;
          if (lineType) {
            if (lineType.type === 'list-item') {
              const listMatch = line.match(/^(\s*[-*+]\s|\s*\d+\.\s)/);
              markerLength = listMatch ? listMatch[0].length : 0;
            } else if (lineType.type === 'blockquote') {
              const quoteMatch = line.match(/^(\s*>\s)/);
              markerLength = quoteMatch ? quoteMatch[0].length : 0;
            } else if (lineType.type === 'heading') {
              markerLength = lineType.level;
            }
          }
          
          lineMarkerInfo.push({ lineStart, markerLength, lineType });
          currentPos += line.length + 1;
        });
        
        // 🔥 预计算每个字符所在的行索引（使用二分查找优化）
        const getLineIndexForChar = (charIndex) => {
          // 使用二分查找找到字符所在的行
          let left = 0, right = lineStartIndices.length - 1;
          while (left < right) {
            const mid = Math.floor((left + right) / 2);
            if (charIndex < lineStartIndices[mid]) {
              right = mid;
            } else if (charIndex >= lineStartIndices[mid + 1]) {
              left = mid + 1;
            } else {
              return mid;
            }
          }
          return left;
        };
        
        // 🔥 批量预计算修改标签类名（避免重复遍历）
        const modifyTagClasses = new Array(textLength).fill('');
        if (item.modifyTags && item.modifyTags.length > 0) {
          // 按level分组，从内到外处理（支持1-7次修改）
          const getModifyContentClass = (level) => {
            return `modify-content-${level}`;
          };
          for (let level = 7; level >= 1; level--) {
            item.modifyTags.forEach(range => {
              if (range.level === level) {
                // 标签内容
                for (let i = range.contentStart; i < range.contentEnd; i++) {
                  if (i < textLength && !modifyTagClasses[i]) {
                    modifyTagClasses[i] = getModifyContentClass(level);
                  }
                }
                // 标签本身（淡化）
                for (let i = range.startPos; i < range.contentStart; i++) {
                  if (i < textLength && !modifyTagClasses[i]) {
                    modifyTagClasses[i] = 'modify-tag-fade';
                  }
                }
                for (let i = range.contentEnd; i < range.endPos && i < textLength; i++) {
                  if (!modifyTagClasses[i]) {
                    modifyTagClasses[i] = 'modify-tag-fade';
                  }
                }
              }
            });
          }
        }
        
        // 🔥 预计算样式字符串数组，避免模板中函数调用（提升性能）
        item.charStyles = textArray.map((char, index) => {
          const color = item.colors[index];
          return color && color !== 'black' ? `color: ${color}` : '';
        });
        
        // 为每个字符预计算类名
        item.charClasses = textArray.map((char, index) => {
          const classes = [];
          
          // 获取行索引和行信息
          const lineIndex = getLineIndexForChar(index);
          const lineInfo = lineMarkerInfo[lineIndex];
          
          if (lineInfo && lineInfo.lineType) {
            const lineType = lineInfo.lineType;
            const lineStart = lineInfo.lineStart;
            const markerLength = lineInfo.markerLength;
            
            if (lineType.type === 'heading') {
              classes.push(`h${lineType.level}-line`);
              if (index > lineStart + lineType.level) {
                classes.push(`h${lineType.level}-text`);
              }
            } else if (lineType.type === 'list-item') {
              classes.push('list-item-line');
              if (index >= lineStart && index < lineStart + markerLength) {
                classes.push('md-list-marker');
              }
            } else if (lineType.type === 'blockquote') {
              classes.push('blockquote-line');
              if (index >= lineStart && index < lineStart + markerLength) {
                classes.push('md-blockquote-marker');
              } else if (index >= lineStart + markerLength && index < lineStart + lineType.length) {
                classes.push('md-blockquote-content');
              }
            } else if (lineType.type === 'hr') {
              classes.push('hr-line');
            } else if (lineType.type === 'table-row') {
              classes.push('table-row-line');
              if (char === '|') {
                classes.push('md-table-marker');
              }
            }
          }
          
          // 行内代码判断（使用预计算的反引号对）
          let isInCode = false;
          for (const pair of backtickPairs) {
            if (index > pair.start && index < pair.end) {
              isInCode = true;
              classes.push('md-inline-code');
              break;
            }
          }
          if (!isInCode && char === '`') {
            classes.push('md-code-marker');
          }
          
          // 链接判断（使用预计算的链接范围）
          let isInLink = false;
          for (const linkRange of linkRanges) {
            if (index >= linkRange.textStart && index < linkRange.textEnd) {
              isInLink = true;
              classes.push('md-link-text');
              break;
            } else if ((index >= linkRange.textStart - 1 && index < linkRange.textStart) ||
                       (index >= linkRange.textEnd && index < linkRange.textEnd + 1) ||
                       (index >= linkRange.urlStart && index < linkRange.urlEnd)) {
              isInLink = true;
              classes.push('md-link-marker');
              break;
            }
          }
          
          // 标记符号
          if ((char === '*' || char === '_') && !classes.includes('md-link-text') && 
              !classes.includes('md-link-marker') && !classes.includes('md-inline-code')) {
            classes.push('md-marker');
          }
          
          // 修改标签类名（使用预计算的数组）
          if (modifyTagClasses[index]) {
            classes.push(modifyTagClasses[index]);
          }
          
          return classes.join(' ');
        });
      });
    },
    
    // 🔥 预计算所有链接范围，避免重复计算
    findLinkRanges(text) {
      const ranges = [];
      const linkPattern = /\[([^\]]+)\]\(([^)]+)\)/g;
      let match;
      
      while ((match = linkPattern.exec(text)) !== null) {
        ranges.push({
          textStart: match.index + 1, // [ 后的位置
          textEnd: match.index + 1 + match[1].length, // ] 前的位置
          urlStart: match.index + match[0].indexOf('(') + 1, // ( 后的位置
          urlEnd: match.index + match[0].length - 1 // ) 前的位置
        });
      }
      
      return ranges;
    },
    
    processAnswer() {
      // 与 processUpdateAnswer 相同的处理逻辑
      this.mixedContent = [];
      this.visibleMixedContent = []; // 🔥 重置可见内容
      const codeRegex = /```(.*?)```/gs;
      const textParts = this.answer.split(codeRegex);
      
      textParts.forEach((part, index) => {
        if (index % 2 === 0) {
          // 🔥 分批渲染：将长文本分段
          const processedContent = this.processModifyTags(part);
          const text = processedContent.text;
          const textLength = text.length;
          
          // 🔥 计算当前文本块在answer中的起始位置
          let textBlockStartInAnswer = 0;
          for (let k = 0; k < index; k++) {
            if (k % 2 === 0) {
              // 文本块
              const prevText = textParts[k];
              textBlockStartInAnswer += prevText.length;
            } else {
              // 代码块（包括标记）
              textBlockStartInAnswer += textParts[k].length + '``````'.length;
            }
          }
          
          // 如果文本很长，分段处理
          if (textLength > this.renderBatchSize) {
            const textArray = Array.from(text);
            const colors = textArray.map((char, idx) => 
              this.getTextColor(text, idx, processedContent.tags)
            );
            
            let startIndex = 0;
            let segmentIndex = 0;
            
            while (startIndex < textLength) {
              let endIndex = Math.min(startIndex + this.renderBatchSize, textLength);
              
              // 🔥 如果不是最后一段，尽量在换行符处分割
              if (endIndex < textLength) {
                let searchStart = Math.max(startIndex, endIndex - 200);
                let newlinePos = text.indexOf('\n', searchStart);
                if (newlinePos !== -1 && newlinePos < endIndex && newlinePos > startIndex + this.renderBatchSize * 0.8) {
                  endIndex = newlinePos + 1;
                }
              }
              
              const segmentText = text.substring(startIndex, endIndex);
              const segmentColors = segmentText.split('').map((char, idx) => colors[startIndex + idx]);
              
              // 🔥 将modifyTags转换为相对于本段的相对位置
              const segmentTags = processedContent.tags.map(tag => {
                const tagStart = tag.startPos;
                const tagEnd = tag.endPos;
                
                if (tagEnd <= startIndex || tagStart >= endIndex) {
                  return null;
                }
                
                const relativeStart = Math.max(0, tagStart - startIndex);
                const relativeContentStart = Math.max(0, tag.contentStart - startIndex);
                const relativeContentEnd = Math.min(endIndex - startIndex, tag.contentEnd - startIndex);
                const relativeEnd = Math.min(endIndex - startIndex, tagEnd - startIndex);
                
                if (relativeEnd <= 0 || relativeStart >= (endIndex - startIndex)) {
                  return null;
                }
                
                return {
                  level: tag.level,
                  startPos: relativeStart,
                  contentStart: relativeContentStart,
                  contentEnd: relativeContentEnd,
                  endPos: relativeEnd,
                  startTagLength: tag.startTagLength,
                  endTagLength: tag.endTagLength
                };
              }).filter(tag => tag !== null);
              
              // 创建分段item
              const segmentItem = { 
                type: 'text', 
                content: segmentText,
                colors: segmentColors,
                modifyTags: segmentTags, // 🔥 使用转换后的相对位置标签
                charClasses: null,
                charStyles: null,
                originalStartIndex: startIndex,
                originalEndIndex: endIndex,
                isSegment: true,
                segmentIndex: segmentIndex,
                textBlockStartInAnswer: textBlockStartInAnswer // 🔥 记录原始文本块在answer中的起始位置
              };
              
              Object.freeze(segmentItem.colors);
              Object.freeze(segmentItem.modifyTags);
              Object.seal(segmentItem);
              
              this.mixedContent.push(segmentItem);
              startIndex = endIndex;
              segmentIndex++;
            }
          } else {
            // 短文本，正常处理
            const processedContent = this.processModifyTags(part);
            const textArray = Array.from(processedContent.text);
            const colors = textArray.map((char, idx) => 
              this.getTextColor(processedContent.text, idx, processedContent.tags)
            );
            
            const textItem = { 
              type: 'text', 
              content: processedContent.text,
              colors: colors,
              modifyTags: processedContent.tags,
              charClasses: null,
              charStyles: null,
              isSegment: false
            };
            
            Object.freeze(textItem.colors);
            Object.freeze(textItem.modifyTags);
            Object.seal(textItem);
            
            this.mixedContent.push(textItem);
          }
        } else {
          this.mixedContent.push({ type: 'code', content: part });
        }
      });
      
      // 🔥 初始化可见内容：先渲染第一批
      this.initializeVisibleContent();
    },
    
    copyCode(code, event) {
      // 阻止事件冒泡，防止点击事件继续传播
      if (event) {
        event.stopPropagation();
        event.preventDefault();
      }

      navigator.clipboard.writeText(code)
        .then(() => {
          this.$message.success('代码已复制');
        })
        .catch(err => {
          console.error('代码复制失败', err);
        });
    },
    
    // 🔥 处理单击事件，计算全局字符位置并存储到event对象（用于编辑功能）
    handleClick(event, item, contentIndex) {
      // 不阻止事件冒泡，让父组件的click事件也能收到
      // 但是我们会在event对象上添加一个属性，供父组件使用
      
      if (!event || !event.target) {
        console.log('[AnswerParser handleClick] event或event.target为空');
        return;
      }
      
      // 🔥 使用与startFromSelection相同的方式获取段落容器和span
      const paragraphRef = this.$refs[`paragraph${contentIndex}`];
      if (!paragraphRef || !paragraphRef[0]) {
        console.log('[AnswerParser handleClick] 未找到paragraph ref');
        return;
      }
      
      const paragraphContainer = paragraphRef[0];
      
      // 找到点击的span元素
      const clickedSpan = event.target.closest('span');
      if (!clickedSpan) {
        console.log('[AnswerParser handleClick] 未找到span元素');
        return;
      }
      
      // 🔥 使用与startFromSelection完全相同的方式获取所有span
      const allSpans = paragraphContainer.getElementsByTagName('span');
      const spanIndex = Array.from(allSpans).indexOf(clickedSpan);
      
      console.log(`[AnswerParser handleClick] 点击的span索引: ${spanIndex}, 总span数: ${allSpans.length}`);
      console.log(`[AnswerParser handleClick] 点击的span内容: "${clickedSpan.textContent}"`);
      
      if (spanIndex === -1) {
        console.log('[AnswerParser handleClick] 无法找到span索引');
        return;
      }
      
      // 🔥 找到对应的mixedContent索引（使用与startFromSelection相同的逻辑）
      const visibleItem = this.visibleMixedContent[contentIndex];
      console.log(`[AnswerParser handleClick] visibleItem:`, {
        isSegment: visibleItem?.isSegment,
        textBlockStartInAnswer: visibleItem?.textBlockStartInAnswer,
        originalStartIndex: visibleItem?.originalStartIndex,
        contentLength: visibleItem?.content?.length,
        contentPreview: visibleItem?.content?.substring(0, 50)
      });
      
      let mixedContentIndex = -1;
      
      for (let i = 0; i < this.mixedContent.length; i++) {
        if (this.mixedContent[i] === visibleItem) {
          mixedContentIndex = i;
          break;
        }
      }
      
      if (mixedContentIndex === -1) {
        console.log('[AnswerParser handleClick] 无法找到mixedContent索引');
        return;
      }
      
      console.log(`[AnswerParser handleClick] mixedContentIndex: ${mixedContentIndex}`);
      
      // 🔥 计算总偏移量：基于answer文本的绝对位置（与startFromSelection相同的逻辑）
      let totalOffset = 0;
      
      if (visibleItem.isSegment && visibleItem.textBlockStartInAnswer !== undefined) {
        // 🔥 分段：使用textBlockStartInAnswer + originalStartIndex + spanIndex
        totalOffset = visibleItem.textBlockStartInAnswer + (visibleItem.originalStartIndex || 0) + spanIndex;
        console.log(`[AnswerParser handleClick] 分段计算: textBlockStartInAnswer=${visibleItem.textBlockStartInAnswer}, originalStartIndex=${visibleItem.originalStartIndex || 0}, spanIndex=${spanIndex}, totalOffset=${totalOffset}`);
      } else if (visibleItem.textBlockStartInAnswer !== undefined) {
        // 🔥 非分段：使用textBlockStartInAnswer + spanIndex
        totalOffset = visibleItem.textBlockStartInAnswer + spanIndex;
        console.log(`[AnswerParser handleClick] 非分段计算: textBlockStartInAnswer=${visibleItem.textBlockStartInAnswer}, spanIndex=${spanIndex}, totalOffset=${totalOffset}`);
      } else {
        // fallback：通过查找content在answer中的位置来确定（与startFromSelection保持一致）
        const searchText = visibleItem.content.substring(0, Math.min(100, visibleItem.content.length));
        const posInAnswer = this.answer.indexOf(searchText);
        
        if (posInAnswer !== -1) {
          totalOffset = posInAnswer + spanIndex;
          console.log(`[AnswerParser handleClick] fallback通过indexOf: posInAnswer=${posInAnswer}, spanIndex=${spanIndex}, totalOffset=${totalOffset}`);
        } else {
          // 最后的fallback：累加前面所有item的长度
          let codeBlockMarkerLength = 0;
          for (let i = 0; i < mixedContentIndex; i++) {
            const prevItem = this.mixedContent[i];
            if (prevItem.type === 'text') {
              totalOffset += prevItem.content.length;
            } else {
              totalOffset += prevItem.content.length;
              codeBlockMarkerLength += '``````'.length;
            }
          }
          totalOffset += spanIndex + codeBlockMarkerLength;
          console.log(`[AnswerParser handleClick] 最后fallback: 累加前面=${totalOffset - spanIndex - codeBlockMarkerLength}, spanIndex=${spanIndex}, codeBlockMarkerLength=${codeBlockMarkerLength}, totalOffset=${totalOffset}`);
        }
      }
      
      // 🔥 显示计算出的位置对应的字符内容
      const charAtPos = this.answer[totalOffset];
      const contextStart = Math.max(0, totalOffset - 50);
      const contextEnd = Math.min(this.answer.length, totalOffset + 50);
      const contextBefore = this.answer.substring(contextStart, totalOffset);
      const contextAfter = this.answer.substring(totalOffset + 1, contextEnd);
      
      console.log(`[AnswerParser handleClick] 计算出的位置: ${totalOffset}, 该位置的字符: "${charAtPos}"`);
      console.log(`[AnswerParser handleClick] 位置上下文前: "${contextBefore.replace(/\n/g, '\\n')}"`);
      console.log(`[AnswerParser handleClick] 位置上下文后: "${contextAfter.replace(/\n/g, '\\n')}"`);
      
      // 🔥 将计算出的位置和上下文信息存储到event对象上，供父组件使用
      event._calculatedCharPosition = totalOffset;
      event._calculatedCharContext = {
        char: charAtPos,
        before: contextBefore, // 位置前的文本（最多50字符）
        after: contextAfter    // 位置后的文本（最多50字符）
      };
    },
    
    startFromSelection(event, content, contentIndex) {
      if(this.isDoubleAble === true) {
        this.isDoubleAble = false
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
          const range = selection.getRangeAt(0);
          const clickedSpan = range.startContainer.parentNode;  // 获取点击的 span
          const allSpans = this.$refs[`paragraph${contentIndex}`][0].getElementsByTagName('span');
          const startOffset = Array.from(allSpans).indexOf(clickedSpan);  // 获取点击的 span 的索引

          if (startOffset !== -1) {
            // 🔥 找到对应的mixedContent索引和item
            const visibleItem = this.visibleMixedContent[contentIndex];
            let mixedContentIndex = -1;
            
            // 在mixedContent中找到对应的item
            for (let i = 0; i < this.mixedContent.length; i++) {
              if (this.mixedContent[i] === visibleItem) {
                mixedContentIndex = i;
                break;
              }
            }
            
            if (mixedContentIndex === -1) {
              console.error('[AnswerParser] 无法找到对应的mixedContent索引');
              this.isDoubleAble = true; // 恢复状态
              return;
            }
            
            // 🔥 计算总偏移量：基于answer文本的绝对位置
            let totalOffset = 0;
            
            if (visibleItem.isSegment && visibleItem.textBlockStartInAnswer !== undefined) {
              // 🔥 分段：使用textBlockStartInAnswer + originalStartIndex + startOffset
              totalOffset = visibleItem.textBlockStartInAnswer + (visibleItem.originalStartIndex || 0) + startOffset;
            } else {
              // 🔥 非分段：通过查找content在answer中的位置来确定
              const searchText = visibleItem.content.substring(0, Math.min(100, visibleItem.content.length));
              const posInAnswer = this.answer.indexOf(searchText);
              
              if (posInAnswer !== -1) {
                totalOffset = posInAnswer + startOffset;
              } else {
                // fallback：累加前面所有item的长度
                let codeBlockMarkerLength = 0;
                for (let i = 0; i < mixedContentIndex; i++) {
                  const item = this.mixedContent[i];
                  if (item.type === 'text') {
                    totalOffset += item.content.length;
                  } else {
                    totalOffset += item.content.length;
                    codeBlockMarkerLength += '``````'.length;
                  }
                }
                totalOffset += startOffset + codeBlockMarkerLength;
              }
            }

            // 高亮双击的位置开始的 15 个字符
            this.highlightText(totalOffset, content, contentIndex);

            // 现在 totalOffset 是整个文本中的精确位置，包括代码块的长度
            this.$emit('startReading', totalOffset, this.answer);
          } else {
            // 如果找不到点击的span，恢复状态
            this.isDoubleAble = true;
          }
        }
      } else {
        this.$message.error('您操作过快，请您稍等2s，再点读其他位置');
      }
    },
    
    highlightText(startIndex, content, contentIndex) {
      const paragraph = this.$refs[`paragraph${contentIndex}`]; // 获取对应段落的 DOM 元素
      if (!paragraph || !paragraph[0]) {
        console.error('[AnswerParser] 无法找到段落DOM元素');
        return;
      }
      
      const paragraphEl = paragraph[0];
      
      // 🔥 找到对应的mixedContent索引
      const visibleItem = this.visibleMixedContent[contentIndex];
      let mixedContentIndex = -1;
      for (let i = 0; i < this.mixedContent.length; i++) {
        if (this.mixedContent[i] === visibleItem) {
          mixedContentIndex = i;
          break;
        }
      }
      
      if (mixedContentIndex === -1) {
        console.error('[AnswerParser] 无法找到对应的mixedContent索引');
        this.isDoubleAble = true; // 🔥 重置状态，避免卡死
        return;
      }

      // 🔥 计算当前段落的总偏移量（基于mixedContent）
      let totalOffset = 0;
      for (let i = 0; i < mixedContentIndex; i++) {
        const item = this.mixedContent[i];
        if (item.type === 'text') {
          if (item.isSegment) {
            // 分段：累加同一文本块的所有分段
            let segmentGroupLength = item.content.length;
            let j = i + 1;
            while (j < this.mixedContent.length && this.mixedContent[j].isSegment) {
              if (this.mixedContent[j].segmentIndex === this.mixedContent[j - 1].segmentIndex + 1) {
                segmentGroupLength += this.mixedContent[j].content.length;
              } else {
                break;
              }
              j++;
            }
            totalOffset += segmentGroupLength;
            i = j - 1;
          } else {
            totalOffset += item.content.length;
          }
        } else {
          // 代码块：不需要减去``````，因为startIndex已经包含了
          // 这里只是计算文本偏移，代码块的标记不影响文本位置
        }
      }
      
      // 🔥 如果是分段，需要调整totalOffset
      if (visibleItem.isSegment) {
        // 找到当前分段所属的原始文本块的起始位置
        // 通过查找segmentIndex=0的分段来确定文本块的起始位置
        let blockStartOffset = 0;
        for (let i = 0; i < mixedContentIndex; i++) {
          const item = this.mixedContent[i];
          if (item.isSegment && item.segmentIndex === 0) {
            // 这是一个新的文本块的开始，累加前面所有item的长度
            break;
          }
        }
        // totalOffset需要调整为：前面所有完整item的长度 + 当前文本块内前面所有分段的长度 + originalStartIndex
        // 但实际上，由于我们已经在循环中累加了分段长度，所以totalOffset已经包含了当前文本块前面所有分段的长度
        // 我们需要减去这些长度，然后加上originalStartIndex
        let currentBlockPrevSegmentsLength = 0;
        for (let i = 0; i < mixedContentIndex; i++) {
          const item = this.mixedContent[i];
          if (item.isSegment) {
            // 查找连续的分段，看是否属于同一文本块
            if (i > 0 && this.mixedContent[i-1].isSegment && 
                item.segmentIndex === this.mixedContent[i-1].segmentIndex + 1) {
              // 连续分段，累加长度
              currentBlockPrevSegmentsLength += item.content.length;
            } else if (item.segmentIndex === 0) {
              // 新的文本块开始，重置
              currentBlockPrevSegmentsLength = 0;
            }
          } else {
            // 非分段item，重置（说明分段组结束了）
            currentBlockPrevSegmentsLength = 0;
          }
        }
        // 调整totalOffset：减去当前文本块前面分段的长度（已经在totalOffset中），加上originalStartIndex
        totalOffset = totalOffset - currentBlockPrevSegmentsLength + (visibleItem.originalStartIndex || 0);
      }

      // 计算高亮范围（相对于当前段落的局部位置）
      const localStartIndex = startIndex - totalOffset;
      const localEndIndex = Math.min(localStartIndex + this.highlightDuration, content.length);

      // 检查高亮位置是否在当前段落范围内
      if (localStartIndex < 0 || localStartIndex >= content.length) {
        console.warn('[AnswerParser] 高亮位置超出当前段落范围', { startIndex, totalOffset, localStartIndex, contentLength: content.length });
        this.isDoubleAble = true; // 🔥 重置状态，避免卡死
        return;
      }

      // 获取所有span元素
      const spans = paragraphEl.querySelectorAll('.markdown-text span');
      
      // 找到需要高亮的span范围
      const startSpanIndex = localStartIndex;
      const endSpanIndex = Math.min(localEndIndex, spans.length);

      // 为需要高亮的span添加高亮样式类
      for (let i = startSpanIndex; i < endSpanIndex; i++) {
        if (spans[i]) {
          spans[i].classList.add('highlighted-text');
          spans[i].style.transition = 'color 0.4s ease';
        }
      }

      // 触发过渡到红色
      setTimeout(() => {
        for (let i = startSpanIndex; i < endSpanIndex; i++) {
          if (spans[i]) {
            spans[i].style.color = 'red';
          }
        }
      }, 10); // 微小的延迟来确保过渡被触发

      // 2.3 秒后逐渐恢复原来的颜色
      setTimeout(() => {
        for (let i = startSpanIndex; i < endSpanIndex; i++) {
          if (spans[i]) {
            spans[i].style.color = 'black'; // 恢复为黑色（0.4秒的过渡）
          }
        }
        
        // 0.4 秒后移除高亮样式类
        setTimeout(() => {
          for (let i = startSpanIndex; i < endSpanIndex; i++) {
            if (spans[i]) {
              spans[i].classList.remove('highlighted-text');
              spans[i].style.transition = '';
              spans[i].style.color = ''; // 恢复原始颜色
            }
          }
          this.isDoubleAble = true; // 允许下次双击
          this.$emit("doubleClickOver")
        }, 400);
      }, 2300);
    }
  }
}
</script>

<style scoped>
  /* 保留原始代码块样式 */
  .original-code-block {
    position: relative;
    background: #4b5462;
    border-radius: 8px;
    padding: 15px;
    margin: 15px 0;
    overflow: auto;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  }

  /* 代码块中的按钮样式 */
  .copy-button {
      position: absolute;
      top: 10px;
      right: 10px;
      background: #96efff;
      color: #282c34;
      border: none;
      border-radius: 4px;
      padding: 4px 8px;
      cursor: pointer;
      transition: background 0.3s ease;
      font-size: 0.8em;
  }

  .copy-button:hover {
      background: #466cca;
  }

  /* 代码样式 */
  pre {
      margin: 0;
      white-space: pre-wrap; /* 确保换行 */
      color: #f8f8f2;
  }

  code {
      display: block;
      overflow: auto;
      /* font-family: 'Fira Code', monospace;  */
      font-family: 'Consolas', 'Monaco', 'Courier New', monospace;    /* 可以自定义字体 */
      font-size: 0.8em;
  }
  
  /* Markdown容器 */
  .markdown-container {
    position: relative;
    max-width: 100%;
    margin-bottom: 8px;
    /* 🔥 使用containment优化渲染性能，减少重排重绘范围 */
    contain: layout style paint;
    /* 🔥 使用transform优化合成层，提升渲染性能 */
    will-change: contents;
  }
  
  /* Markdown文本样式 */
  .markdown-text {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    line-height: 1.5;
    word-wrap: break-word;
    color: #24292e;
    /* 🔥 使用containment优化渲染性能 */
    contain: layout style;
    /* 🔥 优化文本渲染 */
    text-rendering: optimizeSpeed;
    -webkit-font-smoothing: antialiased;
  }
  
  /* 控制行间距 */
  .markdown-text span {
    white-space: pre-wrap;
    display: inline;
    /* 🔥 优化大量span元素的渲染性能 */
    contain: style;
    /* 🔥 减少重排，使用transform代替位置变化 */
    transform: translateZ(0);
  }
  
  /* 标题样式 - 明确区分不同级别 */
  .h1-line {
    line-height: 1.25;
  }
  
  .h2-line {
    line-height: 1.25;
  }
  
  .h3-line {
    line-height: 1.25;
  }
  
  .h4-line {
    line-height: 1.25;
  }
  
  .h5-line, .h6-line {
    line-height: 1.25;
  }
  
  /* 标题文本样式 */
  .h1-text {
    font-size: 2em !important;
    font-weight: 600 !important;
  }
  
  .h2-text {
    font-size: 1.5em !important;
    font-weight: 600 !important;
  }
  
  .h3-text {
    font-size: 1.25em !important;
    font-weight: 600 !important;
  }
  
  .h4-text {
    font-size: 1.1em !important;
    font-weight: 600 !important;
  }
  
  .h5-text, .h6-text {
    font-size: 0.9em !important;
    font-weight: 600 !important;
  }
  
  /* 标题标记符号样式 */
  .md-heading-marker {
    color: #9a9a9a !important;
    opacity: 0.35 !important;
  }
  
  /* 标题空格样式 */
  .md-heading-space {
    opacity: 0.35 !important;
  }
  
  /* 列表样式 */
  .list-item-line {
    margin: 0.25em 0;
    padding-left: 0;
  }
  
  /* 列表标记符号样式 */
  .md-list-marker {
    color: #9a9a9a !important;
    opacity: 0.5;
  }
  
  /* 引用块样式 */
  .blockquote-line {
    color: #6a737d;
    border-left: 0.25em solid #dfe2e5;
    margin: 0;
    padding-left: 1em;
  }
  
  /* 引用标记样式 */
  .md-blockquote-marker {
    color: #9a9a9a !important;
    opacity: 0.5;
    letter-spacing: -0.02em;
    margin-right: 0.1em;
  }
  
  /* 引用内容样式 */
  .md-blockquote-content {
    color: #444;
    letter-spacing: 0.01em;
  }
  
  /* 水平线样式 */
  .hr-line {
    height: 1px;
    background-color: #e1e4e8;
    margin: 16px 0;
    padding: 0;
    border: 0;
  }
  
  /* 水平线标记符号 */
  .md-hr-char {
    opacity: 0 !important;
  }
  
  /* 插入的HR元素 */
  .md-hr-container {
    height: 1px;
    background-color: #ddd;
    margin: 16px 0;
    width: 100%;
  }
  
  /* 表格样式 */
  .table-row-line {
    margin: 0;
    padding: 0;
  }
  
  /* 表格标记符号样式 */
  .md-table-marker {
    color: #9a9a9a !important;
    opacity: 0.5;
  }
  
  /* 表格原始字符 */
  .md-table-original-char {
    opacity: 0 !important;
  }
  
  /* 表格容器样式 */
  .md-table-container {
    margin: 16px 0;
    overflow-x: auto;
  }
  
  /* 表格样式 */
  .md-table {
    border-collapse: collapse;
    width: 100%;
  }
  
  /* 表格单元格样式 */
  .md-table th, .md-table td {
    padding: 8px 13px;
    border: 1px solid #dfe2e5;
    text-align: left;
  }
  
  /* 表格表头样式 */
  .md-table th {
    background-color: #f6f8fa;
    font-weight: 600;
    text-align: center;
  }
  
  /* 表格奇偶行颜色交替 */
  .md-table tr:nth-child(even) {
    background-color: #f6f8fa;
  }
  
  .md-table tr:nth-child(odd) {
    background-color: #ffffff;
  }
  
  /* 加粗文本 */
  .md-bold {
    font-weight: 600;
  }
  
  /* 加粗+斜体文本（用户编辑的内容） */
  .md-bold-italic {
    font-weight: 600;
    font-style: italic;
  }
  
  /* 加粗标记 */
  .md-bold-marker {
    color: #9a9a9a !important;
    opacity: 0.35;
  }
  
  /* 行内代码 */
  .md-inline-code {
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.95em;
    background: linear-gradient(135deg, #ded2ef 0%, #c5c7eb 50%, #dbd2ef 100%);
    color: #e83e8c;
    /* padding: 0.15em 0.3em; */
    border-radius: 1px;
    /* border: 1px solid rgba(27, 31, 35, 0.1); */
    font-weight: 500;
    letter-spacing: -0.01em;
    display: inline-block;
    white-space: nowrap;
    box-shadow: 0 4px 2px rgba(0,0,0,0.05), inset 0 1px 0 rgba(255,255,255,0.8);
    text-shadow: 0 1px 0 rgba(255,255,255,0.5);
    /* margin: 0 0.1em; */
    /* 🔥 优化渲染性能 */
    contain: style;
    transform: translateZ(0);
  }
  
  /* 代码标记符号 */
  .md-code-marker {
    color: #9a9a9a !important;
    opacity: 0.5;
  }
  
  /* 链接文本 */
  .md-link-text {
    color: #0366d6 !important;
    text-decoration: underline;
  }
  
  /* 链接标记符号 */
  .md-link-marker {
    color: #9a9a9a !important;
    opacity: 0.35;
  }
  
  /* 其他标记符号 */
  .md-marker {
    color: #9a9a9a !important;
    opacity: 0.35;
  }
  
  /* 空格和换行符处理 */
  .markdown-text span:empty {
    line-height: 1;
  }
  
  /* 连续换行处理 */
  .markdown-text span:empty + span:empty {
    line-height: 0.7;
  }
  
  /* 修复占位符相关样式 */
  .md-table-placeholder {
    display: none;
    height: 0;
    width: 0;
    position: absolute;
    overflow: hidden;
  }


  /* 图片容器样式 */
  .md-image-container {
    margin: 16px 0;
    text-align: center;
  }

  /* 渲染的图片样式 */
  .md-rendered-image {
    max-width: 100%;
    margin: 0 auto;
    display: block;
    border-radius: 4px;
  }

  /* 高亮文本样式 */
  .highlighted-text {
    transition: color 0.4s ease;
  }
  
  /* 🔥 修改标签样式 - 第1次修改（红色） */
  .modify-tag-1 {
    background: linear-gradient(135deg, rgba(255, 200, 200, 0.4) 0%, rgba(255, 180, 180, 0.5) 100%);
    border-left: 3px solid rgba(255, 100, 100, 0.8);
    padding: 2px 4px;
    border-radius: 3px;
    margin: 0 1px;
    display: inline;
    box-shadow: 0 1px 2px rgba(255, 100, 100, 0.2);
  }
  
  /* 🔥 修改标签样式 - 第2次修改（蓝色） */
  .modify-tag-2 {
    background: linear-gradient(135deg, rgba(200, 220, 255, 0.4) 0%, rgba(180, 200, 255, 0.5) 100%);
    border-left: 3px solid rgba(100, 150, 255, 0.8);
    padding: 2px 4px;
    border-radius: 3px;
    margin: 0 1px;
    display: inline;
    box-shadow: 0 1px 2px rgba(100, 150, 255, 0.2);
  }
  
  /* 🔥 修改标签样式 - 第3次修改（紫色） */
  .modify-tag-3 {
    background: linear-gradient(135deg, rgba(230, 200, 255, 0.4) 0%, rgba(220, 180, 255, 0.5) 100%);
    border-left: 3px solid rgba(180, 100, 255, 0.8);
    padding: 2px 4px;
    border-radius: 3px;
    margin: 0 1px;
    display: inline;
    box-shadow: 0 1px 2px rgba(180, 100, 255, 0.2);
  }
  
  /* 🔥 修改标签淡化（标签本身淡化显示，保持可见以确保双击读功能正常） */
  .modify-tag-fade {
    opacity: 0.25 !important;
    color: #999 !important;
    font-size: 0.85em;
  }
  
  /* 🔥 修改内容样式 - 第1次修改（红色背景，连续无断开） */
  .modify-content-1 {
    background: linear-gradient(135deg, rgba(255, 220, 220, 0.4) 0%, rgba(255, 200, 200, 0.5) 100%) !important;
    border-left: 2px solid rgba(255, 120, 120, 0.7) !important;
    padding-left: 2px;
    padding-right: 0;
    padding-top: 0;
    padding-bottom: 0;
    border-radius: 0;
    margin: 0;
    display: inline;
    letter-spacing: normal !important;
    /* 🔥 优化渲染性能 */
    contain: style;
    transform: translateZ(0);
  }
  
  /* 后续字符去掉左边框，保持连续 */
  .modify-content-1 + .modify-content-1 {
    border-left: none !important;
    padding-left: 0;
  }
  
  /* 🔥 修改内容样式 - 第2次修改（蓝色背景，连续无断开） */
  .modify-content-2 {
    background: linear-gradient(135deg, rgba(220, 230, 255, 0.4) 0%, rgba(200, 220, 255, 0.5) 100%) !important;
    border-left: 2px solid rgba(120, 160, 255, 0.7) !important;
    padding-left: 2px;
    padding-right: 0;
    padding-top: 0;
    padding-bottom: 0;
    border-radius: 0;
    margin: 0;
    display: inline;
    letter-spacing: normal !important;
    /* 🔥 优化渲染性能 */
    contain: style;
    transform: translateZ(0);
  }
  
  /* 后续字符去掉左边框，保持连续 */
  .modify-content-2 + .modify-content-2 {
    border-left: none !important;
    padding-left: 0;
  }
  
  /* 🔥 修改内容样式 - 第3次修改（紫色背景，连续无断开） */
  .modify-content-3 {
    background: linear-gradient(135deg, rgba(240, 220, 255, 0.4) 0%, rgba(230, 200, 255, 0.5) 100%) !important;
    border-left: 2px solid rgba(200, 120, 255, 0.7) !important;
    padding-left: 2px;
    padding-right: 0;
    padding-top: 0;
    padding-bottom: 0;
    border-radius: 0;
    margin: 0;
    display: inline;
    letter-spacing: normal !important;
    /* 🔥 优化渲染性能 */
    contain: style;
    transform: translateZ(0);
  }
  
  /* 后续字符去掉左边框，保持连续 */
  .modify-content-3 + .modify-content-3 {
    border-left: none !important;
    padding-left: 0;
  }
  
  /* 🔥 修改内容样式 - 第4次修改（黄色背景，连续无断开） */
  .modify-content-4 {
    background: linear-gradient(135deg, rgba(255, 245, 200, 0.4) 0%, rgba(255, 235, 180, 0.5) 100%) !important;
    border-left: 2px solid rgba(255, 165, 0, 0.7) !important;
    padding-left: 2px;
    padding-right: 0;
    padding-top: 0;
    padding-bottom: 0;
    border-radius: 0;
    margin: 0;
    display: inline;
    letter-spacing: normal !important;
    /* 🔥 优化渲染性能 */
    contain: style;
    transform: translateZ(0);
  }
  
  .modify-content-4 + .modify-content-4 {
    border-left: none !important;
    padding-left: 0;
  }
  
  /* 🔥 修改内容样式 - 第5次修改（橙色背景，连续无断开） */
  .modify-content-5 {
    background: linear-gradient(135deg, rgba(255, 230, 180, 0.4) 0%, rgba(255, 210, 160, 0.5) 100%) !important;
    border-left: 2px solid rgba(255, 140, 0, 0.7) !important;
    padding-left: 2px;
    padding-right: 0;
    padding-top: 0;
    padding-bottom: 0;
    border-radius: 0;
    margin: 0;
    display: inline;
    letter-spacing: normal !important;
    /* 🔥 优化渲染性能 */
    contain: style;
    transform: translateZ(0);
  }
  
  .modify-content-5 + .modify-content-5 {
    border-left: none !important;
    padding-left: 0;
  }
  
  /* 🔥 修改内容样式 - 第6次修改（绿色背景，连续无断开） */
  .modify-content-6 {
    background: linear-gradient(135deg, rgba(220, 255, 220, 0.4) 0%, rgba(200, 255, 200, 0.5) 100%) !important;
    border-left: 2px solid rgba(50, 205, 50, 0.7) !important;
    padding-left: 2px;
    padding-right: 0;
    padding-top: 0;
    padding-bottom: 0;
    border-radius: 0;
    margin: 0;
    display: inline;
    letter-spacing: normal !important;
    /* 🔥 优化渲染性能 */
    contain: style;
    transform: translateZ(0);
  }
  
  .modify-content-6 + .modify-content-6 {
    border-left: none !important;
    padding-left: 0;
  }
  
  /* 🔥 修改内容样式 - 第7次修改（青色背景，连续无断开） */
  .modify-content-7 {
    background: linear-gradient(135deg, rgba(200, 255, 255, 0.4) 0%, rgba(180, 240, 240, 0.5) 100%) !important;
    border-left: 2px solid rgba(0, 206, 209, 0.7) !important;
    padding-left: 2px;
    padding-right: 0;
    padding-top: 0;
    padding-bottom: 0;
    border-radius: 0;
    margin: 0;
    display: inline;
    letter-spacing: normal !important;
    /* 🔥 优化渲染性能 */
    contain: style;
    transform: translateZ(0);
  }
  
  .modify-content-7 + .modify-content-7 {
    border-left: none !important;
    padding-left: 0;
  }
</style>
