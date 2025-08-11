import requests

url = "https://www.69shuba.com/book/85454/"

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en-US,en;q=0.9,vi;q=0.8",
    "cache-control": "max-age=0",
    "if-modified-since": "Mon, 11 Aug 2025 02:50:05 GMT",
    "if-none-match": "\"6f912ad4671d9a6d82f2326c78e2641f\"",
    "priority": "u=0, i",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
    "sec-ch-ua-arch": "\"x86\"",
    "sec-ch-ua-bitness": "\"64\"",
    "sec-ch-ua-full-version": "\"138.0.7204.185\"",
    "sec-ch-ua-full-version-list": "\"Not)A;Brand\";v=\"8.0.0.0\", \"Chromium\";v=\"138.0.7204.185\", \"Google Chrome\";v=\"138.0.7204.185\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-model": "\"\"",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-ch-ua-platform-version": "\"15.0.0\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "cookie": "_ga=GA1.1.842094013.1747818848; zh_choose=s; _ym_uid=1753171652757917886; _ym_uid_cst=zix7LPQsHA%3D%3D; _lr_env_src_ats=false; _sharedID=b9845997-d6a5-43f1-9f48-f3b3b22d378f; _sharedID_cst=zix7LPQsHA%3D%3D; cf_clearance=Iqp51Jmwrw4j5_BAlSfZsSikrvxSBsf.k80EjRSn8ro-1754880157-1.2.1.1-QSBq3c1CXjQyLeo685L3flF.n.boW3f0yR1.hcacfmycfldhkHwPNzotbqHe0qYCvGsZswalMFnDgptKUiM8v6c1gWytyw4SuxpsmX6f61YhsDFti1bnm7EA9r1m6TrCxDL_RFtNZPwwUebetpKHHyGUr5BJxtyHDgSOZmySBZ0GgDpASAEBUpZhyD1j_hqdBXWGRwyGPsZ4kqgbBVp0jFRx698_5sSWra2efAq249o; PHPSESSID=bp0q7hm0gg3m81tikiae8vodq4; jieqiUserInfo=jieqiUserId%3D1687290%2CjieqiUserUname%3Draymondt0809%2CjieqiUserName%3Draymondt0809%2CjieqiUserGroup%3D3%2CjieqiUserGroupName%3D%26%23x666E%3B%26%23x901A%3B%26%23x4F1A%3B%26%23x5458%3B%2CjieqiUserVip%3D0%2CjieqiUserHonorId%3D%2CjieqiUserHonor%3D%26%23x65B0%3B%26%23x624B%3B%26%23x4E0A%3B%26%23x8DEF%3B%2CjieqiUserToken%3D516108f4bac6a46622de138a9c386814%2CjieqiCodeLogin%3D0%2CjieqiCodePost%3D0%2CjieqiNewMessage%3D0%2CjieqiUserPassword%3D87e246cd31ab40890fd54d657975bd38%2CjieqiUserLogin%3D1754880205; jieqiVisitInfo=jieqiUserLogin%3D1754880205%2CjieqiUserId%3D1687290; shuba=11509-13887-23415-5867; _lr_retry_request=true; jieqiHistory=85454-39564385-%25u7B2C2%25u7AE0%2520%25u4E0D%25u53D8%25u8005-1754880343%7C89958-40426136-%25u7B2C2%25u7AE0%2520%25u68A6%25u4E0E%25u7535%25u5F71-1754469152; _ga_04LTEL5PWY=GS2.1.s1754880203$o15$g1$t1754881684$j59$l0$h0"
}

response = requests.get(url, headers=headers)

print(response.status_code)
print(response.text)
