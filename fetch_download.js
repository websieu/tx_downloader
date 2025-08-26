async ({ args }) => {
  console.log(args);
  const host = "bilibili", vid = args, quality = "未知";
  const data = { host, vid, quality };

  const res = await fetch("https://greenvideo.cc/api/video/getDownloadInfo", {
    method: "POST",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      kdsystem: "GreenVideo",
    },
    credentials: "include",
    body: JSON.stringify(data),
  });

  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  const data_json = await res.json(); // nhớ khai báo const/let
  console.log(data_json);
  return data_json;
}