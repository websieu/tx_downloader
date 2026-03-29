/**
 * fetch_biquge.js
 * Script to fetch novel chapters from biquge.tw
 * 
 * Flow:
 * Step 1: Get all chapter links from //div[@class="booklist"]//li
 * Step 2: Sort chapters by ID ascending
 * Step 3: Loop through chapters and fetch content
 * Step 4: Handle multi-part chapters (part 1, part 2, etc.)
 * Step 5: Sleep 20s every 10 requests
 */

async ({ args }) => {
    // Get parameters from args
    const startChapter = args && args.startChapter ? args.startChapter : 1;
    const existingText = args && args.existingText ? args.existingText : "";
    const bookId = args && args.bookId ? args.bookId : "";
    
    console.log('Starting from chapter:', startChapter);
    console.log('Existing text length:', existingText.length);
    console.log('Book ID from args:', bookId);
    
    /* ---------- Helper Functions ---------- */
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    
    function getBookIdFromUrl(url) {
        const m = url.match(/\/book\/(\d+)/);
        return m ? m[1] : null;
    }
    
    function getChapterIdFromHref(href) {
        // Match both /book/123/456.html and /book/123/456_2.html
        const m = href.match(/\/(\d+)(?:_\d+)?\.html$/);
        return m ? m[1] : null;
    }
    
    function isPartUrl(href) {
        // Check if URL is a part URL like 80502506_2.html
        return /_\d+\.html$/.test(href);
    }
    
    function isBookUrl(href, bookId) {
        // Check if URL is the book index URL
        const pattern = new RegExp(`/book/${bookId}/?$`);
        return pattern.test(href) || href.endsWith(`/book/${bookId}/`);
    }
    
    function isNextChapter(href, currentChapterId, chapterIds) {
        // Check if this href points to the next chapter
        const nextChapterId = getChapterIdFromHref(href);
        if (!nextChapterId) return false;
        
        const currentIndex = chapterIds.indexOf(currentChapterId);
        if (currentIndex === -1 || currentIndex === chapterIds.length - 1) return false;
        
        return nextChapterId === chapterIds[currentIndex + 1];
    }
    
    /**
     * Extract text from HTML while preserving line breaks
     * Reference: fetch_novel.js - extractChapterTextFromHtmlKeepLine
     */
    function extractChapterTextKeepLine(contentDiv) {
        try {
            if (!contentDiv) {
                console.warn("Content div is null");
                return "";
            }
            
            // Remove script/style elements
            const scripts = contentDiv.querySelectorAll("script, style");
            scripts.forEach(el => el.remove());
            
            // Get innerHTML to preserve structure
            let htmlStr = contentDiv.innerHTML;
            
            // 1) Normalize line break tags
            // <br> -> newline
            htmlStr = htmlStr.replace(/<br\s*\/?>/gi, "\n");
            
            // Between </p><p> -> 2 newlines (paragraph break)
            htmlStr = htmlStr.replace(/<\/p>\s*<p[^>]*>/gi, "\n\n");
            
            // Remove remaining <p> tags
            htmlStr = htmlStr.replace(/<p[^>]*>/gi, "");
            htmlStr = htmlStr.replace(/<\/p>/gi, "\n");
            
            // Handle <div> as paragraphs too
            htmlStr = htmlStr.replace(/<\/div>\s*<div[^>]*>/gi, "\n\n");
            htmlStr = htmlStr.replace(/<div[^>]*>/gi, "");
            htmlStr = htmlStr.replace(/<\/div>/gi, "\n");
            
            // 2) Remove all remaining HTML tags
            htmlStr = htmlStr.replace(/<[^>]+>/g, "");
            
            // 3) Decode HTML entities
            const textArea = document.createElement("textarea");
            textArea.innerHTML = htmlStr;
            htmlStr = textArea.value;
            
            // 4) Clean up whitespace and newlines
            htmlStr = htmlStr.replace(/\r\n/g, "\n");
            htmlStr = htmlStr.replace(/\n[ \t]+/g, "\n");
            htmlStr = htmlStr.replace(/[ \t]+\n/g, "\n");
            htmlStr = htmlStr.replace(/\n{3,}/g, "\n\n"); // Max 2 consecutive newlines
            
            // 5) Clean up ad text and garbage strings
            htmlStr = htmlStr
                .replace(/請記住本書首發域名.*/g, '')
                .replace(/筆趣閣.*/g, '')
                .replace(/手機版閱讀網址.*/g, '')
                .replace(/\(本章完\)/g, '')
                .replace(/\(本章未完，請點擊下一頁繼續閱讀\)/g, '')
                .replace(/最新網址.*/g, '')
                .replace(/biquge\.tw/gi, '')
                .replace(/www\..+?\.(com|tw|net)/gi, '')
                // Remove malformed HTML comments
                .replace(/&l;!--.*?--&g;/gi, '')
                .replace(/&lt;!--.*?--&gt;/gi, '');
            
            return htmlStr.trim();
        } catch (e) {
            console.error("Error extracting text:", e);
            return "";
        }
    }
    
    /* ---------- Step 1: Get chapter list ---------- */
    console.log("Step 1: Getting chapter list...");
    
    const currentBookId = bookId || getBookIdFromUrl(window.location.href);
    if (!currentBookId) {
        console.error("Could not determine book ID");
        return { status: "error", text: existingText, currentChapter: 0, error: "Could not determine book ID" };
    }
    
    const baseUrl = `https://www.biquge.tw/book/${currentBookId}/`;
    console.log("Book ID:", currentBookId);
    console.log("Base URL:", baseUrl);
    
    // Get all li elements from booklist
    const booklistDiv = document.evaluate(
        '//div[@class="booklist"]//li',
        document,
        null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
        null
    );
    
    if (!booklistDiv || booklistDiv.snapshotLength === 0) {
        console.error("Could not find chapter list");
        return { status: "error", text: existingText, currentChapter: 0, error: "Could not find chapter list" };
    }
    
    /* ---------- Step 2: Collect and sort chapter IDs ---------- */
    console.log("Step 2: Collecting chapter links...");
    
    const chapters = [];
    for (let i = 0; i < booklistDiv.snapshotLength; i++) {
        const li = booklistDiv.snapshotItem(i);
        const anchor = li.querySelector('a');
        if (anchor) {
            const href = anchor.getAttribute('href');
            const chapterId = getChapterIdFromHref(href);
            if (chapterId) {
                chapters.push({
                    id: chapterId,
                    href: href,
                    title: anchor.textContent.trim()
                });
            }
        }
    }
    
    // Sort chapters by ID (numeric ascending)
    chapters.sort((a, b) => parseInt(a.id) - parseInt(b.id));
    
    console.log(`Total chapters found: ${chapters.length}`);
    
    if (chapters.length === 0) {
        return { status: "error", text: existingText, currentChapter: 0, error: "No chapters found" };
    }
    
    // Create array of just chapter IDs for lookup
    const chapterIds = chapters.map(c => c.id);
    
    /* ---------- Step 3 & 4: Fetch chapter content ---------- */
    console.log("Step 3: Fetching chapter content...");
    
    // NOTE: Không đưa existingText vào results - để Python xử lý việc ghép
    // Điều này tránh duplicate khi retry
    let results = [];
    let requestCount = 0;
    let currentChapterIndex = Math.max(0, startChapter - 1);
    let lastCompletedChapter = startChapter - 1; // Chapter cuối đã hoàn thành ĐẦY ĐỦ
    
    try {
        for (let i = currentChapterIndex; i < chapters.length; i++) {
            const chapter = chapters[i];
            console.log(`\n--- Fetching chapter ${i + 1}/${chapters.length}: ${chapter.title} ---`);
            
            // Sleep every 10 requests
            if (requestCount > 0 && requestCount % 10 === 0) {
                console.log("Sleeping 20 seconds...");
                await sleep(20000);
            }
            
            // Fetch all parts of this chapter
            let chapterContent = [];
            let chapterTitle = ""; // Store chapter title from part 1
            let currentUrl = `https://www.biquge.tw${chapter.href}`;
            let partNumber = 1;
            let isChapterComplete = false;
            
            while (!isChapterComplete) {
                console.log(`  Part ${partNumber}: ${currentUrl}`);
                requestCount++;
                
                let success = false;
                let retryCount = 0;
                let partContent = "";
                let nextUrl = null;
                
                while (!success && retryCount < 5) {
                    try {
                        const resp = await fetch(currentUrl, { credentials: 'same-origin' });
                        if (!resp.ok) {
                            throw new Error(`HTTP ${resp.status}`);
                        }
                        
                        const html = await resp.text();
                        
                        // Parse HTML
                        const doc = new DOMParser().parseFromString(html, 'text/html');
                        
                        // Get chapter title from h1 tag (only on part 1)
                        if (partNumber === 1) {
                            const h1 = doc.querySelector('h1');
                            if (h1) {
                                chapterTitle = h1.textContent.trim();
                                // Remove (1/2), (2/2), （1 / 2）, etc. from title
                                // Handle both regular () and Chinese （） parentheses
                                chapterTitle = chapterTitle
                                    .replace(/\s*\(\s*\d+\s*\/\s*\d+\s*\)\s*$/g, '')
                                    .replace(/\s*（\s*\d+\s*\/\s*\d+\s*）\s*$/g, '')
                                    .trim();
                                console.log(`  Chapter title: ${chapterTitle}`);
                            }
                        }
                        
                        // Get chapter content
                        const contentDiv = doc.evaluate(
                            '//div[@id="chaptercontent"]',
                            doc,
                            null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE,
                            null
                        ).singleNodeValue;
                        
                        if (!contentDiv) {
                            console.warn("  Content div not found");
                            throw new Error("Content div not found");
                        }
                        
                        // Get text content while preserving line breaks
                        partContent = extractChapterTextKeepLine(contentDiv);
                        
                        // Get next URL from #next_url link
                        const nextLink = doc.getElementById('next_url');
                        if (nextLink) {
                            const nextHref = nextLink.getAttribute('href');
                            console.log(`  Next link href: ${nextHref}`);
                            
                            // Check if next URL is the book index (means we're done)
                            if (isBookUrl(nextHref, currentBookId)) {
                                console.log("  Reached end of book");
                                isChapterComplete = true;
                                nextUrl = null;
                            }
                            // Check if next URL is the next chapter
                            else if (isNextChapter(nextHref, chapter.id, chapterIds)) {
                                console.log("  Moving to next chapter");
                                isChapterComplete = true;
                                nextUrl = null;
                            }
                            // Check if next URL is another part of current chapter
                            else if (isPartUrl(nextHref) || getChapterIdFromHref(nextHref) === chapter.id) {
                                nextUrl = nextHref.startsWith('http') ? nextHref : `https://www.biquge.tw${nextHref}`;
                                console.log(`  Continuing to part ${partNumber + 1}`);
                            }
                            else {
                                // Default: assume it's a new chapter
                                console.log("  End of current chapter");
                                isChapterComplete = true;
                                nextUrl = null;
                            }
                        } else {
                            console.log("  No next link found, chapter complete");
                            isChapterComplete = true;
                        }
                        
                        success = true;
                        
                    } catch (e) {
                        retryCount++;
                        console.error(`  Error fetching (attempt ${retryCount}/5):`, e.message);
                        if (retryCount < 5) {
                            console.log("  Retrying in 10 seconds...");
                            await sleep(10000);
                        }
                    }
                }
                
                if (!success) {
                    console.error("  Failed to fetch after 5 retries");
                    // Chỉ trả về text của chapters đã hoàn thành ĐẦY ĐỦ
                    // Không bao gồm chapter đang fetch dở
                    console.log("Last completed chapter:", lastCompletedChapter);
                    return {
                        status: "error",
                        text: results.join("\n\n"),  // Chỉ chứa chapters hoàn thành
                        currentChapter: lastCompletedChapter,  // Chapter cuối đã hoàn thành ĐẦY ĐỦ
                        error: `Failed to fetch chapter ${i + 1}, part ${partNumber}`
                    };
                }
                
                chapterContent.push(partContent);
                
                if (nextUrl && !isChapterComplete) {
                    currentUrl = nextUrl;
                    partNumber++;
                    
                    // Sleep every 10 requests (including part requests)
                    if (requestCount % 10 === 0) {
                        console.log("Sleeping 20 seconds...");
                        await sleep(20000);
                    }
                }
            }
            
            // Combine all parts of the chapter
            // Format: Title + newline + content
            const contentText = chapterContent.join("\n");
            const fullChapterContent = chapterTitle ? `${chapterTitle}\n${contentText}` : contentText;
            results.push(fullChapterContent);
            
            // Chỉ update lastCompletedChapter SAU KHI chapter hoàn thành đầy đủ
            lastCompletedChapter = i + 1;
            
            console.log(`  Chapter ${i + 1} complete (${chapterContent.length} parts, ${fullChapterContent.length} chars)`);
            console.log(`  Preview: ${fullChapterContent.slice(0, 300)}...`);
        }
        
        /* ---------- Step 5: Return results ---------- */
        console.log("\n=== Fetch complete! ===");
        console.log(`Total chapters: ${chapters.length}`);
        console.log(`Total requests: ${requestCount}`);
        
        const fullText = results.join("\n\n");
        console.log(`Total text length: ${fullText.length} characters`);
        
        return {
            status: "success",
            text: fullText,
            currentChapter: chapters.length,
            totalChapters: chapters.length
        };
        
    } catch (e) {
        console.error("Unexpected error:", e);
        console.log("Last completed chapter:", lastCompletedChapter);
        return {
            status: "error",
            text: results.join("\n\n"),  // Chỉ chứa chapters hoàn thành
            currentChapter: lastCompletedChapter,  // Chapter cuối đã hoàn thành ĐẦY ĐỦ
            error: e.message
        };
    }
    
}
