async ({ args }) => {
  // TEST VERSION - Simulates exceptions to test retry logic
  const startFromChapter = args && args.startChapter ? args.startChapter : 1;
  const existingText = args && args.existingText ? args.existingText : "";
  const retryAttempt = args && args.retryAttempt ? args.retryAttempt : 0;
  
  // Error points - each triggers ONCE based on startFromChapter
  // Nếu startFromChapter > error point thì không trigger nữa
  const errorPoints = [
    { chapter: 11, part: 2 },
    { chapter: 22, part: 1 },
    { chapter: 30, part: 2 }
  ];
  
  // Track which errors have been triggered in THIS run
  const triggeredErrors = new Set();
  
  console.log('=== EXCEPTION TEST MODE ===');
  console.log('Starting from chapter:', startFromChapter);
  console.log('Existing text length:', existingText.length);
  console.log('Retry attempt:', retryAttempt);
  console.log('Will simulate errors at: Ch11-P2, Ch22-P1, Ch30-P2');

  const firstLink = document.querySelector('.chaplist ul li a');
  const href = firstLink ? firstLink.getAttribute('href') : null; 
  console.log('First href:', href);

  function extractChapterNumber(path) {
    if (typeof path !== 'string') return null;
    const m = path.match(/_(\d+)\.html(?:\?.*)?$/i);
    return m ? parseInt(m[1], 10) : null;
  }

  const chapterNumber = extractChapterNumber(href);
  console.log('Max chapterNumber:', chapterNumber);

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

  // Check if we should simulate an error for this chapter/part
  function shouldSimulateError(chapter, part) {
    const key = `ch${chapter}_p${part}`;
    
    // Nếu đã trigger error này trong run hiện tại, không trigger lại
    if (triggeredErrors.has(key)) {
      return false;
    }
    
    // Tìm xem có error point nào match không
    for (const ep of errorPoints) {
      if (ep.chapter === chapter && ep.part === part) {
        // Chỉ trigger nếu startFromChapter < chapter này (STRICTLY LESS THAN)
        // Nếu startFromChapter == chapter, nghĩa là đang retry từ chapter này → skip error
        if (startFromChapter < chapter) {
          triggeredErrors.add(key);
          console.log(`🎯 Error point matched: Ch${chapter} P${part}, startFrom=${startFromChapter}`);
          return true;
        } else {
          console.log(`⏭️ Skipping error at Ch${chapter} P${part} (startFrom=${startFromChapter} >= ${chapter}, already retrying)`);
        }
      }
    }
    
    return false;
  }

  async function fetchChapterPart(chapter, part) {
    const url = buildChapterUrl(chapter, part);
    const maxRetries = 1; // Reduced for test
    let attempt = 0;
    const extractTitle = (part === 1);

    while (attempt <= maxRetries) {
      attempt++;
      console.log("Fetching chapter " + chapter + ", part " + part + " (attempt " + attempt + "):", url);

      // SIMULATE ERROR
      if (shouldSimulateError(chapter, part)) {
        console.error("🔴 SIMULATED ERROR at chapter " + chapter + ", part " + part);
        throw new Error("SIMULATED: Network error at chapter " + chapter + ", part " + part);
      }

      try {
        const res = await fetch(url, { credentials: 'same-origin' });
        if (!res.ok) {
          throw new Error("HTTP " + res.status + " khi fetch " + url);
        }
        const html = await res.text();
        const result = extractChapterTextFromHtmlKeepLine(html, extractTitle);
        
        console.log("✅ Ch" + chapter + " P" + part + ": " + result.text.length + " chars");
        
        return { chapter, part, url, text: result.text, title: result.title };
      } catch (err) {
        console.error("Lỗi fetch chapter " + chapter + ", part " + part + ":", err);
        if (attempt > maxRetries) {
          throw new Error("Failed to fetch chapter " + chapter + ", part " + part);
        }
        await sleep(2000);
      }
    }
  }

  async function fetchAllChapters(maxChapter, startChapter = 1) {
    const collected = [];
    let lastCompletedChapter = startChapter - 1;

    try {
      for (let ch = startChapter; ch <= maxChapter; ch++) {
        console.log("\n========== CHAPTER " + ch + "/" + maxChapter + " ==========");
        
        const part1 = await fetchChapterPart(ch, 1);
        const part2 = await fetchChapterPart(ch, 2);

        collected.push(part1, part2);
        lastCompletedChapter = ch;

        // Reduced sleep for test
        if (ch % 6 === 0 && ch < maxChapter) {
          console.log("Nghỉ 2s...");
          await sleep(2000);
        }
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
        const contentText = chapterParts.map(item => item.text).join("\n");
        const fullChapter = title ? `${title}\n${contentText}` : contentText;
        chapterTexts.push(fullChapter);
      }
      
      const fullText = chapterTexts.join("\n\n");

      console.log('\n=== SUCCESS ===');
      console.log('Total chapters:', maxChapter - startChapter + 1);
      console.log('Total length:', fullText.length);

      return {
        status: "success",
        text: fullText,
        currentChapter: maxChapter,
        totalChapters: maxChapter
      };
    } catch (error) {
      console.error("\n🔴 ERROR occurred:", error.message);
      console.log("Last completed chapter:", lastCompletedChapter);
      
      const completedChapters = collected.filter(item => item.chapter <= lastCompletedChapter);
      
      completedChapters.sort((a, b) => {
        if (a.chapter === b.chapter) return a.part - b.part;
        return a.chapter - b.chapter;
      });

      const chapterTexts = [];
      const uniqueChapters = [...new Set(completedChapters.map(item => item.chapter))];
      for (const ch of uniqueChapters) {
        const chapterParts = completedChapters.filter(item => item.chapter === ch);
        if (chapterParts.length < 2) continue;
        
        const part1 = chapterParts.find(p => p.part === 1);
        const title = part1 ? part1.title : "";
        const contentText = chapterParts.map(item => item.text).join("\n");
        const fullChapter = title ? `${title}\n${contentText}` : contentText;
        chapterTexts.push(fullChapter);
      }
      
      const partialText = chapterTexts.join("\n\n");

      console.log("Partial text from chapters", startChapter, "to", lastCompletedChapter);
      console.log("Partial text length:", partialText.length);

      return {
        status: "error",
        text: partialText,
        currentChapter: lastCompletedChapter,
        totalChapters: maxChapter,
        error: error.message
      };
    }
  }

  const result = await fetchAllChapters(chapterNumber, startFromChapter);

  return {
    status: result.status,
    text: result.text,
    currentChapter: result.currentChapter,
    totalChapters: result.totalChapters,
    error: result.error || null
  };
}
