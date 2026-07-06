import katex from 'katex'

/** Markdown 表格列分隔符占位符（仅用于 $...$ 内的 |，渲染前还原） */
const MATH_PIPE_PLACEHOLDER = '\uE000'

/** 收紧 $ 定界符内侧空格（markdown-it-katex 要求 $ 紧贴内容） */
export function tightenMathDelimiters(text: string): string {
  return text.replace(/\$\s+/g, '$').replace(/\s+\$/g, '$')
}

/** 表格单元格公式内的 | 会破坏 Markdown 表格，先换成占位符 */
export function escapePipesInMathForMarkdown(text: string): string {
  return text.replace(/\$([^$\n]+?)\$/g, (_match, latex: string) => {
    return `$${latex.replace(/\|/g, MATH_PIPE_PLACEHOLDER)}$`
  })
}

function restoreMathPipePlaceholders(latex: string): string {
  return latex.replace(new RegExp(MATH_PIPE_PLACEHOLDER, 'g'), '|')
}

/** 修复 MinerU 切割错误：$\alpha \cdot$$\beta$ → $\alpha \cdot$ $\beta$ */
export function fixBrokenInlineDelimiters(text: string): string {
  return text.replace(/(\$[^$\n]*?)\$\$(\\[a-zA-Z]+)/g, (_, open, cmd) => `${open}$ $${cmd}`)
}

/** 裸 LaTeX 段落（无 $ 包裹，以 \frac / \alpha 等开头） */
export function looksLikeBareLatex(text: string): boolean {
  const t = text.trim()
  if (!t || t.includes('$') || /[\u4e00-\u9fff]/.test(t)) return false
  if (!t.startsWith('\\')) return false
  const signals =
    /\\(?:frac|sum|prod|int|lim|alpha|beta|gamma|lambda|sigma|varepsilon|mathcal|mathrm|mathbf|operatorname|qquad|quad|cdot|tag|text|begin|left|right|vert|in)/ 
  return signals.test(t) && t.length < 2000
}

/** 占位符：Markdown 解析前保护 $...$ / $$...$$，避免 _ 强调与括号误转换 */
const MATH_SLOT_OPEN = '\uFFF0'
const MATH_SLOT_CLOSE = '\uFFF1'

export interface MathSlot {
  latex: string
  display: boolean
}

function protectInlineMathLine(line: string, slots: MathSlot[]): string {
  if (!line.includes('$') || line.includes(MATH_SLOT_OPEN)) return line

  const merged = mergeFragmentedInlineMath(line)
  const indices: number[] = []
  for (let i = 0; i < merged.length; i += 1) {
    if (merged[i] === '$' && merged[i + 1] !== '$') indices.push(i)
  }
  if (indices.length < 2) return merged

  // 一行内多对 $：优先合并为 first…last 整段公式
  if (indices.length > 2) {
    const inner = merged.slice(indices[0] + 1, indices[indices.length - 1])
    if (/\\left|\\right|_\{|\\text|\\frac|=/.test(inner)) {
      const id = slots.length
      slots.push({ latex: stripLatexDelimiters(inner.trim()), display: false })
      return (
        merged.slice(0, indices[0]) +
        `${MATH_SLOT_OPEN}${id}${MATH_SLOT_CLOSE}` +
        merged.slice(indices[indices.length - 1] + 1)
      )
    }
  }

  // 单对 $
  const id = slots.length
  slots.push({ latex: stripLatexDelimiters(merged.slice(indices[0] + 1, indices[1]).trim()), display: false })
  return (
    merged.slice(0, indices[0]) +
    `${MATH_SLOT_OPEN}${id}${MATH_SLOT_CLOSE}` +
    merged.slice(indices[1] + 1)
  )
}

export function protectMathDelimiters(text: string, slots: MathSlot[] = []): { text: string; slots: MathSlot[] } {
  let out = text

  out = out.replace(/\$\$\s*([\s\S]+?)\s*\$\$/g, (match, body: string) => {
    if (body.includes(MATH_SLOT_OPEN)) return match
    const id = slots.length
    slots.push({ latex: stripLatexDelimiters(body.trim()), display: true })
    return `${MATH_SLOT_OPEN}${id}${MATH_SLOT_CLOSE}`
  })

  out = out
    .split('\n')
    .map(line => protectInlineMathLine(line, slots))
    .join('\n')

  return { text: out, slots }
}

export function restoreMathSlots(text: string, slots: MathSlot[]): string {
  return text.replace(
    new RegExp(`${MATH_SLOT_OPEN}(\\d+)${MATH_SLOT_CLOSE}`, 'g'),
    (_m, id: string) => {
      const slot = slots[Number(id)]
      if (!slot) return _m
      return slot.display ? `$$${slot.latex}$$` : `$${slot.latex}$`
    },
  )
}

/** 去掉 KaTeX 不需要的外层定界符（$、$$、\\(\\)、\\[\\]），递归剥离多层嵌套 */
export function stripLatexDelimiters(latex: string): string {
  let t = latex.trim()
  let prev = ''
  while (t !== prev) {
    prev = t
    const paren = /^\\\(\s*([\s\S]*?)\s*\\\)$/.exec(t)
    if (paren) {
      t = paren[1].trim()
      continue
    }
    const bracket = /^\\\[\s*([\s\S]*?)\s*\\\]$/.exec(t)
    if (bracket) {
      t = bracket[1].trim()
      continue
    }
    if (t.startsWith('$$') && t.endsWith('$$') && t.length > 4) {
      t = t.slice(2, -2).trim()
      continue
    }
    if (t.startsWith('$') && t.endsWith('$') && t.length > 2) {
      t = t.slice(1, -1).trim()
      continue
    }
  }
  return t
}

/** LLM 输出的 \\(\\) / \\[\\] 统一转为 $ / $$（须在 bold 包裹与 protect 之前） */
export function convertLatexDelimitersToDollar(text: string): string {
  let out = text
  out = out.replace(/\\\[\s*([\s\S]+?)\s*\\\]/g, (_m, inner: string) => `$$${inner.trim()}$$`)
  out = out.replace(/\\\(\s*([\s\S]+?)\s*\\\)/g, (_m, inner: string) => `$${inner.trim()}$`)
  return out
}

/** OCR / RapidLaTeXOCR 常见粘连：\\simD → \\sim D，否则 KaTeX 报红 */
const OCR_GLUE_COMMANDS =
  'sim|simeq|cong|approx|equiv|propto|in|notin|ni|subset|supset|subseteq|supseteq|to|mapsto|gets|leftrightarrow|Leftrightarrow|rightarrow|leftarrow|Rightarrow|Leftarrow|cdot|times|circ|bullet|pm|mp|cap|cup|vee|wedge|leq|geq|neq|le|ge|lt|gt|mid|parallel|perp|models|vdash|dashv'

export function fixOcrLatexGlue(latex: string): string {
  let text = latex
  // 分布符号 ~ 在数学模式里应写作 \sim，裸 ~ 会被 KaTeX 当成空白
  text = text.replace(/([)\}_\w])\s*~\s*(?=\\|[A-Za-z{])/g, '$1 \\sim ')
  text = text.replace(new RegExp(`\\\\(?:${OCR_GLUE_COMMANDS})(?=[A-Za-z\\\\])`, 'g'), (match) => `${match} `)
  return text
}

/** OCR 公式：仅做粘连/笔误修复，不做 MinerU 式空格压缩（会破坏嵌套下标） */
export function normalizeOcrLatex(latex: string): string {
  return fixOcrLatexGlue(
    fixLlmLatexSyntax(restoreMathPipePlaceholders(stripLatexDelimiters(latex.trim()))),
  )
}

function compactScriptBody(body: string): string {
  return fixOcrLatexGlue(body.replace(/\s+/g, ''))
}

/** 按花括号深度匹配 _{…} / ^{…}，避免 D_{gen} 内的 } 截断外层下标 */
function compactBalancedScripts(text: string, marker: '_' | '^'): string {
  let result = ''
  let i = 0
  while (i < text.length) {
    if (text[i] === marker && text[i + 1] === '{') {
      let depth = 1
      let j = i + 2
      while (j < text.length && depth > 0) {
        if (text[j] === '{') depth += 1
        else if (text[j] === '}') depth -= 1
        j += 1
      }
      const body = text.slice(i + 2, j - 1)
      result += `${marker}{${compactScriptBody(body)}}`
      i = j
      continue
    }
    result += text[i]
    i += 1
  }
  return result
}

/** LLM 输出的常见 LaTeX 笔误 */
export function fixLlmLatexSyntax(latex: string): string {
  let text = latex.trim()
  text = text.replace(/\\left\s*\\text/g, '\\left( \\text')
  text = text.replace(/\\left\s*\(\s*/g, '\\left(')
  text = text.replace(/\\right\s*\)/g, '\\right)')
  text = text.replace(/\\right\s*\$/g, '\\right)')
  text = text.replace(/\\right\s*(?=[.;,\s]*$)/g, '\\right)')
  text = text.replace(/\\text\{([^}]*)\}\(/g, '\\text{$1}(')
  // \text{Concat} I_{den} → \text{Concat}(I_{den}
  text = text.replace(/\\text\{([^}]+)\}\s+([A-Za-z_\\][A-Za-z0-9_{}\\]*)/g, '\\text{$1}($2')
  return text
}

/** 将 MinerU / LLM 松散 LaTeX 收紧为 KaTeX 可正确排版的形式 */
export function normalizeLatexForKatex(latex: string): string {
  let text = fixOcrLatexGlue(fixLlmLatexSyntax(restoreMathPipePlaceholders(stripLatexDelimiters(latex.trim()))))
  if (!text) return text

  text = text.replace(/\\tag\s*\{([^}]*)\}/g, '\\quad\\text{($1)}')
  text = text.replace(/\\quad\\text\{\(([^}]*)\)\}/g, '\\quad\\text{($1)}')

  text = text.replace(
    /\\begin\s*\{\s*array\s*\}\s*\{\s*([^}]*?)\s*\}\s*\{\s*([\s\S]*?)\s*\}\s*\\end\s*\{\s*array\s*\}/g,
    (_m, cols: string, body: string) => {
      const col = cols.replace(/\s+/g, '')
      return col === 'r' || col === 'l' || col === 'c' ? body.trim() : _m
    },
  )
  text = text.replace(
    /\\begin\s*\{\s*array\s*\}\s*\{\s*([^}]*?)\s*\}\s*\{\s*/g,
    (_m, cols: string) => `\\begin{array}{${cols.replace(/\s+/g, '')}} `,
  )
  text = text.replace(/\}\s*\\end\s*\{\s*array\s*\}/g, ' \\end{array}')

  text = text.replace(
    /\\(mathit|mathrm|mathbf|mathcal|mathbb|mathfrak|mathsf|mathtt)\s*\{\s*([^}]+?)\s*\}/g,
    (_m, cmd: string, body: string) => `\\${cmd}{${body.replace(/\s+/g, '')}}`,
  )

  text = text.replace(
    /\\operatorname\s*\*\s*\{\s*([^}]+?)\s*\}/g,
    (_m, body: string) => `\\operatorname*{${body.replace(/\s+/g, '')}}`,
  )
  text = text.replace(
    /\\operatorname\s*\{\s*([^}]+?)\s*\}/g,
    (_m, body: string) => `\\operatorname{${body.replace(/\s+/g, '')}}`,
  )

  text = text.replace(
    /\\frac\s*\{\s*([^}]+?)\s*\}\s*\{\s*([^}]+?)\s*\}/g,
    (_m, num: string, den: string) =>
      `\\frac{${compactFracPart(num)}}{${compactFracPart(den)}}`,
  )

  text = compactBalancedScripts(text, '_')
  text = compactBalancedScripts(text, '^')

  // \mathcal { R } _ { i j } → \mathcal{R}_{ij}
  text = text.replace(/\\([a-zA-Z]+)\s*\{\s*([^}]+?)\s*\}/g, (_m, cmd: string, body: string) => {
    if (['frac', 'begin', 'end', 'text', 'tag'].includes(cmd)) return _m
    return `\\${cmd}{${body.replace(/\s+/g, '')}}`
  })

  text = text.replace(/\{\s+/g, '{')
  text = text.replace(/\s+\}/g, '}')
  text = text.replace(/\|\s+/g, '|')
  text = text.replace(/\s+\|/g, '|')
  text = text.replace(/\s+/g, ' ')

  return text.trim()
}

function compactFracPart(part: string): string {
  // 含 LaTeX 命令时分母/分子保留空格，避免 M \times N → M\timesN 破坏命令
  if (/\\[a-zA-Z]+/.test(part)) {
    return part
      .replace(/\|\s+/g, '|')
      .replace(/\s+\|/g, '|')
      .replace(/\s+/g, ' ')
      .trim()
  }
  return part
    .replace(/\|\s+/g, '|')
    .replace(/\s+\|/g, '|')
    .replace(/\s*\+\s*/g, '+')
    .replace(/\s*-\s*/g, '-')
    .replace(/\s+/g, '')
    .trim()
}

/** 含中文说明或行内 $...$ 的「伪公式块」应作为段落渲染 */
export function isMixedFormulaBlock(text: string): boolean {
  const inner = text.replace(/^\$\$|\$\$$/g, '').trim()
  return /\$[^$]+\$/.test(inner) || /[\u4e00-\u9fff]/.test(inner)
}

export function renderKatexHtml(
  content: string,
  displayMode: boolean,
  opts?: { source?: 'ocr' | 'default' },
): string {
  const normalized =
    opts?.source === 'ocr' ? normalizeOcrLatex(content) : normalizeLatexForKatex(content)
  try {
    return katex.renderToString(normalized, {
      displayMode,
      throwOnError: false,
      strict: 'ignore',
    })
  } catch {
    return normalized
  }
}

export function katexRenderedCleanly(html: string): boolean {
  return html.includes('class="katex"') && !html.includes('katex-error')
}

/** 仅将简单括号内容转为行内公式，避免拆散 \left(...\right) 等复杂表达式 */
export function shouldWrapParenAsMath(inner: string): boolean {
  if (!looksLikeInlineLatex(inner)) return false
  const t = inner.trim()
  if (/[,;=]/.test(t)) return false
  if (/\\left|\\right|\\text|\\frac|\\sum|\\int|\\cdot|\\times/.test(t)) return false
  if (/\([^)]*\)/.test(t)) return false
  // F_{den}(I_{noisy}) 中的 (I_{noisy}) 是函数实参，不是独立公式
  if (/^[A-Za-z](?:_\{[^{}]+\}|\^\{[^{}]+\})+$/.test(t.replace(/\s+/g, ''))) return false
  return /^[A-Za-z\\][A-Za-z0-9\\]*(?:_\{[^{}]+\}|\^\{[^{}]+\})?$/.test(t.replace(/\s+/g, ''))
}

/** 合并被误拆的多段 $...$（如 Concat$I_{den}, E$; \theta） */
export function mergeFragmentedInlineMath(text: string): string {
  let out = text
  let prev = ''
  while (out !== prev) {
    prev = out
    // $a$ mid $b$ → 单段（mid 为逗号/分号/空格/标识符）
    out = out.replace(/\$([^$\n]+)\$([^$\n]+?)\$([^$\n]+)\$/g, (match, a, mid, b) => {
      if (!/^[A-Za-z_{\\}\s,;().+\-^=\\]+$/.test(mid)) return match
      const merged = `${a}${mid}${b}`
      if (/\\left|\\right|_\{|\\text|\\frac|=/.test(merged)) return `$${merged}$`
      return match
    })
    // $a$$b$ 紧邻
    out = out.replace(/\$([^$\n]+)\$\$([^$\n]+)\$/g, (match, a, b) => {
      const merged = `${a}${b}`
      if (/\\left|\\right|_\{|\\text|\\frac|=/.test(merged)) return `$${merged}$`
      return match
    })
  }
  return out
}

/** **粗体** 内的裸 LaTeX（无 $）会被 markdown-it 的 _ 语法拆碎，先包 $ */
function looksLikeBoldLatexContent(inner: string): boolean {
  const t = inner.trim()
  if (!t || /[\u4e00-\u9fff]/.test(t)) return false
  if (/^\$.*\$$/.test(t)) return false
  return (
    looksLikeInlineLatex(t) ||
    /_\{[^{}]+\}/.test(t) ||
    /\\[a-zA-Z]+/.test(t) ||
    (/[A-Za-z]/.test(t) && /[=_{}\\]/.test(t))
  )
}

export function wrapMarkdownBoldLatex(text: string): string {
  return text.replace(/\*\*([^*\n]+?)\*\*/g, (match, inner: string) => {
    const stripped = stripLatexDelimiters(mergeFragmentedInlineMath(inner.trim()))
    if (!looksLikeBoldLatexContent(stripped) && !/^\$.*\$$/.test(stripped)) return match
    const body = stripped
    if (body.startsWith('$') && body.endsWith('$')) return `**${body}**`
    return `**$${body}$**`
  })
}

/** 列表项「公式标签：说明」形如 `- I_{den}=...：首先` */
export function wrapListLabelLatex(text: string): string {
  return text.replace(/^(\s*[-*•]\s+)([^\n]+)$/gm, (match, prefix, body) => {
    if (body.includes('**') || body.includes(MATH_SLOT_OPEN)) return match
    const colon = body.search(/[：:]\s*[\u4e00-\u9fff]/)
    if (colon <= 0) return match
    const label = body.slice(0, colon).trim()
    const tail = body.slice(colon)
    if (!looksLikeBoldLatexContent(label)) return match
    if (label.startsWith('$') && label.endsWith('$')) return match
    return `${prefix}$${label}$${tail}`
  })
}

/** LLM 常用 ( ... ) / [ ... ] 包裹的 LaTeX，转为 $ / $$ 定界符 */
export function looksLikeInlineLatex(inner: string): boolean {
  const t = inner.trim()
  if (!t || t.length > 800) return false
  if (/[\u4e00-\u9fff，。；：、]/.test(t) && !/(?:\\[a-zA-Z]+|[_^{}])/.test(t)) return false
  return (
    /(?:\\[a-zA-Z]+|[_^]|\\left|\\right|\\text|\\frac|\\cdot|\\theta|\\alpha|\\beta)/.test(t) ||
    /[A-Za-z]\s*_\s*\{/.test(t) ||
    /\\left\s*\(/.test(t)
  )
}

export function normalizeLlmMathDelimiters(text: string): string {
  const { text: protectedText, slots } = protectMathDelimiters(text)
  let out = protectedText

  // 标准 LaTeX 定界符 \(...\) / \[...\]（占位符外的文本）
  out = out.replace(/\\\(\s*([\s\S]+?)\s*\\\)/g, (_m, inner: string) => `$${inner.trim()}$`)
  out = out.replace(/\\\[\s*([\s\S]+?)\s*\\\]/g, (_m, inner: string) => `$$\n${inner.trim()}\n$$`)

  // 独立成段的 [ \n formula \n ]（排除引用角标 [1]）
  out = out.replace(/(^|\n)\[\s*\n([\s\S]+?)\n\s*\](\n|$)/g, (match, before, inner, after) => {
    const body = inner.trim()
    if (!body || /^\d{1,2}$/.test(body)) return match
    if (!looksLikeInlineLatex(body) && !looksLikeBareLatex(body)) return match
    return `${before}$$\n${body}\n$$${after}`
  })

  // 单行 [ formula ]
  out = out.replace(/(^|\n)\[\s*([^\]\n]+?)\s*\](\n|$)/g, (match, before, inner, after) => {
    const body = inner.trim()
    if (/^\d{1,2}$/.test(body)) return match
    if (!looksLikeInlineLatex(body) && !looksLikeBareLatex(body)) return match
    return `${before}$$\n${body}\n$$${after}`
  })

  // 行内 ( formula )：仅转换简单符号，不拆散复杂表达式（$...$ 已被 protect 占位）
  out = out.replace(/(?<!\\left)\(\s*([^()]*(?:\([^()]*\)[^()]*)*?)\s*\)/g, (match, inner: string) => {
    if (inner.includes(MATH_SLOT_OPEN)) return match
    if (!shouldWrapParenAsMath(inner)) return match
    return `$${inner.trim()}$`
  })

  out = mergeFragmentedInlineMath(out)
  out = unwrapMixedDisplayMathBlocks(out)
  return restoreMathSlots(out, slots)
}

/** 解除误包裹的 $$ 块（内含中文标题/列表时） */
export function unwrapMixedDisplayMathBlocks(text: string): string {
  return text.replace(/\$\$\s*([\s\S]+?)\s*\$\$/g, (match, body: string) => {
    if (!/[\u4e00-\u9fff]/.test(body)) return match
    const lines = body.split('\n')
    const proseLines = lines.filter(
      l => /[\u4e00-\u9fff]/.test(l) && !looksLikeInlineLatex(l) && !looksLikeBareLatex(l.trim()),
    )
    if (!proseLines.length) return match
    return lines
      .map(line => {
        const t = line.trim()
        const pureLatex =
          (looksLikeInlineLatex(t) || looksLikeBareLatex(t)) &&
          !/[\u4e00-\u9fff]/.test(t) &&
          !/^[-*•]\s/.test(t) &&
          !/\*\*/.test(t)
        if (pureLatex) return `\n$$${t}$$\n`
        return line
      })
      .join('\n')
  })
}

export function renderMathSlotsInHtml(html: string, slots: MathSlot[]): string {
  const slotRe = new RegExp(`${MATH_SLOT_OPEN}(\\d+)${MATH_SLOT_CLOSE}`, 'g')
  html = html.replace(slotRe, (_m, id: string) => {
    const slot = slots[Number(id)]
    if (!slot) return _m
    const rendered = renderKatexHtml(slot.latex, slot.display)
    if (!rendered.includes('class="katex"')) {
      return slot.display ? `$$${slot.latex}$$` : `$${slot.latex}$`
    }
    return slot.display
      ? `<div class="formula-display">${rendered}</div>`
      : `<span class="math-inline">${rendered}</span>`
  })
  // 不再二次扫描 $，避免已渲染公式被拆碎
  return html
}

/**
 * 必须在 Markdown 表格解析完成后再做，否则单元格内的 | 会破坏表格。
 */
export function renderMathInMarkdownHtml(html: string): string {
  // 块级公式（md 渲染后常在 <p> 内）
  html = html.replace(/<p>\s*\$\$\s*([\s\S]+?)\s*\$\$\s*<\/p>/g, (_match, latex: string) => {
    const rendered = renderKatexHtml(latex.trim(), true)
    return rendered.includes('class="katex"')
      ? `<div class="formula-display">${rendered}</div>`
      : `<p>$$${latex}$$</p>`
  })

  // md 未转换的 \(...\) / \[...\] 字面量（常见于 LLM 输出）
  html = html.replace(/\\\(\s*([\s\S]+?)\s*\\\)/g, (match, latex: string, offset: number) => {
    const before = html.slice(Math.max(0, offset - 80), offset)
    if (/class="(?:katex|math-inline|formula-display)/.test(before)) return match
    const rendered = renderKatexHtml(latex.trim(), false)
    return rendered.includes('class="katex"')
      ? `<span class="math-inline math-inline--cell">${rendered}</span>`
      : match
  })

  return html.replace(/\$([^$\n]+?)\$/g, (match, latex: string, offset: number) => {
    const before = html.slice(Math.max(0, offset - 120), offset)
    if (/class="(?:katex|math-inline|formula-display)/.test(before) && !before.includes('</span>')) {
      return match
    }
    const normalized = normalizeLatexForKatex(latex.trim())
    if (!normalized) return match
    try {
      const rendered = katex.renderToString(normalized, {
        displayMode: false,
        throwOnError: false,
        strict: 'ignore',
      })
      return `<span class="math-inline math-inline--cell">${rendered}</span>`
    } catch {
      return match
    }
  })
}

/** 将 ![图题](url) 转为 ![](url)\n图题，使图题在页面上可见（alt 文本默认不显示） */
export function normalizeFigureCaptionMarkdown(text: string): string {
  const trimmed = text.trim()
  if (!trimmed.startsWith('![')) return text

  const lines = trimmed.split('\n')
  const first = lines[0]?.match(/^!\[([^\]]*)\]\(([^)]+)\)\s*$/)
  if (!first) return text

  const alt = first[1]?.trim() || ''
  const url = first[2]?.trim() || ''
  if (!url) return text

  const tail = lines.slice(1).filter(line => line.trim())
  if (!alt && tail.length) return text

  const visibleCaption = [alt, ...tail].filter(Boolean).join('\n')
  return visibleCaption ? `![](${url})\n${visibleCaption}` : `![](${url})`
}

/** 段落 / 表格 Markdown：保护公式后再做定界符处理（KaTeX 在 md.render 之后注入） */
export function prepareMarkdownForRender(text: string): string {
  let source = escapePipesInMathForMarkdown(text)
  const { text: protectedText, slots } = protectMathDelimiters(source)
  let prepared = normalizeFigureCaptionMarkdown(protectedText)
  prepared = fixBrokenInlineDelimiters(prepared)
  prepared = tightenMathDelimiters(preprocessMarkdownMath(prepared))
  return restoreMathSlots(prepared, slots)
}

export function preprocessMarkdownMath(text: string): string {
  return text.replace(/\\tag\s*\{([^}]*)\}/g, '\\quad\\text{($1)}')
}

/** 聊天 Markdown：保护已有公式 → 转换 LLM 定界符 → 标准预处理 */
export function prepareChatMarkdownForRender(text: string): string {
  let source = unwrapMixedDisplayMathBlocks(text)
  source = convertLatexDelimitersToDollar(source)
  source = wrapMarkdownBoldLatex(source)
  source = wrapListLabelLatex(source)
  source = mergeFragmentedInlineMath(source)
  const first = protectMathDelimiters(source)
  let t = normalizeLlmMathDelimiters(first.text)
  t = restoreMathSlots(t, first.slots)
  return prepareMarkdownForRender(t)
}

export function renderChatMarkdownHtml(raw: string, mdRender: (s: string) => string): string {
  const prepared = mergeFragmentedInlineMath(prepareChatMarkdownForRender(raw))
  const { text: mdInput, slots } = protectMathDelimiters(prepared)
  let html = mdRender(mdInput)
  html = renderMathSlotsInHtml(html, slots)
  // 兜底：占位符未覆盖的残留公式
  return renderMathInMarkdownHtml(html)
}

export function renderBareLatexBlock(text: string): string {
  const html = renderKatexHtml(text, true)
  return html.includes('class="katex"')
    ? `<div class="formula-display">${html}</div>`
    : `<pre class="formula-block">${text}</pre>`
}
