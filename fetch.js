(async () => {
  /* ---------- 1) Lấy UL chứa danh sách chương ---------- */
   
  const ul = document.evaluate(
    '//*[@id="catalog"]/ul',
    document,
    null,
    XPathResult.FIRST_ORDERED_NODE_TYPE,
    null
  ).singleNodeValue;

  if (!ul) {
    console.warn('Không tìm thấy UL theo XPath //*[@id="catalog"]/ul');
    return;
  }

  /* ---------- 2) Thu thập & sắp xếp chapterId ---------- */
  const liSnap = document.evaluate('.//li', ul, null,
    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);

  const chapterIds = [];
  for (let i = 0; i < liSnap.snapshotLength; i++) {
    const li = liSnap.snapshotItem(i);
    const num  = parseInt(li.dataset.num, 10);          // data‑num
    const href = li.querySelector('a')?.href || '';
    const m = href.match(/\/(\d+)(?:\/)?$/);            // id cuối URL
    if (m) chapterIds.push({ num, id: m[1] });
  }

  chapterIds.sort((a, b) => a.num - b.num);            // tăng dần
  console.log('Tổng chương:', chapterIds.length);

  /* ---------- 3) Hàm tiện ích ---------- */
  function getBookId(url) {
    const m = url.match(/\/book\/(\d+)/);   // tìm “/book/” rồi lấy chuỗi số ngay sau
    return m ? m[1] : null;                 // ⇒ "51434"
  }
  const url = window.location.href;
  const bookId = getBookId(url);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const base  = 'https://www.69shuba.com/txt/' + bookId + '/'; // base URL

  /* ---------- 4) Vòng lặp fetch ---------- */
  const results = [];                                   // [{id,text}] → hoặc chỉ text
  for (let i = 0; i < chapterIds.length; i++) {

    if (i > 0 && i % 10 === 0) {                        // cứ 15 chương nghỉ 20 s

      await sleep(20000);
    }

    const { id: chapId } = chapterIds[i];
    const url = base + chapId;
    let success = false;
    let retryCount = 0;
    while (!success && retryCount < 5) {
      try {
        const resp = await fetch(url, { credentials: 'same-origin' });
        if (!resp.ok) {
          console.error('HTTP lỗi', resp.status, url);
          throw new Error(resp.status);
        }

        // Trang không gửi charset GBK → tự decode
        const buffer = await resp.arrayBuffer();
        const html   = new TextDecoder('gb18030').decode(buffer);

        // Parse DOM ngoại tuyến
        const doc  = new DOMParser().parseFromString(html, 'text/html');
        const evalOne = xp =>
          doc.evaluate(xp, doc, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null)
              .singleNodeValue;

        const node = evalOne('/html/body/div[2]/div[1]/div[3]');
        if (!node) {
          console.warn('Không tìm thấy node nội dung', url);
          continue;
        }

        /* ---------- 4.1) Xóa các phần tử không mong muốn ---------- */
        [
          '/html/body/div[2]/div[1]/div[3]/h1',
          '/html/body/div[2]/div[1]/div[3]/div[1]',
          '//*[@id="txtright"]',
          '/html/body/div[2]/div[1]/div[3]/div[4]',
        ].forEach(xp => {
          const garbage = evalOne(xp);
          if (garbage) garbage.parentNode.removeChild(garbage);
        });

        /* ---------- 4.2) Lấy text ---------- */
        var text = node.textContent.trim();
        var text = text.replace('(本章完)',''); // Xóa số chương đầu nếu có
        var text = text.replace('loadAdv(3, 0);',''); // Xóa số chương đầu nếu có

        results.push(text);                                   // hoặc {id: chapId, text}
        console.log(text.slice(0, 50), '...'); // Hiển thị 50 ký tự đầu
        success = true;
      } catch (e) {
        retryCount++;
        if (retryCount >= 5) {
          console.error('Quá 5 lần thử, bỏ qua chương này');
          return "error"
        }
        console.error('Lỗi fetch', url, e);
        console.log('Chờ 10 giây và thử lại...');
        await sleep(10000);
      }
    }
  }

  /* ---------- 5) Xuất kết quả ---------- */
  console.log('Kết quả:', results, 'chương');
 
  return results;
  
})();
