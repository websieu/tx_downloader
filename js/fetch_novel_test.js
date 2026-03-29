async ({ args }) => {
  // TEST VERSION - Max 2 chapters only
  const MAX_TEST_CHAPTERS = 2;
  
  const startFromChapter = args && args.startChapter ? args.startChapter : 1;
  const existingText = args && args.existingText ? args.existingText : "";
  
  console.log('=== TEST MODE: Max ' + MAX_TEST_CHAPTERS + ' chapters ===');
  console.log('Starting from chapter:', startFromChapter);
  console.log('Existing text length:', existingText.length);

  const firstLink = document.querySelector('.chaplist ul li a');
  const href = firstLink ? firstLink.getAttribute('href') : null; 
  console.log('First href:', href);

  function extractChapterNumber(path) {
    if (typeof path !== 'string') return null;
    const m = path.match(/_(\d+)\.html(?:\?.*)?$/i);
    return m ? parseInt(m[1], 10) : null;
  }

  const realChapterNumber = extractChapterNumber(href);
  const chapterNumber = Math.min(realChapterNumber, MAX_TEST_CHAPTERS);
  console.log('Real max chapter:', realChapterNumber, '| Testing with:', chapterNumber);

  if (!href || !chapterNumber) {
    console.error('Không lấy được href hoặc chapterNumber');
    return null;
  }

  function extractBookInfo(path) {
    const parts = path.split('/').filter(Boolean);
    const bookId = parts[0];
    const fileName = parts[1];
    const prefixMatch = fileName.match(/^(\d+)_\d+\.html$/);
    const chapterPrefix = prefixMatch ? prefixMatch[1] : null;
    return { bookId, chapterPrefix };
  }

  const { bookId, chapterPrefix } = extractBookInfo(href);
  console.log('bookId:', bookId, 'chapterPrefix:', chapterPrefix);

  if (!bookId || !chapterPrefix) {
    console.error('Không phân tích được bookId/chapterPrefix từ href');
    return null;
  }

  const BASE_URL = 'https://www.novel543.com';
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function buildChapterUrl(chapter, part) {
    const partSuffix = part === 1 ? '' : '_2';
    return BASE_URL + "/" + bookId + "/" + chapterPrefix + "_" + chapter + partSuffix + ".html";
  }

  function extractChapterTextFromHtmlKeepLine(html, extractTitle = false) {
    try {
      var parser = new DOMParser();
      var doc = parser.parseFromString(html, "text/html");
      var contentDiv = doc.querySelector("div.chapter-content.px-3");
      if (!contentDiv) {
        console.warn("Không tìm thấy div.chapter-content.px-3");
        return { title: "", text: "" };
      }

      var title = "";
      if (extractTitle) {
        var h1 = contentDiv.querySelector("h1");
        if (h1) {
          title = h1.textContent.trim();
          title = title
            .replace(/\s*\(\s*\d+\s*\/\s*\d+\s*\)\s*$/g, '')
            .replace(/\s*（\s*\d+\s*\/\s*\d+\s*）\s*$/g, '')
            .trim();
          console.log("  Chapter title: " + title);
          h1.remove();
        }
      } else {
        var h1 = contentDiv.querySelector("h1");
        if (h1) {
          h1.remove();
        }
      }

      var scripts = contentDiv.querySelectorAll("script, style");
      scripts.forEach(function (el) { el.remove(); });

      var htmlStr = contentDiv.innerHTML;
      htmlStr = htmlStr.replace(/<br\s*\/?>/gi, "\n");
      htmlStr = htmlStr.replace(/<\/p>\s*<p[^>]*>/gi, "\n\n");
      htmlStr = htmlStr.replace(/<p[^>]*>/gi, "");
      htmlStr = htmlStr.replace(/<\/p>/gi, "");
      htmlStr = htmlStr.replace(/<[^>]+>/g, "");
      htmlStr = htmlStr.replace(/\r\n/g, "\n");
      htmlStr = htmlStr.replace(/\n[ \t]+/g, "\n");
      htmlStr = htmlStr.replace(/[ \t]+\n/g, "\n");
      htmlStr = htmlStr.replace(/\n{3,}/g, "\n\n");
      htmlStr = htmlStr.replace(/\(1\/2\)/g, "");
      htmlStr = htmlStr.replace(/\(2\/2\)/g, "");
      htmlStr = htmlStr.replace(/（1\/2）/g, "");
      htmlStr = htmlStr.replace(/（2\/2）/g, "");

      var text = htmlStr.trim();
      
      if (title && text) {
        var titlePattern = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        var duplicateTitleRegex = new RegExp('^' + titlePattern + '\\s*(?:\\(?\\d+\\/\\d+\\)?)?\\s*(?:（\\d+\\/\\d+）)?\\s*\\n*', 'i');
        text = text.replace(duplicateTitleRegex, '').trim();
      }

      return { title: title, text: text };
    } catch (e) {
      console.error("Lỗi parse HTML:", e);
      return { title: "", text: "" };
    }
  }

  async function fetchChapterPart(chapter, part) {
    const url = buildChapterUrl(chapter, part);
    const maxRetries = 1; // Giảm retry cho test
    let attempt = 0;
    const extractTitle = (part === 1);

    while (attempt <= maxRetries) {
      attempt++;
      console.log("Fetching chapter " + chapter + ", part " + part + " (attempt " + attempt + "):", url);

      try {
        const res = await fetch(url, { credentials: 'same-origin' });
        if (!res.ok) {
          throw new Error("HTTP " + res.status + " khi fetch " + url);
        }
        const html = await res.text();
        const result = extractChapterTextFromHtmlKeepLine(html, extractTitle);
        
        console.log("=== CHAPTER " + chapter + " PART " + part + " ===");
        console.log("Title: [" + result.title + "]");
        console.log("Text length: " + result.text.length);
        console.log("Text preview (first 500 chars):");
        console.log("---START---");
        console.log(result.text.slice(0, 500));
        console.log("---END---");
        
        return { chapter, part, url, text: result.text, title: result.title };
      } catch (err) {
        console.error("Lỗi fetch chapter " + chapter + ", part " + part + ":", err);
        if (attempt > maxRetries) {
          throw new Error("Failed to fetch chapter " + chapter + ", part " + part);
        }
        await sleep(5000);
      }
    }
  }

  async function fetchAllChapters(maxChapter, startChapter = 1) {
    const collected = [];
    let currentChapter = startChapter;

    try {
      for (let ch = startChapter; ch <= maxChapter; ch++) {
        currentChapter = ch;
        console.log("\n========== FETCHING CHAPTER " + ch + " ==========");
        
        const part1 = await fetchChapterPart(ch, 1);
        const part2 = await fetchChapterPart(ch, 2);

        collected.push(part1, part2);
        
        console.log("\n--- Collected so far ---");
        collected.forEach(item => {
          console.log("Ch" + item.chapter + " Part" + item.part + ": " + item.text.length + " chars, title: [" + item.title + "]");
        });

        await sleep(2000);
      }

      collected.sort((a, b) => {
        if (a.chapter === b.chapter) return a.part - b.part;
        return a.chapter - b.chapter;
      });

      const chapterTexts = [];
      for (let ch = startChapter; ch <= maxChapter; ch++) {
        const chapterParts = collected.filter(item => item.chapter === ch);
        if (chapterParts.length === 0) continue;
        
        const part1 = chapterParts.find(p => p.part === 1);
        const title = part1 ? part1.title : "";
        
        // DEBUG: Show what we're combining
        console.log("\n=== COMBINING CHAPTER " + ch + " ===");
        console.log("Title from part1: [" + title + "]");
        chapterParts.forEach(p => {
          console.log("Part " + p.part + " text (first 200): " + p.text.slice(0, 200));
        });
        
        const contentText = chapterParts.map(item => item.text).join("\n");
        const fullChapter = title ? `${title}\n${contentText}` : contentText;
        chapterTexts.push(fullChapter);
        
        console.log("Combined chapter " + ch + " length: " + fullChapter.length);
      }
      
      const fullText = chapterTexts.join("\n\n");

      console.log('\n=== FINAL FULL TEXT ===');
      console.log('Total length:', fullText.length);
      console.log('\n--- FULL TEXT CONTENT ---');
      console.log(fullText);
      console.log('--- END FULL TEXT ---');

      return {
        status: "success",
        text: fullText,
        currentChapter: maxChapter,
        totalChapters: maxChapter
      };
    } catch (error) {
      console.error("Error occurred:", error);
      
      collected.sort((a, b) => {
        if (a.chapter === b.chapter) return a.part - b.part;
        return a.chapter - b.chapter;
      });

      const chapterTexts = [];
      const uniqueChapters = [...new Set(collected.map(item => item.chapter))];
      for (const ch of uniqueChapters) {
        const chapterParts = collected.filter(item => item.chapter === ch);
        if (chapterParts.length === 0) continue;
        
        const part1 = chapterParts.find(p => p.part === 1);
        const title = part1 ? part1.title : "";
        const contentText = chapterParts.map(item => item.text).join("\n");
        const fullChapter = title ? `${title}\n${contentText}` : contentText;
        chapterTexts.push(fullChapter);
      }
      
      const partialText = chapterTexts.join("\n\n");

      return {
        status: "error",
        text: partialText,
        currentChapter: currentChapter - 1,
        totalChapters: maxChapter,
        error: error.message
      };
    }
  }

  let finalText = existingText;
  const result = await fetchAllChapters(chapterNumber, startFromChapter);
  
  if (existingText && result.text) {
    finalText = existingText + "\n\n" + result.text;
  } else if (result.text) {
    finalText = result.text;
  }

  return {
    status: result.status,
    text: finalText,
    currentChapter: result.currentChapter,
    totalChapters: result.totalChapters,
    error: result.error || null
  };
}
