# Fix Lỗi Trùng Lặp Nội Dung - Novel543 Fetcher

## 📅 Ngày: 14/01/2026

## 🐛 Mô Tả Vấn Đề

Khi fetch nội dung truyện từ novel543.com, nếu có lỗi xảy ra giữa chừng và hệ thống retry, **toàn bộ nội dung bị duplicate** (lặp 2 lần).

### Ví dụ:
- Truyện có 502 chương
- Đang fetch chapter 501 thì bị lỗi
- Retry lại → text bị lặp toàn bộ 1-502 lên 2 lần

---

## 🔍 Nguyên Nhân Gốc

### 1. JavaScript ghép `existingText` sai cách

**File:** `js/fetch_novel.js` (dòng 305-311 cũ)

```javascript
// CODE CŨ - SAI
let finalText = existingText;
const result = await fetchAllChapters(chapterNumber, startFromChapter);

if (existingText && result.text) {
    finalText = existingText + "\n\n" + result.text;  // ❌ JS ghép
}
```

**Vấn đề:** Khi Python retry, nó truyền `existingText` (text đã fetch) vào JS. JS lại ghép thêm lần nữa → **duplicate**.

---

### 2. `currentChapter` trả về sai khi có lỗi

**File:** `js/fetch_novel.js` (dòng 294 cũ)

```javascript
// CODE CŨ - SAI
return {
    status: "error",
    text: partialText,
    currentChapter: currentChapter - 1,  // ❌ Sai khi lỗi ở giữa chapter
    ...
};
```

**Vấn đề:** 
- Nếu đang fetch chapter 50, part 1 OK, part 2 lỗi
- `currentChapter = 50`, trả về `50 - 1 = 49`
- Nhưng `partialText` đã chứa part 1 của chapter 50!
- Python retry từ chapter 50 → **part 1 của ch50 bị duplicate**

---

### 3. Chapter chưa hoàn thành vẫn được đưa vào `partialText`

**File:** `js/fetch_novel.js` (dòng 278-291 cũ)

```javascript
// CODE CŨ - SAI
const uniqueChapters = [...new Set(collected.map(item => item.chapter))];
for (const ch of uniqueChapters) {
    const chapterParts = collected.filter(item => item.chapter === ch);
    if (chapterParts.length === 0) continue;  // ❌ Không check đủ 2 parts
    // ...
}
```

**Vấn đề:** Chapter có 1 part vẫn được đưa vào text → retry sẽ fetch lại chapter đó → **duplicate**.

---

## ✅ Giải Pháp Đã Áp Dụng

### Fix 1: JavaScript chỉ trả về text mới, Python xử lý việc ghép

**File:** `js/fetch_novel.js`

```javascript
// CODE MỚI - ĐÚNG
/* ---------- 7) Chạy ---------- */
// NOTE: Không ghép existingText ở đây nữa - để Python xử lý
// Điều này tránh duplicate khi retry
const result = await fetchAllChapters(chapterNumber, startFromChapter);

return {
    status: result.status,
    text: result.text,  // ✅ Chỉ trả về text mới fetch
    currentChapter: result.currentChapter,
    totalChapters: result.totalChapters,
    error: result.error || null
};
```

---

### Fix 2: Dùng `lastCompletedChapter` thay vì `currentChapter - 1`

**File:** `js/fetch_novel.js`

```javascript
// CODE MỚI - ĐÚNG
async function fetchAllChapters(maxChapter, startChapter = 1) {
    const collected = [];
    let lastCompletedChapter = startChapter - 1; // ✅ Chapter cuối đã hoàn thành ĐẦY ĐỦ

    try {
        for (let ch = startChapter; ch <= maxChapter; ch++) {
            const part1 = await fetchChapterPart(ch, 1);
            const part2 = await fetchChapterPart(ch, 2);

            collected.push(part1, part2);
            lastCompletedChapter = ch; // ✅ Chỉ update SAU KHI cả 2 parts OK
            // ...
        }
    }
}
```

---

### Fix 3: Chỉ giữ lại chapter đã hoàn thành đầy đủ khi lỗi

**File:** `js/fetch_novel.js`

```javascript
// CODE MỚI - ĐÚNG
} catch (error) {
    // ✅ Chỉ giữ chapter đã hoàn thành ĐẦY ĐỦ (có cả 2 parts)
    const completedChapters = collected.filter(item => item.chapter <= lastCompletedChapter);
    
    // ...
    
    for (const ch of uniqueChapters) {
        const chapterParts = completedChapters.filter(item => item.chapter === ch);
        if (chapterParts.length < 2) continue; // ✅ Bỏ qua chapter thiếu part
        // ...
    }
    
    return {
        status: "error",
        text: partialText,
        currentChapter: lastCompletedChapter, // ✅ Chapter cuối hoàn thành ĐẦY ĐỦ
        // ...
    };
}
```

---

### Fix 4: Python ghép text đúng cách

**File:** `novel543.py`

```python
# CODE MỚI - ĐÚNG
if isinstance(result, dict):
    status = result.get("status", "error")
    text = result.get("text", "")
    current_chapter = result.get("currentChapter", 0)
    
    # ✅ Python ghép text mới với existing_text
    if existing_text and text:
        combined_text = existing_text + "\n\n" + text
    else:
        combined_text = text if text else existing_text
    
    if status == "error":
        # ✅ Retry từ chapter tiếp theo
        # current_chapter là chapter cuối cùng đã hoàn thành ĐẦY ĐỦ
        return start_fetch_book_novel543(url, retry_attempt + 1, current_chapter + 1, combined_text)
```

---

## 📊 Kết Quả Test

### Test với simulated exceptions (3 error points):

| Attempt | Start | Existing | New | Error Point | Result |
|---------|-------|----------|-----|-------------|--------|
| 1 | Ch1 | 0 | 46,436 | Ch11-P2 | Error → retry |
| 2 | Ch11 | 46,436 | 53,558 | Ch22-P1 | Error → retry |
| 3 | Ch22 | 99,996 | 38,001 | Ch30-P2 | Error → retry |
| **4** | **Ch30** | **137,999** | **23,058** | - | **✅ SUCCESS** |

### Kết quả cuối:
- ✅ **Total: 161,059 ký tự**
- ✅ **34/34 chapter markers**
- ✅ **No duplicate chapters!**
- ✅ **No missing chapters!**

---

## 📁 Files Đã Sửa

1. **`js/fetch_novel.js`**
   - Bỏ ghép `existingText` trong JS
   - Dùng `lastCompletedChapter` 
   - Lọc chapter chưa hoàn thành

2. **`novel543.py`**
   - Python xử lý việc ghép `existing_text + text`
   - Retry đúng chapter

---

## 🔑 Nguyên Tắc Quan Trọng

1. **Single Responsibility**: JS chỉ fetch, Python ghép text
2. **Atomic Chapter**: Chapter chỉ được tính khi CẢ 2 parts đều OK
3. **Clean Retry**: Retry từ chapter tiếp theo, không bao gồm chapter lỗi
4. **No Double Concatenation**: Chỉ ghép text ở 1 nơi (Python)
