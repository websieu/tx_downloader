(async () => {
  /* ---------- A) Utils ---------- */
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // Giữ nguyên ý tưởng getBookId từ code gốc
  function getBookId(url) {
    const m = String(url).match(/\/book\/(\d+)/);
    return m ? m[1] : null;
  }

  /* ---------- B) Cấu hình dải URL cần duyệt ---------- */
  // Bắt đầu: https://www.69shuba.com/ajax_novels/full/1/1.htm
  // Kết thúc: https://www.69shuba.com/ajax_novels/full/1/12.html
  const base = 'https://www.69shuba.com/ajax_novels/class/4/'
  //const base = 'https://www.69shuba.com/ajax_novels/full/1/';
  const startPage = 2;
  const endPage   = 12;

  /* ---------- C) Vòng lặp tải & trích xuất bookId ---------- */
  const bookIdSet = new Set(); // khử trùng lặp
  let page = startPage;

  while (page <= endPage) {
    // Trang 1 có đuôi .htm, các trang sau dùng .html
    const ext = '.htm'
    const url = base + page + ext;

    console.log(`[FETCH] Page ${page}: ${url}`);

    try {
      const resp = await fetch(url, { credentials: 'same-origin' });
      if (!resp.ok) {
        console.error('HTTP lỗi', resp.status, url);
        throw new Error(`HTTP ${resp.status}`);
      }

      // Decode GB18030 để an toàn (giữ tinh thần code gốc)
      const buffer = await resp.arrayBuffer();
      const html = new TextDecoder('gb18030').decode(buffer);

      // Parse DOM
      const doc = new DOMParser().parseFromString(html, 'text/html');

      // Lấy tất cả thẻ <li><a ...> trong HTML
      // (dùng querySelectorAll cho gọn; nếu muốn có thể dùng XPath như code gốc)
      const anchors = doc.querySelectorAll('li > a[href]');

      console.log(`- Tìm thấy ${anchors.length} thẻ <li><a>`);

      anchors.forEach(a => {
        const href = a.getAttribute('href') || '';
        const id = getBookId(href);
        if (id) {
          bookIdSet.add(id);
        }
      });

    } catch (e) {
      console.error(`Lỗi khi xử lý trang ${page}:`, e);
      // Có thể bỏ qua trang lỗi để tiếp tục, hoặc tùy chọn retry nếu cần
    }

    // Mỗi lần request xong, sleep 5s trước khi sang trang tiếp theo
    if (page < endPage) {
      console.log('Ngủ 5 giây trước khi sang trang tiếp theo…');
      await sleep(3000);
    }
    page++;
  }

  /* ---------- D) Kết quả ---------- */
  const result = Array.from(bookIdSet);
  console.log('Tổng số bookId (unique):', result.length);
  console.log(result);

  return result;
})();
