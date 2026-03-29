async ({ args }) => {
  // Get starting chapter from args (if retry), default to 1
  const startFromChapter = args && args.startChapter ? args.startChapter : 1;
  const existingText = args && args.existingText ? args.existingText : "";
  
  console.log('Starting from chapter:', startFromChapter);
  console.log('Existing text length:', existingText.length);

  /* ---------- 1) Lấy link đầu tiên để suy ra bookId + prefix + số chương ---------- */

  const firstLink = document.querySelector('.chaplist ul li a');
  const href = firstLink ? firstLink.getAttribute('href') : null; 
  // ví dụ href: "/0924648104/8096_583.html"
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
    // "/0924648104/8096_583.html" -> ["0924648104", "8096_583.html"]
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
  
  // Title của chapter chưa được duyệt - sẽ bỏ qua
  const UNAPPROVED_CHAPTER_TITLE = '該章節未審核通過';

  /* ---------- 1.5) Fetch catalog API để kiểm tra duplicate chapters ---------- */
  async function fetchAndValidateCatalog(bookId, chapterPrefix) {
    console.log('=== FETCHING CATALOG API ===');
    const catalogUrl = 'https://www.novel543.com/book/ajaxcatalog.html';
    
    try {
      const res = await fetch(catalogUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        },
        body: `book_id=${bookId}&sid=${chapterPrefix}`,
        credentials: 'same-origin'
      });
      
      if (!res.ok) {
        console.error('Catalog API returned HTTP', res.status);
        return { maxChapter: null, hasDuplicates: false, duplicateInfo: null, skipChapters: [] };
      }
      
      const data = await res.json();
      console.log('Catalog API response - Total chapters:', data.length);
      
      // data format: [["第一章 ...", 1, "8001"], ["第二章 ...", 2, "8001"], ...]
      // Element 0: chapter name, Element 1: chapter id, Element 2: sid
      
      // Filter out unapproved chapters (該章節未審核通過)
      const skipChapters = []; // List of chapter indices to skip (1-based)
      const validChapters = [];
      
      for (let i = 0; i < data.length; i++) {
        const chapterName = data[i][0];
        const chapterIndex = i + 1; // 1-based index
        
        if (chapterName === UNAPPROVED_CHAPTER_TITLE || chapterName.includes(UNAPPROVED_CHAPTER_TITLE)) {
          console.log(`⏭️ SKIP unapproved chapter at index ${chapterIndex}: "${chapterName}"`);
          skipChapters.push(chapterIndex);
        } else {
          validChapters.push({ name: chapterName, index: chapterIndex });
        }
      }
      
      console.log('Valid chapters count:', validChapters.length);
      console.log('Skipped chapters count:', skipChapters.length);
      if (skipChapters.length > 0) {
        console.log('Skipped chapter indices:', skipChapters);
      }
      
      // Check for duplicates by chapter name (only on valid chapters)
      const chapterNames = validChapters.map(item => item.name);
      const uniqueNames = [...new Set(chapterNames)];
      const hasDuplicates = chapterNames.length !== uniqueNames.length;
      
      console.log('Original chapter count (excluding unapproved):', chapterNames.length);
      console.log('Unique chapter count:', uniqueNames.length);
      console.log('Has duplicates:', hasDuplicates);
      
      let duplicateInfo = null;
      let maxChapter = data.length; // Max chapter index (1-based, including skipped)

      if (hasDuplicates) {
        // Log duplicate names for awareness, but do NOT truncate maxChapter.
        // Duplicate names != duplicate chapters (different chapters can share a title).
        // Next-link navigation handles real content duplicates at fetch time.
        const seenNames = new Map();
        const duplicateNames = [];

        for (let i = 0; i < validChapters.length; i++) {
          const name = validChapters[i].name;
          const originalIndex = validChapters[i].index;

          if (seenNames.has(name)) {
            duplicateNames.push({ name, index: originalIndex, firstSeen: seenNames.get(name) });
          } else {
            seenNames.set(name, originalIndex);
          }
        }

        duplicateInfo = {
          originalCount: data.length,
          validCount: validChapters.length,
          uniqueCount: uniqueNames.length,
          duplicateCount: duplicateNames.length,
          skippedCount: skipChapters.length
        };

        console.log('=== DUPLICATE CHAPTER NAMES (info only) ===');
        console.log('Duplicate name count:', duplicateNames.length);
        for (const d of duplicateNames.slice(0, 10)) {
          console.log(`  "${d.name}" at index ${d.index} (first seen at ${d.firstSeen})`);
        }
        console.log('maxChapter unchanged:', maxChapter);
        console.log('===========================================');
      }
      
      // Log first and last 5 chapters for verification
      console.log('First 5 valid chapters:', validChapters.slice(0, 5).map(item => `[${item.index}] ${item.name}`));
      console.log('Last 5 valid chapters:', validChapters.slice(-5).map(item => `[${item.index}] ${item.name}`));
      
      return {
        maxChapter: maxChapter,
        hasDuplicates: hasDuplicates,
        duplicateInfo: duplicateInfo,
        skipChapters: skipChapters
      };
    } catch (error) {
      console.error('Error fetching catalog:', error);
      return { maxChapter: null, hasDuplicates: false, duplicateInfo: null, skipChapters: [] };
    }
  }

  // Fetch và validate catalog
  const catalogResult = await fetchAndValidateCatalog(bookId, chapterPrefix);
  
  // Determine actual max chapter
  let actualMaxChapter = chapterNumber; // Default từ DOM
  if (catalogResult.maxChapter !== null) {
    actualMaxChapter = catalogResult.maxChapter;
    console.log('Using maxChapter from catalog API:', actualMaxChapter);
  } else {
    console.log('Using maxChapter from DOM:', actualMaxChapter);
  }
  
  // Get list of chapters to skip
  const skipChapters = catalogResult.skipChapters || [];
  
  console.log('=== CHAPTER INFO ===');
  console.log('Original maxChapter (from DOM):', chapterNumber);
  console.log('Actual maxChapter (after dedup):', actualMaxChapter);
  console.log('Has duplicates:', catalogResult.hasDuplicates);
  if (catalogResult.duplicateInfo) {
    console.log('Duplicate info:', JSON.stringify(catalogResult.duplicateInfo, null, 2));
  }
  console.log('==================');

  /* ---------- 2) Helper sleep ---------- */
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  /* ---------- 3) Build URL chương / phần ---------- */
  function buildChapterUrl(chapter, part) {
    // part 1: 8096_x.html
    // part 2: 8096_x_2.html
    const partSuffix = part === 1 ? '' : '_2';
    return BASE_URL + "/" + bookId + "/" + chapterPrefix + "_" + chapter + partSuffix + ".html";
  }

  /* ---------- 3.5) Next-link navigation helpers ---------- */
  function extractNextLink(doc) {
    // Get "下一章" link from footer: last <a> in div.foot-nav
    const footNav = doc.querySelector('div.foot-nav');
    if (!footNav) return null;
    const links = footNav.querySelectorAll('a');
    const lastLink = links[links.length - 1];
    return lastLink ? lastLink.getAttribute('href') : null;
  }

  function getChapterIdFromHref(href) {
    // "/0701495882/8096_218.html" → 218
    // "/0701495882/8096_218_2.html" → 218
    if (!href) return null;
    const m = href.match(/_(\d+)(?:_\d+)?\.html/);
    return m ? parseInt(m[1], 10) : null;
  }

  function isDirUrl(href) {
    // "/0701495882/dir" → true
    return href && /\/dir\/?$/.test(href);
  }

  function isEndUrl(href) {
    // "/0701495882/end.html" → true
    return href && /\/end\.html\/?$/.test(href);
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

    // Extract title from h1 if needed (only for part 1)
    var title = "";
    if (extractTitle) {
      var h1 = contentDiv.querySelector("h1");
      if (h1) {
        title = h1.textContent.trim();
        // Remove (1/2), (2/2), （1 / 2）, etc. from title
        title = title
          .replace(/\s*\(\s*\d+\s*\/\s*\d+\s*\)\s*$/g, '')
          .replace(/\s*（\s*\d+\s*\/\s*\d+\s*）\s*$/g, '')
          .trim();
        console.log("  Chapter title: " + title);
        // Remove h1 from content to avoid duplication
        h1.remove();
      }
    } else {
      // For part 2, remove h1 to avoid duplicate title
      var h1 = contentDiv.querySelector("h1");
      if (h1) {
        h1.remove();
      }
    }

    // Xóa script/style
    var scripts = contentDiv.querySelectorAll("script, style");
    scripts.forEach(function (el) { el.remove(); });

    // Lấy HTML gốc bên trong, để còn giữ được cấu trúc p, br
    var htmlStr = contentDiv.innerHTML;

    // 1) Chuẩn hóa các thẻ xuống dòng
    // <br> -> 1 dòng mới
    htmlStr = htmlStr.replace(/<br\s*\/?>/gi, "\n");

    // Giữa 2 đoạn <p></p><p> -> 2 dòng mới
    htmlStr = htmlStr.replace(/<\/p>\s*<p[^>]*>/gi, "\n\n");

    // Bỏ các thẻ <p> còn lại (mở/đóng)
    htmlStr = htmlStr.replace(/<p[^>]*>/gi, "");
    htmlStr = htmlStr.replace(/<\/p>/gi, "");

    // Nếu trang dùng <div> làm đoạn, có thể chuyển luôn:
    // htmlStr = htmlStr.replace(/<\/div>\s*<div[^>]*>/gi, "\n\n");

    // 2) Bỏ mọi tag HTML còn lại
    htmlStr = htmlStr.replace(/<[^>]+>/g, "");

    // 3) Dọn khoảng trắng + xuống dòng thừa
    htmlStr = htmlStr.replace(/\r\n/g, "\n");
    htmlStr = htmlStr.replace(/\n[ \t]+/g, "\n");
    htmlStr = htmlStr.replace(/[ \t]+\n/g, "\n");
    htmlStr = htmlStr.replace(/\n{3,}/g, "\n\n");

    // Remove (1/2), (2/2) markers from content
    htmlStr = htmlStr.replace(/\(1\/2\)/g, "");
    htmlStr = htmlStr.replace(/\(2\/2\)/g, "");
    htmlStr = htmlStr.replace(/（1\/2）/g, "");
    htmlStr = htmlStr.replace(/（2\/2）/g, "");

    var text = htmlStr.trim();
    
    // Remove duplicate title from content if it appears at the beginning
    if (title && text) {
      // Check if content starts with title (with or without part markers)
      var titlePattern = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // Escape regex special chars
      var duplicateTitleRegex = new RegExp('^' + titlePattern + '\\s*(?:\\(?\\d+\\/\\d+\\)?)?\\s*(?:（\\d+\\/\\d+）)?\\s*\\n*', 'i');
      text = text.replace(duplicateTitleRegex, '').trim();
    }

    return { title: title, text: text };
  } catch (e) {
    console.error("Lỗi parse HTML:", e);
    return { title: "", text: "" };
  }
}


  /* ---------- 4) Fetch 1 page, trả text + next link ---------- */
  async function fetchChapterPage(pageUrl, extractTitle = false) {
    const maxRetries = 3;
    let attempt = 0;

    while (attempt <= maxRetries) {
      attempt++;
      console.log("  Fetching page (attempt " + attempt + "/" + (maxRetries + 1) + "):", pageUrl);

      try {
        const res = await fetch(pageUrl, { credentials: 'same-origin' });
        if (!res.ok) {
          throw new Error("HTTP " + res.status + " khi fetch " + pageUrl);
        }
        const html = await res.text();
        const result = extractChapterTextFromHtmlKeepLine(html, extractTitle);

        // Parse next link from footer
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const nextHref = extractNextLink(doc);

        console.log("  Got " + result.text.length + " chars, nextHref: " + nextHref);
        return { url: pageUrl, text: result.text, title: result.title, nextHref };
      } catch (err) {
        console.error("  Fetch error (attempt " + attempt + "):", err);
        if (attempt > maxRetries) {
          throw new Error("Failed to fetch " + pageUrl + " after " + (maxRetries + 1) + " attempts");
        }
        console.log("  Sleeping 1 min before retry...");
        await sleep(60_000);
      }
    }
  }

  /* ---------- 6) Fetch toàn bộ text truyện (next-link navigation) ---------- */
  async function fetchAllChapters(maxChapter, startChapter = 1, skipChapterList = []) {
    const chapterTexts = [];
    let lastCompletedChapter = startChapter - 1;
    let requestCount = 0;

    try {
      for (let ch = startChapter; ch <= maxChapter; ch++) {
        // Skip unapproved chapters
        if (skipChapterList.includes(ch)) {
          console.log(`⏭️ Skipping unapproved chapter ${ch}`);
          lastCompletedChapter = ch;
          continue;
        }

        console.log(`\n--- Chapter ${ch}/${maxChapter} ---`);

        let chapterTitle = "";
        let chapterParts = [];
        let currentUrl = buildChapterUrl(ch, 1);
        let partNumber = 1;
        let isChapterComplete = false;

        while (!isChapterComplete) {
          // Rate limiting: sleep every 6 chapters worth of requests
          if (requestCount > 0 && requestCount % 6 === 0) {
            console.log("Sleeping 10s...");
            await sleep(10_000);
          }

          const page = await fetchChapterPage(currentUrl, partNumber === 1);
          requestCount++;

          if (partNumber === 1) chapterTitle = page.title;
          chapterParts.push(page.text);

          // Determine if next link is a continuation or new chapter
          if (!page.nextHref || isDirUrl(page.nextHref) || isEndUrl(page.nextHref)) {
            console.log("  Chapter complete (no next link, dir or end URL)");
            isChapterComplete = true;
          } else {
            const nextChapterId = getChapterIdFromHref(page.nextHref);
            if (nextChapterId === ch) {
              // Same chapter, continuation part
              currentUrl = BASE_URL + page.nextHref;
              partNumber++;
              console.log(`  Continuing to part ${partNumber}...`);
            } else {
              // Different chapter, we're done with this one
              console.log("  Chapter complete (next link is different chapter)");
              isChapterComplete = true;
            }
          }
        }

        // Combine parts
        const contentText = chapterParts.join("\n");
        const fullChapter = chapterTitle ? `${chapterTitle}\n${contentText}` : contentText;
        chapterTexts.push(fullChapter);
        lastCompletedChapter = ch;

        console.log(`Chapter ${ch}: ${chapterParts.length} part(s), ${fullChapter.length} chars`);
        console.log(`Preview: ${fullChapter.slice(0, 200)}...`);
      }

      const fullText = chapterTexts.join("\n\n");

      console.log('\n=== FETCH COMPLETE ===');
      console.log('Total chapters:', chapterTexts.length);
      console.log('Total requests:', requestCount);
      console.log('Total length:', fullText.length);

      return {
        status: "success",
        text: fullText,
        currentChapter: maxChapter,
        totalChapters: maxChapter
      };
    } catch (error) {
      console.error("Error occurred while fetching chapters:", error);

      const partialText = chapterTexts.join("\n\n");

      console.log("Last completed chapter:", lastCompletedChapter);
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

  /* ---------- 7) Chạy ---------- */
  // NOTE: Không ghép existingText ở đây nữa - để Python xử lý
  // Điều này tránh duplicate khi retry
  // Sử dụng actualMaxChapter (đã dedup từ catalog API)
  // Pass skipChapters để bỏ qua các chapter chưa được duyệt
  const result = await fetchAllChapters(actualMaxChapter, startFromChapter, skipChapters);

  return {
    status: result.status,
    text: result.text,  // Chỉ trả về text mới fetch, không ghép existingText
    currentChapter: result.currentChapter,
    totalChapters: result.totalChapters,
    originalMaxChapter: chapterNumber,  // Max chapter từ DOM (có thể có duplicate)
    actualMaxChapter: actualMaxChapter,  // Max chapter sau khi dedup
    hasDuplicates: catalogResult.hasDuplicates,
    duplicateInfo: catalogResult.duplicateInfo,
    skipChapters: skipChapters,  // List of skipped chapter indices
    error: result.error || null
  };
}